"""Orchestrator — F0 Feishu intake: poll → classify → archive → canonical F0.

This module ties the ingestion components into a single ``sync_chat()`` call
used by the CLI / scheduler.

F0-only boundary (BK1 / R-12)
-----------------------------
``sync_chat`` is an **F0 intake** path. It produces canonical ``ContentRecord``
+ ``ImportReceipt`` and registers each item in Project Memory. It deliberately
does **not** run Vision/OCR, summary generation, or NotebookLM sync inline —
those were decoupled and now belong to downstream (F1+) stages or a separate
sync job. The archived raw files under ``data/raw/...`` plus the ContentRecords
are the hand-off seam for F1. See ``F1_HANDOFF_SEAM`` below.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from finer.config import load_feishu_config
from finer.ingestion.classifier import ClassificationResult, FileClassifier
from finer.ingestion.feishu_f0_importer import import_feishu_export_all
from finer.ingestion.feishu_poller import (
    DownloadedFile,
    FeishuMessage,
    FeishuPoller,
    SyncState,
)
from finer.ingestion.receipt import ReceiptSender
from finer.manifests import ContentManifest, _infer_file_type, build_content_id, write_manifest
from finer.paths import f0_receipt_path, f0_record_path
from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportReceipt
from finer.utils.time import now_utc

logger = logging.getLogger(__name__)

# Hand-off seam to F1: capabilities that USED to run inline in this F0 path but
# were decoupled per BK1/R-12. An F1 owner should consume the archived raw files
# + ContentRecords and run these as F1 stages, not re-add them here.
F1_HANDOFF_SEAM = (
    "vision_ocr",          # image description / OCR (was VisionDescriptor inline)
    "content_summary",     # overall summary generation (was SummaryGenerator inline)
    "notebooklm_sync",     # push to NotebookLM (was NLMSync inline; now a separate job)
)

# ContentRecord.file_type is a closed literal; classifier source_type is open, so
# the archived attachment's file_type is derived from its extension via
# _infer_file_type, then mapped onto the ContentRecord literal set.
_RECORD_FILE_TYPES = {"chat_log", "image", "pdf", "doc", "audio", "video", "text"}


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
            "Project Memory registration skipped for %s: %s", record.content_id, exc
        )


def _archive_file(
    root: Path,
    file: DownloadedFile,
    classification: ClassificationResult,
) -> Path:
    """Move a file from inbox to the canonical raw archive location."""
    target_dir = (
        root / "data" / "raw"
        / classification.creator_id
        / classification.source_type
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file.local_path.name

    # Avoid overwriting existing files
    if target_path.exists():
        stem = target_path.stem
        suffix = target_path.suffix
        counter = 1
        while target_path.exists():
            target_path = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(file.local_path), str(target_path))
    logger.info("Archived: %s → %s", file.local_path.name, target_path)
    return target_path


def _record_file_type(archived_path: Path) -> str:
    """Map an archived attachment to a ContentRecord file_type literal."""
    inferred = _infer_file_type(archived_path.suffix)
    return inferred if inferred in _RECORD_FILE_TYPES else "text"


def _emit_attachment_f0_record(
    root: Path,
    file: DownloadedFile,
    classification: ClassificationResult,
    archived_path: Path,
) -> ContentRecord:
    """Emit a canonical F0 ContentRecord + ImportReceipt for one attachment.

    Writes both under ``data/F0_intake/feishu/`` via the GATE path helpers and
    registers the record in Project Memory. The attachment's ``source_type`` is
    mapped to the canonical ``feishu_chat`` intake type (attachments arrive on
    the Feishu chat channel); the original classifier label is preserved in
    metadata for downstream routing.
    """
    content_id = build_content_id(
        classification.creator_id,
        classification.source_type,
        file.original_name,
    )
    rel_raw_path = str(archived_path.relative_to(root)) if archived_path.is_absolute() else str(archived_path)
    external_source_id = f"feishu_msg:{file.chat_id}:{file.message_id}:{file.original_name}"
    collected = now_utc()

    record = ContentRecord(
        content_id=content_id,
        source_type="feishu_chat",
        source_platform="feishu",
        creator_id=classification.creator_id,
        creator_name=classification.creator_id,
        published_at=classification.published_at,
        collected_at=collected,
        title=file.original_name,
        raw_path=rel_raw_path,
        file_type=_record_file_type(archived_path),
        metadata={
            "original_filename": file.original_name,
            "extension": archived_path.suffix,
            "registered_via": "feishu-sync",
            "feishu_message_id": file.message_id,
            "feishu_chat_id": file.chat_id,
            "feishu_sender_id": file.sender_id,
            "msg_type": file.msg_type,
            "classified_source_type": classification.source_type,
            "classification_rule": classification.matched_rule,
            "classification_confidence": classification.confidence,
            "context_text": file.context_text,
        },
        external_source_id=external_source_id,
        dedupe_fingerprint=external_source_id,
        language="zh",
        market_scope=["US", "HK", "A"],
    )

    record_path = f0_record_path("feishu", content_id)
    receipt_path = f0_receipt_path("feishu", content_id)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    finished = now_utc()
    receipt = ImportReceipt(
        run_id=f"feishu_{content_id}",
        source_channel="feishu",
        source_kind="feishu_chat_attachment",
        status="completed",
        content_id=content_id,
        external_source_id=external_source_id,
        dedupe_fingerprint=record.dedupe_fingerprint,
        collected_at=collected,
        started_at=finished,
        finished_at=finished,
        raw_paths={"attachment": rel_raw_path},
        record_path=str(record_path),
        records_created=1,
    )
    receipt_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")

    _register_f0_index(record, receipt)
    return record


def _create_manifest(
    root: Path,
    file: DownloadedFile,
    classification: ClassificationResult,
    archived_path: Path,
) -> Path:
    """Create a legacy ContentManifest for an archived file.

    Kept for backward compatibility with downstream code/manifest index that
    still reads ContentManifest; the canonical F0 artifact is the ContentRecord
    emitted by ``_emit_attachment_f0_record``. Vision/summary fields are no
    longer populated here (decoupled per R-12).
    """
    content_id = build_content_id(
        classification.creator_id,
        classification.source_type,
        file.original_name,
    )

    metadata = {
        "original_filename": file.original_name,
        "extension": archived_path.suffix,
        "registered_via": "feishu-sync",
        "feishu_message_id": file.message_id,
        "feishu_chat_id": file.chat_id,
        "feishu_sender_id": file.sender_id,
        "classification_rule": classification.matched_rule,
        "classification_confidence": classification.confidence,
        "context_text": file.context_text,
    }

    manifest = ContentManifest(
        content_id=content_id,
        source_type=classification.source_type,
        source_platform="feishu",
        creator_id=classification.creator_id,
        creator_name=classification.creator_id,
        published_at=classification.published_at.isoformat(),
        collected_at=datetime.utcnow().replace(microsecond=0).isoformat(),
        title=file.original_name,
        raw_path=str(archived_path),
        file_type=_infer_file_type(archived_path.suffix),
        metadata=metadata,
        source_url=None,
        external_source_id=None,
        dedupe_fingerprint=None,
        language="zh",
        market_scope=["US", "HK", "A"],
    )

    manifest_path = write_manifest(root, manifest)
    logger.info("Manifest: %s", manifest_path)
    return manifest_path


def _create_chat_transcript(
    root: Path,
    chat_id: str,
    chat_name: str,
    messages: list[FeishuMessage],
    creator_id: str,
) -> Path | None:
    """Create a Markdown transcript of all text messages in the sync window."""
    # Include text, post, and merge_forward message types
    text_messages = [m for m in messages if m.msg_type in ("text", "post", "merge_forward")]
    if not text_messages:
        return None

    # Sort by time
    text_messages.sort(key=lambda x: x.create_time)

    start_time = text_messages[0].create_time.strftime("%Y%m%d_%H%M")
    end_time = text_messages[-1].create_time.strftime("%Y%m%d_%H%M")

    filename = f"chat_history_{start_time}_to_{end_time}.md"
    target_dir = root / "data" / "raw" / creator_id / "transcripts"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    content = [
        f"# Chat History: {chat_name}\n",
        f"- **Chat ID**: {chat_id}",
        f"- **Creator Segment**: {creator_id}",
        f"- **Time Range**: {text_messages[0].create_time.isoformat()} 至 {text_messages[-1].create_time.isoformat()}\n",
        "---",
    ]

    for msg in text_messages:
        time_str = msg.create_time.strftime("%Y-%m-%d %H:%M:%S")
        # Use content_text (now populated for text and post types)
        msg_content = msg.content_text or msg.content_raw or "(无内容)"
        content.append(f"### [{time_str}] {msg.sender_id} ({msg.msg_type})")
        content.append(f"{msg_content}\n")

    target_path.write_text("\n".join(content), encoding="utf-8")
    logger.info("Chat transcript created: %s (%d messages)", target_path.name, len(text_messages))
    return target_path


def _import_transcript_f0(
    root: Path,
    chat_id: str,
    chat_name: str,
    transcript_path: Path,
    creator_id: str,
) -> list[ContentRecord]:
    """Route a freshly-written chat transcript through the canonical F0 importer.

    Each chat message becomes a canonical ``ContentRecord`` (source_type
    ``feishu_chat``) and is registered in Project Memory. The importer writes a
    per-message ImportReceipt-equivalent record; here we additionally emit an
    ImportReceipt + PM row per produced record so the chat text shows up in the
    Import Console catalog.
    """
    result = import_feishu_export_all(
        source_path=transcript_path,
        chat_id=chat_id,
        chat_name=chat_name,
        creator_id=creator_id or "maodaren",
        data_root=root / "data",
    )
    records: list[ContentRecord] = []
    for item in result.items:
        record = item.content_record
        finished = now_utc()
        receipt = ImportReceipt(
            run_id=f"feishu_{record.content_id}",
            source_channel="feishu",
            source_kind="feishu_chat",
            status="completed",
            content_id=record.content_id,
            external_source_id=record.external_source_id,
            dedupe_fingerprint=record.dedupe_fingerprint,
            collected_at=record.collected_at,
            started_at=finished,
            finished_at=finished,
            raw_sha256={"message_slice": item.raw_slice_sha256},
            raw_paths={"message_slice": str(item.raw_slice_path)},
            record_path=str(item.record_path),
            records_created=1,
        )
        receipt_path = f0_receipt_path("feishu", record.content_id)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
        _register_f0_index(record, receipt)
        records.append(record)
    return records


def sync_chat(
    root: Path,
    chat_config: dict[str, Any],
    full_config: dict[str, Any],
    state: SyncState,
    dry_run: bool = False,
    auto_nlm: bool = True,
) -> dict[str, Any]:
    """Sync a single Feishu chat into F0: poll → transcribe → classify → archive.

    F0-only: produces canonical ContentRecord + ImportReceipt + Project Memory
    rows for chat text and attachments. Vision/OCR, summary, and NotebookLM sync
    are NOT run here (decoupled per R-12); see ``F1_HANDOFF_SEAM``.

    ``auto_nlm`` is retained for signature compatibility but is now a no-op in
    the F0 path (NotebookLM sync is a separate downstream job).
    """
    chat_id = chat_config["chat_id"]
    chat_name = chat_config["name"]
    default_creator = chat_config.get("default_creator", "")

    feishu_cfg = full_config.get("feishu", {})
    inbox_dir = root / feishu_cfg.get("inbox_dir", "data/inbox")
    receipt_chat_id = feishu_cfg.get("receipt_chat_id", "")

    if auto_nlm:
        logger.debug(
            "auto_nlm is a no-op in the F0 path; NotebookLM sync is decoupled (R-12)."
        )

    # Initialize components
    lark_cli_path = feishu_cfg.get("lark_cli_path", "/opt/homebrew/bin/lark-cli")
    poller = FeishuPoller(inbox_dir, lark_cli_path=lark_cli_path)
    classifier = FileClassifier(full_config)
    receipt = ReceiptSender(receipt_chat_id, lark_cli_path=lark_cli_path) if receipt_chat_id else None

    # Get last sync timestamp
    since = state.get_last_sync(chat_id)
    logger.info(
        "Syncing chat '%s' (%s) since %s",
        chat_name, chat_id, since or "beginning",
    )

    # ── Step 1: Pull messages ──
    messages = poller.poll_chat(chat_id, since=since)
    if not messages:
        logger.info("No new messages in '%s'", chat_name)
        return {
            "status": "ok",
            "chat_name": chat_name,
            "messages_scanned": 0,
            "files_processed": 0,
            "records_created": 0,
            "f1_handoff_seam": list(F1_HANDOFF_SEAM),
        }

    # ── Step 2: Transcribe chat history → canonical F0 ContentRecords ──
    records_created = 0
    chat_transcript_path = _create_chat_transcript(
        root, chat_id, chat_name, messages, default_creator
    )
    if chat_transcript_path:
        try:
            transcript_records = _import_transcript_f0(
                root, chat_id, chat_name, chat_transcript_path, default_creator
            )
            records_created += len(transcript_records)
        except Exception as te:  # pragma: no cover - parse robustness
            logger.error("Transcript F0 import failed for '%s': %s", chat_name, te)

    # ── Step 3: Download attachments ──
    if dry_run:
        attachment_msgs = [m for m in messages if m.msg_type in ("file", "image")]
        return {
            "status": "dry_run",
            "chat_name": chat_name,
            "messages_scanned": len(messages),
            "attachment_messages": len(attachment_msgs),
            "would_download": [
                {"message_id": m.message_id, "type": m.msg_type, "keys": m.file_keys}
                for m in attachment_msgs
            ],
            "f1_handoff_seam": list(F1_HANDOFF_SEAM),
        }

    downloads = poller.download_all_attachments(messages)
    logger.info("Downloaded %d files from '%s'", len(downloads), chat_name)

    # ── Step 4: Sweep inbox (collect files already in inbox) ──
    # This picks up files from failed previous runs or manual placement
    existing_files = []
    for p in inbox_dir.iterdir():
        if p.is_file() and not p.name.startswith("."):
            # Check if this file was already in 'downloads'
            if not any(d.local_path == p for d in downloads):
                existing_files.append(DownloadedFile(
                    local_path=p,
                    original_name=p.name,
                    message_id="manual",
                    chat_id=chat_id,
                    sender_id="manual",
                    sent_at=datetime.fromtimestamp(p.stat().st_mtime).astimezone(),
                    msg_type="file",
                    context_text="",
                ))

    all_files_to_process = downloads + existing_files
    if existing_files:
        logger.info("Found %d existing files in inbox to process", len(existing_files))

    # ── Step 5: Classify + Archive + canonical F0 (no Vision/Summary/NLM) ──
    processed_files: list[dict[str, Any]] = []
    errors: list[str] = []

    for file in all_files_to_process:
        try:
            # Classify
            classification = classifier.classify(
                filename=file.original_name,
                context_text=file.context_text,
                sent_at=file.sent_at,
                chat_name=chat_name,
                chat_default_creator=default_creator,
            )
            logger.info(
                "Classified %s → %s/%s (%.0f%%, %s)",
                file.original_name,
                classification.creator_id,
                classification.source_type,
                classification.confidence * 100,
                classification.matched_rule,
            )

            # Archive (F0 raw payload)
            archived_path = _archive_file(root, file, classification)

            # Canonical F0 ContentRecord + ImportReceipt + PM row
            record = _emit_attachment_f0_record(root, file, classification, archived_path)
            records_created += 1

            # Legacy ContentManifest (backward-compat for downstream manifest index)
            _create_manifest(root, file, classification, archived_path)

            processed_files.append({
                "filename": file.original_name,
                "content_id": record.content_id,
                "creator_id": classification.creator_id,
                "source_type": classification.source_type,
                "confidence": classification.confidence,
                "matched_rule": classification.matched_rule,
                "archived_path": str(archived_path),
            })

        except Exception as e:
            error_msg = f"Error processing {file.original_name}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    # ── Step 6: Update sync state ──
    if messages:
        latest_time = max(m.create_time for m in messages)
        state.update_last_sync(chat_id, latest_time)

    # ── Step 7: Send Feishu delivery receipt (chat-side acknowledgement) ──
    if receipt and (processed_files or errors):
        receipt.send_sync_receipt(
            source_chat_name=chat_name,
            processed_files=processed_files,
            errors=errors if errors else None,
            total_messages=len(messages),
        )

    return {
        "status": "ok",
        "chat_name": chat_name,
        "messages_scanned": len(messages),
        "files_processed": len(processed_files),
        "records_created": records_created,
        "errors": errors,
        "files": processed_files,
        "f1_handoff_seam": list(F1_HANDOFF_SEAM),
    }


def sync_all_chats(
    root: Path,
    dry_run: bool = False,
    auto_nlm: bool = True,
) -> dict[str, Any]:
    """Sync all configured Feishu chats."""
    config = load_feishu_config(root)
    feishu_cfg = config.get("feishu", {})

    state_file = root / feishu_cfg.get("state_file", "data/.feishu_sync_state.json")
    state = SyncState(state_file)

    results = []
    for chat_cfg in feishu_cfg.get("watched_chats", []):
        try:
            result = sync_chat(
                root=root,
                chat_config=chat_cfg,
                full_config=config,
                state=state,
                dry_run=dry_run,
                auto_nlm=auto_nlm,
            )
            results.append(result)
        except Exception as e:
            error_msg = f"Failed to sync chat {chat_cfg.get('name', '?')}: {e}"
            logger.error(error_msg)
            results.append({"status": "error", "error": error_msg})

            # Send error receipt
            receipt_chat_id = feishu_cfg.get("receipt_chat_id", "")
            if receipt_chat_id:
                ReceiptSender(receipt_chat_id).send_error_receipt(error_msg)

    return {
        "status": "ok",
        "chats_synced": len(results),
        "results": results,
    }
