from fastapi import APIRouter
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from pathlib import Path
import os
import shutil
from datetime import datetime

from finer.config import load_feishu_config
from finer.ingestion.feishu_poller import FeishuPoller, SyncState
from finer.ingestion.classifier import FileClassifier
from finer.ingestion.vision_utils import VisionDescriptor, get_vision_transcript_path
from finer.manifests import ContentManifest, _infer_file_type, build_content_id, write_manifest, register_file
from finer.paths import REPO_ROOT, DATA_ROOT
from finer.errors import FinerError, ErrorCode

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


import subprocess
import json

@router.get("/nlm/notebooks")
async def get_nlm_notebooks():
    """Returns a list of accessible NotebookLM notebooks."""
    try:
        config = load_feishu_config(REPO_ROOT)
        nlm_cli_path = config.get("notebooklm", {}).get("nlm_cli_path", "/Users/zhouhongyuan/.local/bin/nlm")
        res = subprocess.run([nlm_cli_path, "notebook", "list", "--json"], capture_output=True, text=True, check=True)
        notebooks = json.loads(res.stdout)
        return {"notebooks": notebooks}
    except Exception as e:
        raise FinerError(
            ErrorCode.NLM_EXT_001,
            f"Failed to list notebooks: {e}",
            stage="F0",
            operation="nlm_list_notebooks",
            source_channel="nlm",
            retryable=True,
            cause=e,
        )

@router.post("/nlm/fetch")
async def fetch_nlm_notebook(req: NLMFetchRequest):
    """
    Downloads sources from a NotebookLM notebook into the nlm_sync_pool.
    """
    config = load_feishu_config(REPO_ROOT)
    nlm_cli_path = config.get("notebooklm", {}).get("nlm_cli_path", "/Users/zhouhongyuan/.local/bin/nlm")
    
    try:
        # Get source list
        res = subprocess.run([nlm_cli_path, "source", "list", req.notebook_id, "--json"], capture_output=True, text=True, check=True)
        sources = json.loads(res.stdout)
        
        downloaded = []
        for source in sources:
            source_id = source.get("id")
            title = source.get("title", f"Unknown_Source_{source_id}")

            # Sanitize filename
            safe_title = "".join([c if c.isalnum() or c in (" ", "-", "_") else "_" for c in title]).strip()

            try:
                content_res = subprocess.run([nlm_cli_path, "source", "content", source_id], capture_output=True, text=True, check=True)
                source_data = json.loads(content_res.stdout)

                content_text = source_data.get("value", {}).get("content", "")
                if content_text:
                    filename = f"NLM_{safe_title}.md"
                    target_path = NLM_POOL_DIR / filename

                    md_content = f"# {title}\n\n"
                    md_content += f"- **Notebook ID**: {req.notebook_id}\n"
                    md_content += f"- **Source ID**: {source_id}\n"
                    md_content += f"- **Type**: {source_data.get('value', {}).get('source_type', 'unknown')}\n\n"
                    md_content += "---\n\n"
                    md_content += content_text

                    target_path.write_text(md_content, encoding="utf-8")

                    # Create manifest for NLM source
                    content_id = build_content_id("notebooklm", "nlm_source", filename)
                    manifest = ContentManifest(
                        content_id=content_id,
                        source_type="nlm_source",
                        source_platform="notebooklm",
                        creator_id="notebooklm",
                        creator_name="notebooklm",
                        published_at=datetime.utcnow().isoformat(),
                        collected_at=datetime.utcnow().replace(microsecond=0).isoformat(),
                        title=title,
                        raw_path=str(target_path),
                        file_type=_infer_file_type(target_path.suffix),
                        metadata={
                            "nlm_notebook_id": req.notebook_id,
                            "nlm_source_id": source_id,
                            "nlm_notebook_name": req.notebook_id,
                            "source_type": source_data.get("value", {}).get("source_type", "unknown"),
                        },
                        source_url=None,
                        external_source_id=None,
                        dedupe_fingerprint=None,
                        language="zh",
                        market_scope=["US", "HK", "A"],
                    )
                    write_manifest(REPO_ROOT, manifest)

                    downloaded.append(filename)

            except Exception as inner_e:
                print(f"Error fetching source {source_id}: {inner_e}")
                continue
                
        return {
            "status": "ok",
            "sources_scanned": len(sources),
            "downloaded": len(downloaded),
            "files": downloaded
        }
        
    except Exception as e:
        raise FinerError(
            ErrorCode.NLM_EXT_001,
            f"Error fetching NLM data: {e}",
            stage="F0",
            operation="nlm_fetch",
            source_channel="nlm",
            retryable=True,
            cause=e,
        )


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
