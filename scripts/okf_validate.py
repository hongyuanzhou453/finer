#!/usr/bin/env python3
"""OKF knowledge bundle validator.

Phase 2 of docs/specs/2026-06-26-okf-knowledge-bundle.md.

校验 knowledge/okf/ 下的 concept 文件：
  - frontmatter 契约：type ∈ 起步 4 类；f_stage 合法；canonical_source / owner_paths 指向真实路径
  - 链接完整性：正文相对链接与 frontmatter 引用的目标存在
  - legacy 命名禁令：正文不得复活 L0-L8 / V0-V6（meta/技术栈语境豁免）
  - freshness：canonical_source 的 git 提交时间晚于 OKF timestamp 时告警（B3 下沉前置门）

退出码：发现 error 返回 1，仅 warning 返回 0（可进 pre-commit / CI）。
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OKF_ROOT = REPO_ROOT / "knowledge" / "okf"

VALID_TYPES = {"Finer Stage", "Finer Schema", "Finer Known Issue", "Finer Playbook"}
VALID_FSTAGES = {"F0", "F1", "F1.5", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F+"}
RESERVED_FILES = {"index.md", "log.md"}

LEGACY_TOKEN = re.compile(r"\b[LV]\d\b")
LEGACY_EXEMPT = re.compile(r"禁止|deprecated|legacy|废弃|旧|不得|Pydantic|pydantic|约定")
MD_LINK = re.compile(r"\]\(([^)]+)\)")


def parse_frontmatter(text: str) -> dict[str, object]:
    """极简 YAML frontmatter 解析：顶层 scalar 与 `- ` 列表，够覆盖 OKF 契约字段。"""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}
    fields: dict[str, object] = {}
    key: str | None = None
    for line in match.group(1).split("\n"):
        if re.match(r"^\s+-\s+", line) and key is not None:
            bucket = fields.setdefault(key, [])
            if isinstance(bucket, list):
                bucket.append(line.strip()[1:].strip())
            continue
        field = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if field:
            key = field.group(1)
            value = field.group(2).strip()
            fields[key] = value if value else []
    return fields


def git_committed_at(path: Path) -> datetime | None:
    """返回文件最近一次提交时间（aware datetime）；未提交或无 git 时返回 None。"""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    stamp = result.stdout.strip()
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def _is_legacy_stage_token(token: str) -> bool:
    return (token[0] == "L" and token[1] in "012345678") or (
        token[0] == "V" and token[1] in "0123456"
    )


def check() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    md_files = sorted(OKF_ROOT.rglob("*.md"))
    if not md_files:
        return [f"未找到任何 OKF 文件：{OKF_ROOT}"], warnings

    for md in md_files:
        rel = md.relative_to(REPO_ROOT)
        text = md.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        reserved = md.name in RESERVED_FILES

        if not reserved:
            ctype = fm.get("type")
            if ctype not in VALID_TYPES:
                errors.append(f"{rel}: type 缺失或非法（{ctype!r}），须 ∈ {sorted(VALID_TYPES)}")
            fstage = fm.get("f_stage")
            if fstage is not None and not isinstance(fstage, list) and fstage not in VALID_FSTAGES:
                errors.append(f"{rel}: f_stage 非法（{fstage!r}）")
            canonical = fm.get("canonical_source")
            if not canonical:
                errors.append(f"{rel}: 缺 canonical_source")
            elif canonical != "self" and not (REPO_ROOT / str(canonical)).exists():
                errors.append(f"{rel}: canonical_source 指向不存在的路径：{canonical}")
            owner_paths = fm.get("owner_paths")
            if isinstance(owner_paths, list):
                for path in owner_paths:
                    if not (REPO_ROOT / str(path)).exists():
                        errors.append(f"{rel}: owner_path 不存在：{path}")

        for lineno, line in enumerate(text.split("\n"), 1):
            if LEGACY_EXEMPT.search(line):
                continue
            hit = LEGACY_TOKEN.search(line)
            if hit and _is_legacy_stage_token(hit.group(0)):
                errors.append(
                    f"{rel}:{lineno}: 疑似 legacy 命名 {hit.group(0)}（禁止 L0-L8 / V0-V6）"
                )

        for target in MD_LINK.findall(text):
            cleaned = target.split("#")[0]
            if not cleaned or cleaned.startswith(("http://", "https://", "#")):
                continue
            if not (md.parent / cleaned).resolve().exists():
                errors.append(f"{rel}: 坏链接 → {target}")

        if not reserved:
            canonical = fm.get("canonical_source")
            timestamp = fm.get("timestamp")
            if (
                canonical
                and canonical != "self"
                and isinstance(timestamp, str)
                and timestamp
                and (REPO_ROOT / str(canonical)).exists()
            ):
                source_at = git_committed_at(REPO_ROOT / str(canonical))
                try:
                    okf_at: datetime | None = datetime.fromisoformat(timestamp)
                except ValueError:
                    okf_at = None
                if source_at and okf_at and source_at > okf_at:
                    warnings.append(
                        f"{rel}: canonical_source {canonical} 提交时间晚于 OKF timestamp，可能过期"
                    )

    return errors, warnings


def main() -> int:
    errors, warnings = check()
    for warning in warnings:
        print(f"WARN  {warning}")
    for error in errors:
        print(f"ERROR {error}")
    total = len(sorted(OKF_ROOT.rglob("*.md")))
    print(f"--- OKF validate: {total} files, {len(errors)} errors, {len(warnings)} warnings")
    if errors:
        print("FAIL")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
