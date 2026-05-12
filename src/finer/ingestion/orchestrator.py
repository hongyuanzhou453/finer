"""Orchestrator — end-to-end pipeline: Feishu → Classify → Archive → NLM → Receipt.

This module ties together all ingestion components into a single
`sync_chat()` call that can be used by the CLI or a scheduler.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from finer.config import load_feishu_config
from finer.ingestion.classifier import ClassificationResult, FileClassifier
from finer.ingestion.feishu_poller import (
    DownloadedFile,
    FeishuMessage,
    FeishuPoller,
    SyncState,
)
from finer.ingestion.nlm_sync import NLMSync
from finer.ingestion.receipt import ReceiptSender
from finer.ingestion.vision_utils import VisionDescriptor, get_vision_transcript_path
from finer.manifests import ContentManifest, _infer_file_type, build_content_id, write_manifest
from finer.services.summary_generator import SummaryGenerator, init_summary_cache

logger = logging.getLogger(__name__)


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


def _create_manifest(
    root: Path,
    file: DownloadedFile,
    classification: ClassificationResult,
    archived_path: Path,
    vision_transcript_path: Path | None = None,
    summary: str | None = None,
    extracted_timestamp: str | None = None,
) -> Path:
    """Create a content manifest for an archived file."""
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
    if vision_transcript_path:
        metadata["vision_transcript_path"] = str(vision_transcript_path)
    if summary:
        metadata["summary"] = summary
    if extracted_timestamp:
        metadata["extracted_timestamp"] = extracted_timestamp

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


def _create_chat_transcript_manifest(
    root: Path,
    chat_id: str,
    chat_name: str,
    transcript_path: Path,
    creator_id: str,
    message_count: int,
) -> Path:
    """Create a content manifest for a chat transcript file."""
    content_id = build_content_id(creator_id, "chat_transcript", transcript_path.name)

    metadata = {
        "original_filename": transcript_path.name,
        "extension": ".md",
        "registered_via": "feishu-sync",
        "feishu_chat_id": chat_id,
        "chat_name": chat_name,
        "message_count": message_count,
        "source_type": "chat_transcript",
    }

    manifest = ContentManifest(
        content_id=content_id,
        source_type="chat_transcript",
        source_platform="feishu",
        creator_id=creator_id,
        creator_name=creator_id,
        published_at=datetime.now().isoformat(),
        collected_at=datetime.utcnow().replace(microsecond=0).isoformat(),
        title=transcript_path.name,
        raw_path=str(transcript_path),
        file_type=_infer_file_type(transcript_path.suffix),
        metadata=metadata,
        source_url=None,
        external_source_id=None,
        dedupe_fingerprint=None,
        language="zh",
        market_scope=["US", "HK", "A"],
    )

    manifest_path = write_manifest(root, manifest)
    logger.info("Chat transcript manifest: %s", manifest_path)
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


def sync_chat(
    root: Path,
    chat_config: dict[str, Any],
    full_config: dict[str, Any],
    state: SyncState,
    dry_run: bool = False,
    auto_nlm: bool = True,
) -> dict[str, Any]:
    """Sync a single Feishu chat: pull → transcribe → classify → archive → NLM → receipt."""
    chat_id = chat_config["chat_id"]
    chat_name = chat_config["name"]
    notebook_id = chat_config.get("notebook_id", "")
    default_creator = chat_config.get("default_creator", "")
    
    feishu_cfg = full_config.get("feishu", {})
    vision_cfg = full_config.get("vision", {})
    summary_cfg = full_config.get("summary", {})
    inbox_dir = root / feishu_cfg.get("inbox_dir", "data/inbox")
    receipt_chat_id = feishu_cfg.get("receipt_chat_id", "")

    # Initialize components
    lark_cli_path = feishu_cfg.get("lark_cli_path", "/opt/homebrew/bin/lark-cli")
    poller = FeishuPoller(inbox_dir, lark_cli_path=lark_cli_path)
    classifier = FileClassifier(full_config)
    nlm_sync = NLMSync(full_config) if auto_nlm else None
    receipt = ReceiptSender(receipt_chat_id, lark_cli_path=lark_cli_path) if receipt_chat_id else None

    vision_desc = None
    if vision_cfg.get("enabled"):
        vision_desc = VisionDescriptor(model=vision_cfg.get("model", "mimo-v2.5"))

    # Initialize summary generator
    summary_gen = None
    if summary_cfg.get("enabled", True):  # Default enabled
        summary_gen = SummaryGenerator(
            root=root,
            model=summary_cfg.get("model", "qwen-plus"),
            use_cache=summary_cfg.get("use_cache", True),
            financial_mode=summary_cfg.get("financial_mode", True),
        )

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
        }

    # ── Step 2: Transcribe Chat History (Ingest text content) ──
    chat_transcript_path = _create_chat_transcript(
        root, chat_id, chat_name, messages, default_creator
    )
    if chat_transcript_path:
        # Create manifest for chat transcript
        _create_chat_transcript_manifest(
            root, chat_id, chat_name, chat_transcript_path,
            default_creator, len([m for m in messages if m.msg_type in ("text", "post", "merge_forward")])
        )
        if auto_nlm and notebook_id:
            if nlm_sync and nlm_sync.should_sync(chat_transcript_path):
                logger.info("Syncing chat transcript to NotebookLM...")
                nlm_sync.sync_file(chat_transcript_path, notebook_id)

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
        }

    downloads = poller.download_all_attachments(messages)
    logger.info("Downloaded %d files from '%s'", len(downloads), chat_name)

    # ── Step 4: Sweep Inbox (collect files already in inbox) ──
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

    # ── Step 5: Classify + Archive + NLM ──
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

            # Archive
            archived_path = _archive_file(root, file, classification)
            
            # Vision Processing for images
            vision_transcript_path = None
            if vision_desc and file.msg_type == "image":
                try:
                    description = vision_desc.describe_image(archived_path)
                    vision_transcript_path = get_vision_transcript_path(
                        root, archived_path, classification.creator_id
                    )
                    vision_transcript_path.write_text(
                        f"# Vision Analysis: {archived_path.name}\n\n"
                        f"**Source**: Feishu ({chat_name})\n"
                        f"**Creator**: {classification.creator_id}\n\n"
                        f"## Description\n\n{description}\n",
                        encoding="utf-8"
                    )
                    logger.info("Vision transcript created: %s", vision_transcript_path)
                except Exception as ve:
                    logger.error("Vision processing failed for %s: %s", archived_path.name, ve)

            # Summary generation
            summary_text = None
            extracted_ts = None
            if summary_gen:
                try:
                    # Determine if this is an image
                    is_image = file.msg_type == "image"
                    # Get content from vision transcript if available, otherwise read file
                    content_for_summary = None
                    if vision_transcript_path and vision_transcript_path.exists():
                        content_for_summary = vision_transcript_path.read_text(encoding="utf-8")

                    summary_result = summary_gen.generate_summary(
                        file_path=archived_path,
                        content=content_for_summary,
                        is_image=is_image,
                    )
                    if summary_result.get("summary"):
                        summary_text = summary_result["summary"]
                        extracted_ts = summary_result.get("extracted_timestamp")
                        logger.info(
                            "Generated summary for %s (cached=%s)",
                            archived_path.name,
                            summary_result.get("cached", False),
                        )
                except Exception as se:
                    logger.error("Summary generation failed for %s: %s", archived_path.name, se)

            # Create manifest
            _create_manifest(
                root, file, classification, archived_path, vision_transcript_path,
                summary=summary_text, extracted_timestamp=extracted_ts
            )

            # NLM sync
            nlm_synced = False
            if nlm_sync and notebook_id:
                # If it's an image, sync the transcript; otherwise sync the file
                target_to_sync = archived_path
                if vision_transcript_path and vision_transcript_path.exists():
                    target_to_sync = vision_transcript_path
                
                if nlm_sync.should_sync(target_to_sync):
                    sync_result = nlm_sync.sync_file(target_to_sync, notebook_id)
                    nlm_synced = sync_result.success
                    if not sync_result.success:
                        errors.append(
                            f"NLM sync failed for {target_to_sync.name}: {sync_result.error}"
                        )

            processed_files.append({
                "filename": file.original_name,
                "creator_id": classification.creator_id,
                "source_type": classification.source_type,
                "confidence": classification.confidence,
                "matched_rule": classification.matched_rule,
                "archived_path": str(archived_path),
                "nlm_synced": nlm_synced,
                "has_vision": vision_transcript_path is not None,
                "has_summary": summary_text is not None,
                "extracted_timestamp": extracted_ts,
            })

        except Exception as e:
            error_msg = f"Error processing {file.original_name}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    # ── Step 4: Update sync state ──
    if messages:
        latest_time = max(m.create_time for m in messages)
        state.update_last_sync(chat_id, latest_time)

    # ── Step 5: Send receipt ──
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
        "errors": errors,
        "files": processed_files,
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
