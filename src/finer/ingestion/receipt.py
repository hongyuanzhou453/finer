"""Receipt — send processing notifications to the Feishu receipt group.

Sends a summary message to the configured receipt chat after files
have been processed, classified, and archived.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LARK_CLI = "/usr/local/bin/lark-cli"


def _send_markdown(lark_cli: str, chat_id: str, markdown: str) -> bool:
    """Send a markdown message to a Feishu chat."""
    try:
        result = subprocess.run(
            [
                lark_cli, "im", "+messages-send",
                "--chat-id", chat_id,
                "--markdown", markdown,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error("Failed to send receipt: %s", result.stderr)
            return False
        logger.info("Receipt sent to chat %s", chat_id)
        return True
    except Exception as e:
        logger.error("Receipt send error: %s", e)
        return False


def _format_file_entry(
    filename: str,
    creator_id: str,
    source_type: str,
    confidence: float,
    matched_rule: str,
    nlm_synced: bool,
) -> str:
    """Format a single file entry for the receipt."""
    conf_emoji = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.5 else "🔴"
    nlm_badge = " → 📓NLM" if nlm_synced else ""
    return (
        f"  • {conf_emoji} **{filename}**\n"
        f"    └─ `{creator_id}/{source_type}` "
        f"(规则: {matched_rule}, 置信度: {confidence:.0%}){nlm_badge}"
    )


class ReceiptSender:
    """Sends processing receipts to the Feishu receipt group."""

    def __init__(self, receipt_chat_id: str, lark_cli_path: str = DEFAULT_LARK_CLI):
        self.receipt_chat_id = receipt_chat_id
        self.lark_cli_path = lark_cli_path

    def send_sync_receipt(
        self,
        source_chat_name: str,
        processed_files: list[dict[str, Any]],
        errors: list[str] | None = None,
        total_messages: int = 0,
    ) -> bool:
        """Send a summary receipt after a sync operation.
        
        Args:
            source_chat_name: Name of the source Feishu chat.
            processed_files: List of dicts with file processing details.
            errors: Optional list of error messages.
            total_messages: Total messages scanned.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Build markdown message
        lines = [
            f"## 📦 finer 文件同步报告",
            f"**时间**: {now}",
            f"**来源**: {source_chat_name}",
            f"**扫描消息**: {total_messages} 条",
            f"**处理文件**: {len(processed_files)} 个",
            "",
        ]

        if processed_files:
            lines.append("### 📁 文件清单")
            for f in processed_files:
                lines.append(_format_file_entry(
                    filename=f.get("filename", "unknown"),
                    creator_id=f.get("creator_id", "?"),
                    source_type=f.get("source_type") or f.get("content_type", "?"),
                    confidence=f.get("confidence", 0.0),
                    matched_rule=f.get("matched_rule", "?"),
                    nlm_synced=f.get("nlm_synced", False),
                ))
        else:
            lines.append("*无新文件*")

        if errors:
            lines.append("")
            lines.append("### ⚠️ 错误")
            for err in errors:
                lines.append(f"  • {err}")

        lines.append("")
        lines.append("---")
        lines.append("*由 finer 文件管理系统自动生成*")

        markdown = "\n".join(lines)
        return _send_markdown(self.lark_cli_path, self.receipt_chat_id, markdown)

    def send_error_receipt(self, error_message: str) -> bool:
        """Send an error notification to the receipt group."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        markdown = "\n".join([
            "## ❌ finer 同步错误",
            f"**时间**: {now}",
            "",
            "### 错误信息",
            f"```\n{error_message}\n```",
            "",
            "---",
            "*由 finer 文件管理系统自动生成*",
        ])
        return _send_markdown(self.lark_cli_path, self.receipt_chat_id, markdown)
