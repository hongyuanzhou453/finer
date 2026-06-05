from fastapi import APIRouter
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from pathlib import Path
import hashlib
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime

from finer.config import load_feishu_config
from finer.ingestion.classifier import FileClassifier
from finer.ingestion.feishu_poller import FeishuPoller, SyncState
from finer.ingestion.nlm_sync import resolve_nlm_cli
from finer.manifests import ContentManifest, _infer_file_type, build_content_id, write_manifest, register_file
from finer.paths import REPO_ROOT, DATA_ROOT, f0_raw_dir, f0_record_path, f0_receipt_path
from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportReceipt
from finer.utils.time import now_utc
from finer.errors import FinerError, ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter()

FEISHU_POOL_DIR = DATA_ROOT / "feishu_sync_pool"
NLM_POOL_DIR = DATA_ROOT / "nlm_sync_pool"
RAW_DIR = DATA_ROOT / "raw"

# Ensure directories exist
for d in [FEISHU_POOL_DIR, NLM_POOL_DIR, RAW_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# pool_type -> canonical source_platform mapping
_POOL_TYPE_TO_PLATFORM: Dict[str, str] = {
    "nlm": "notebooklm",
    "feishu": "feishu",
    "wechat": "wechat",
    "bilibili": "bilibili",
    "local": "local",
}


class FetchRequest(BaseModel):
    chat_id: str

class NLMFetchRequest(BaseModel):
    notebook_id: str

class ImportRequest(BaseModel):
    filenames: List[str]
    pool_type: str = "feishu"  # feishu or nlm


# ── NotebookLM F0 constants (GATE canonical) ───────────────────────────────
# A NotebookLM source is intake source_type ``nlm_note`` on platform ``nlm``.
# The ImportReceipt routes under the coarse ``notebooklm`` channel; the finer
# per-channel kind is ``nlm_note``.
NLM_PLATFORM = "nlm"
NLM_SOURCE_TYPE = "nlm_note"
NLM_SOURCE_CHANNEL = "notebooklm"
NLM_SOURCE_KIND = "nlm_note"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _register_f0_index(record: ContentRecord, receipt: ImportReceipt) -> None:
    """Best-effort Project Memory registration for a successful F0 import.

    Idempotent (``F0IndexWriter.record_imported`` uses INSERT OR IGNORE). Any
    failure (PM DB missing/locked) is logged and swallowed so an import is never
    lost just because the hot index could not be updated. Tests patch this to a
    no-op to avoid writing to the live project database.
    """
    try:
        from finer.ingestion.f0_index_writer import F0IndexWriter

        F0IndexWriter().record_imported(record, receipt)
    except Exception as exc:  # pragma: no cover - PM availability is environmental
        logger.warning(
            "Project Memory registration skipped for %s: %s",
            record.content_id,
            exc,
        )


def _build_nlm_receipt(
    *,
    record: ContentRecord,
    record_path: Path,
    raw_path: str,
    raw_sha256: str,
    status: str = "completed",
    records_created: int = 1,
    records_skipped: int = 0,
) -> ImportReceipt:
    """Build the GATE ImportReceipt for one fetched NotebookLM source."""
    finished = now_utc()
    return ImportReceipt(
        run_id=f"nlm_{record.content_id}",
        source_channel=NLM_SOURCE_CHANNEL,
        source_kind=NLM_SOURCE_KIND,
        status=status,
        content_id=record.content_id,
        external_source_id=record.external_source_id,
        dedupe_fingerprint=record.dedupe_fingerprint,
        collected_at=record.collected_at,
        started_at=finished,
        finished_at=finished,
        raw_sha256={"nlm_markdown": raw_sha256},
        raw_paths={"nlm_markdown": raw_path},
        record_path=str(record_path),
        records_created=records_created,
        records_skipped=records_skipped,
    )


def _fetch_nlm_notebook_core(notebook_id: str) -> Dict[str, Any]:
    """Fetch all sources of a NotebookLM notebook into F0 (ContentRecord + PM).

    Shared by ``POST /nlm/fetch`` and the NotebookLM branch of
    ``POST /api/sources/refresh`` so both produce canonical F0 output with
    dedupe + Project Memory registration. Raises ``FinerError`` on upstream
    failure; per-source errors are counted, not raised.
    """
    config = load_feishu_config(REPO_ROOT)
    nlm_cli_path = resolve_nlm_cli(config.get("notebooklm", {}).get("nlm_cli_path"))

    try:
        res = subprocess.run(
            [nlm_cli_path, "source", "list", notebook_id, "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        sources = json.loads(res.stdout)
    except FileNotFoundError as e:
        raise FinerError(
            ErrorCode.NLM_EXT_001,
            f"nlm CLI not found at '{nlm_cli_path}'. Install nlm or set "
            "notebooklm.nlm_cli_path.",
            stage="F0",
            operation="nlm_fetch",
            source_channel=NLM_SOURCE_CHANNEL,
            retryable=False,
            cause=e,
        ) from e
    except Exception as e:
        raise FinerError(
            ErrorCode.NLM_EXT_001,
            f"Error listing NLM sources: {e}",
            stage="F0",
            operation="nlm_fetch",
            source_channel=NLM_SOURCE_CHANNEL,
            retryable=True,
            cause=e,
        ) from e

    downloaded: List[str] = []
    skipped: List[str] = []
    errors = 0
    record_dir = f0_record_path(NLM_PLATFORM, "_").parent
    raw_dir = f0_raw_dir(NLM_PLATFORM, notebook_id)
    record_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for source in sources:
        source_id = source.get("id")
        title = source.get("title", f"Unknown_Source_{source_id}")
        # NotebookLM source_id is a stable platform-native id -> external_source_id
        external_source_id = f"nlm:{notebook_id}:{source_id}"
        content_id = f"nlm_{hashlib.sha256(external_source_id.encode('utf-8')).hexdigest()[:24]}"

        record_path = f0_record_path(NLM_PLATFORM, content_id)
        if record_path.exists():
            # Dedupe: this NLM source already imported as an F0 ContentRecord.
            skipped.append(title)
            continue

        try:
            content_res = subprocess.run(
                [nlm_cli_path, "source", "content", source_id],
                capture_output=True,
                text=True,
                check=True,
            )
            source_data = json.loads(content_res.stdout)
            content_text = source_data.get("value", {}).get("content", "")
            if not content_text:
                continue

            nlm_source_type = source_data.get("value", {}).get("source_type", "unknown")
            md_content = (
                f"# {title}\n\n"
                f"- **Notebook ID**: {notebook_id}\n"
                f"- **Source ID**: {source_id}\n"
                f"- **Type**: {nlm_source_type}\n\n"
                "---\n\n"
                f"{content_text}"
            )
            raw_bytes = md_content.encode("utf-8")
            raw_sha256 = _sha256_bytes(raw_bytes)
            raw_path = raw_dir / f"{content_id}.md"
            raw_path.write_bytes(raw_bytes)

            collected = now_utc()
            record = ContentRecord(
                content_id=content_id,
                source_type=NLM_SOURCE_TYPE,
                source_platform=NLM_PLATFORM,
                creator_id="notebooklm",
                creator_name="notebooklm",
                published_at=None,
                collected_at=collected,
                title=title,
                raw_path=str(raw_path),
                file_type=_infer_file_type(raw_path.suffix),
                metadata={
                    "nlm_notebook_id": notebook_id,
                    "nlm_source_id": source_id,
                    "nlm_source_type": nlm_source_type,
                    "registered_via": "nlm-fetch",
                    "raw_sha256": raw_sha256,
                },
                external_source_id=external_source_id,
                dedupe_fingerprint=_sha256_bytes(
                    external_source_id.encode("utf-8") + b"\0" + raw_bytes
                ),
                language="zh",
                market_scope=["US", "HK", "A"],
            )
            record_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

            receipt = _build_nlm_receipt(
                record=record,
                record_path=record_path,
                raw_path=str(raw_path),
                raw_sha256=raw_sha256,
            )
            receipt_path = f0_receipt_path(NLM_PLATFORM, content_id)
            receipt_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")

            _register_f0_index(record, receipt)
            downloaded.append(title)

        except Exception as inner_e:
            errors += 1
            logger.error("Error fetching NLM source %s: %s", source_id, inner_e)
            continue

    return {
        "status": "ok",
        "sources_scanned": len(sources),
        "downloaded": len(downloaded),
        "skipped": len(skipped),
        "errors": errors,
        "files": downloaded,
    }


@router.get("/feishu/chats")
async def get_feishu_chats():
    """Returns a list of configured Feishu chats."""
    try:
        config = load_feishu_config(REPO_ROOT)
        chats = config.get("feishu", {}).get("watched_chats", [])
        return {"chats": chats}
    except FileNotFoundError as e:
        raise FinerError(
            ErrorCode.SYS_CFG_001,
            "Feishu config not found. Please configure first.",
            stage="F0",
            operation="feishu_list_chats",
            source_channel="feishu",
            retryable=False,
            cause=e,
        )


@router.post("/feishu/fetch")
async def fetch_feishu_chat(req: FetchRequest):
    """
    Downloads messages and attachments from a selected feishu chat into the sync pool.
    This acts as Phase 1 (Stage 1) of the integration pipeline.
    """
    config = load_feishu_config(REPO_ROOT)
    feishu_cfg = config.get("feishu", {})
    lark_cli_path = feishu_cfg.get("lark_cli_path", "/opt/homebrew/bin/lark-cli")
    
    # Verify chat is watched to get its metadata
    chat_cfg = next((c for c in feishu_cfg.get("watched_chats", []) if c["chat_id"] == req.chat_id), None)
    if not chat_cfg:
        raise FinerError(
            ErrorCode.F0_IN_001,
            "Chat ID not registered in configurations.",
            stage="F0",
            operation="feishu_fetch",
            source_channel="feishu",
            retryable=False,
        )
        
    chat_name = chat_cfg.get("name", "Unknown Chat")
    
    state_file = REPO_ROOT / feishu_cfg.get("state_file", "data/.feishu_sync_state.json")
    state = SyncState(state_file)
    since = state.get_last_sync(req.chat_id)
    
    # We override inbox_dir to our explicit persistent pool
    poller = FeishuPoller(FEISHU_POOL_DIR, lark_cli_path=lark_cli_path)
    
    try:
        messages = poller.poll_chat(req.chat_id, since=since)
        if not messages:
            return {"status": "ok", "downloaded": 0, "messages_scanned": 0, "message": "No new messages."}
            
        downloads = poller.download_all_attachments(messages)
        
        # Save transcript for text
        text_messages = [m for m in messages if m.msg_type in ("text", "post")]
        transcript_files = []
        if text_messages:
            text_messages.sort(key=lambda x: x.create_time)
            start_time = text_messages[0].create_time.strftime("%Y%m%d_%H%M")
            end_time = text_messages[-1].create_time.strftime("%Y%m%d_%H%M")
            filename = f"chat_history_{chat_name}_{start_time}_to_{end_time}.md"
            target_path = FEISHU_POOL_DIR / filename
            
            content = [
                f"# Chat History: {chat_name}\n",
                f"- **Chat ID**: {req.chat_id}",
                f"- **Time Range**: {text_messages[0].create_time.isoformat()} 至 {text_messages[-1].create_time.isoformat()}\n",
                "---",
            ]
            for msg in text_messages:
                time_str = msg.create_time.strftime("%Y-%m-%d %H:%M:%S")
                content.append(f"### [{time_str}] {msg.sender_id}")
                content.append(f"{msg.content_text}\n")
            
            target_path.write_text("\n".join(content), encoding="utf-8")
            transcript_files.append(filename)
            
        # Update state
        latest_time = max(m.create_time for m in messages)
        state.update_last_sync(req.chat_id, latest_time)
        
        pulled_files = [d.original_name for d in downloads] + transcript_files
        
        return {
            "status": "ok",
            "messages_scanned": len(messages),
            "downloaded": len(pulled_files),
            "files": pulled_files
        }
        
    except Exception as e:
        raise FinerError(
            ErrorCode.F0_EXT_001,
            f"Error fetching Feishu data: {e}",
            stage="F0",
            operation="feishu_fetch",
            source_channel="feishu",
            retryable=True,
            cause=e,
        )


@router.get("/nlm/notebooks")
async def get_nlm_notebooks():
    """Returns a list of accessible NotebookLM notebooks."""
    config = load_feishu_config(REPO_ROOT)
    nlm_cli_path = resolve_nlm_cli(config.get("notebooklm", {}).get("nlm_cli_path"))
    try:
        res = subprocess.run([nlm_cli_path, "notebook", "list", "--json"], capture_output=True, text=True, check=True)
        notebooks = json.loads(res.stdout)
        return {"notebooks": notebooks}
    except FileNotFoundError as e:
        raise FinerError(
            ErrorCode.NLM_EXT_001,
            f"nlm CLI not found at '{nlm_cli_path}'. Install nlm or set notebooklm.nlm_cli_path.",
            stage="F0",
            operation="nlm_list_notebooks",
            source_channel=NLM_SOURCE_CHANNEL,
            retryable=False,
            cause=e,
        ) from e
    except Exception as e:
        raise FinerError(
            ErrorCode.NLM_EXT_001,
            f"Failed to list notebooks: {e}",
            stage="F0",
            operation="nlm_list_notebooks",
            source_channel=NLM_SOURCE_CHANNEL,
            retryable=True,
            cause=e,
        ) from e

@router.post("/nlm/fetch")
async def fetch_nlm_notebook(req: NLMFetchRequest):
    """Fetch a NotebookLM notebook's sources into F0.

    Each source becomes a canonical ``ContentRecord`` (source_type
    ``nlm_note``) plus an ``ImportReceipt``, archived under data/raw/nlm and
    registered in Project Memory. Re-fetching a source whose ContentRecord
    already exists is skipped (dedupe by nlm source id).
    """
    return _fetch_nlm_notebook_core(req.notebook_id)


@router.get("/pool")
async def list_pool_files():
    """Lists all files sitting in the feishu_sync_pool and nlm_sync_pool"""
    def _scan_dir(d: Path, origin_type: str):
        if not d.exists(): return []
        items = []
        for f in d.iterdir():
            if f.is_file() and not f.name.startswith('.'):
                size = f.stat().st_size
                mtime = f.stat().st_mtime
                ext = f.suffix.lower()
                
                # identify if previewable directly
                previewable = ext in ['.png', '.jpg', '.jpeg', '.webp', '.pdf']
                
                items.append({
                    "name": f.name,
                    "type": ext.replace(".", "") or "file",
                    "origin": origin_type,
                    "date": datetime.fromtimestamp(mtime).isoformat(),
                    "size_bytes": size,
                    "previewable": previewable,
                    "download_path": str(f.relative_to(DATA_ROOT))
                })
        return items
        
    feishu_items = _scan_dir(FEISHU_POOL_DIR, "feishu")
    nlm_items = _scan_dir(NLM_POOL_DIR, "nlm")
    
    all_items = feishu_items + nlm_items
    all_items.sort(key=lambda x: x['date'], reverse=True)
    return {"files": all_items}


@router.post("/import")
async def import_from_pool(req: ImportRequest):
    """
    Imports files from sync pools into raw/, triggering the downstream
    classification and physical placement logic.
    """
    config = load_feishu_config(REPO_ROOT)
    classifier = FileClassifier(config)
    
    results = []
    
    for filename in req.filenames:
        # Determine source dir
        source_dir = FEISHU_POOL_DIR if req.pool_type == "feishu" else NLM_POOL_DIR
        source_file = source_dir / filename
        
        if not source_file.exists():
            results.append({"filename": filename, "status": "error", "message": "File not found in pool."})
            continue
            
        try:
            # 1. Classify
            classification = classifier.classify(
                filename=filename,
                context_text="", 
                sent_at=datetime.utcnow(),
                chat_name="Imported Hub",
                chat_default_creator="_inbox"
            )
            
            # 2. Move to raw/creator_id/content_type
            creator_id = classification.creator_id or "_inbox"
            content_type = classification.source_type or "unclassified"

            target_dir = RAW_DIR / creator_id / content_type
            target_dir.mkdir(parents=True, exist_ok=True)
            
            target_path = target_dir / filename
            counter = 1
            while target_path.exists():
                target_path = target_dir / f"{source_file.stem}_{counter}{source_file.suffix}"
                counter += 1
                
            shutil.move(str(source_file), str(target_path))
            
            # 3. Create Manifest
            content_id = build_content_id(creator_id, content_type, filename)
            manifest = ContentManifest(
                content_id=content_id,
                source_type=content_type,
                source_platform=_POOL_TYPE_TO_PLATFORM.get(req.pool_type, req.pool_type),
                creator_id=creator_id,
                creator_name=creator_id,
                published_at=datetime.utcnow().isoformat(),
                collected_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                title=filename,
                raw_path=str(target_path),
                file_type=_infer_file_type(target_path.suffix),
                metadata={
                    "classification_rule": classification.matched_rule,
                    "classification_confidence": classification.confidence
                },
                source_url=None,
                external_source_id=None,
                dedupe_fingerprint=None,
                language="zh",
                market_scope=["US", "HK", "A"],
            )
            write_manifest(REPO_ROOT, manifest)
            
            results.append({"filename": filename, "status": "success", "content_id": content_id, "target": str(target_path)})
            
        except Exception as e:
            results.append({"filename": filename, "status": "error", "message": str(e)})
            
    return {"results": results}
