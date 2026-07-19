"""Broker research F0 intake — register foreign-broker research PDFs as ContentRecords.

Reads meta JSONL lines (one research report per line, produced by the external
研报仓 classifier) and emits canonical F0 artifacts:

    raw archive   -> data/raw/broker/{content_id}.pdf   (symlink by default)
    ContentRecord -> data/F0_intake/broker/{content_id}.json
    ImportReceipt -> data/F0_intake/broker/{content_id}.receipt.json

Strictly F0-only: it hashes readable file bytes for identity/dedupe and archives
them. It never opens PDF content, never OCRs, never standardizes (that is F1's
job via the standardization router).

Hard rules encoded here (spec: docs/specs/2026-07-15-broker-research-source-integration.md §3 A1):

* ``published_at`` comes ONLY from the meta ``date`` field. A missing or invalid
  date skips the item with a failure receipt — there is NO fallback to file
  mtime (that would fabricate a publication date).
* ``raw_path`` is stored relative to data_root (driver contract,
  pipeline/driver.py:225-230) and must live under ``raw/broker/`` — never under
  ``raw/local/``, which the driver silently excludes for PDFs (risk R1,
  driver.py:282).
* ``content_id = "broker_" + sha256(file bytes)[:24]`` so byte-identical
  duplicates collapse to one record.
* The source volume (e.g. ``/Volumes/NAMEZY``) is recorded on every receipt;
  an unmounted volume produces an explicit, retryable error (risk R8).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from finer.paths import DATA_ROOT
from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportErrorEnvelope, ImportReceipt

if TYPE_CHECKING:  # pragma: no cover - type hint only; keeps F0 planning import-light
    from finer.ingestion.f0_index_writer import F0IndexWriter

BEIJING_TZ = timezone(timedelta(hours=8))

BROKER_PLATFORM = "broker"
BROKER_SOURCE_KIND = "broker_research_pdf"

# Meta JSONL fields carried verbatim into ContentRecord.metadata["meta"].
_META_PASSTHROUGH = (
    "filename",
    "broker",
    "broker_raw",
    "date",
    "topic",
    "company_name",
    "stock_code",
    "industry_l1",
    "industry_l2",
    "is_industry_report",
    "rating",
    "rating_action",
)

_ARCHIVE_MODES = ("symlink", "copy")


# ---------------------------------------------------------------------------
# Data holders
# ---------------------------------------------------------------------------


@dataclass
class BrokerIntakeItem:
    """One meta JSONL line and the F0 outcome planned/executed for it."""

    line_no: int
    meta: dict[str, Any]
    request_id: str
    status: str  # "new" | "duplicate" | "exists" | "failed"
    source_path: Optional[Path] = None
    content_hash: Optional[str] = None
    content_id: Optional[str] = None
    published_at: Optional[datetime] = None
    storage_volume: Optional[str] = None
    raw_path_rel: Optional[str] = None
    archive_path: Optional[Path] = None
    record_path: Optional[Path] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False
    fix_hint: Optional[str] = None
    register_error: Optional[str] = None  # F0-index registration failure (best-effort)


@dataclass
class BrokerIntakeResult:
    """Aggregate outcome of one intake run (dry-run or execute)."""

    run_id: str = ""
    dry_run: bool = True
    scanned: int = 0
    new: int = 0
    duplicates: int = 0
    existing: int = 0
    failed: int = 0
    written_records: int = 0
    written_receipts: int = 0
    registered: int = 0        # records registered into PM stage_status (F0 index)
    register_failed: int = 0   # best-effort registration failures (record still on disk)
    items: list[BrokerIntakeItem] = field(default_factory=list)
    receipts: list[ImportReceipt] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """SHA-256 of a file's bytes, streamed in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_meta_date(value: Any) -> Optional[datetime]:
    """Strictly parse the meta ``date`` field (YYYY-MM-DD, Beijing time).

    Returns None for anything missing/blank/unparseable. Callers MUST NOT
    substitute file mtime — a fabricated publish date poisons F7/F8.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None
    return parsed.replace(tzinfo=BEIJING_TZ)


def storage_volume_of(path: Path) -> str:
    """Nearest mount point containing ``path`` (e.g. '/Volumes/NAMEZY').

    Walks up until ``os.path.ismount``; nonexistent paths deterministically
    resolve to the filesystem root.
    """
    probe = path if path.is_absolute() else Path(os.path.abspath(path))
    while not os.path.ismount(probe):
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    return str(probe)


def _expected_volume_root(path: Path) -> Optional[Path]:
    """For ``/Volumes/<name>/...`` paths, the volume root that must be mounted."""
    parts = path.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "Volumes":
        return Path(parts[0], parts[1], parts[2])
    return None


def _new_run_id() -> str:
    return f"broker_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _error_key(item: BrokerIntakeItem, meta_jsonl: Path) -> str:
    """Stable receipt key for a failed item that never got a content_id."""
    filepath = item.meta.get("filepath")
    seed = str(filepath) if filepath else f"{meta_jsonl}:{item.line_no}"
    return f"broker_err_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def _fail(item: BrokerIntakeItem, code: str, message: str, *, retryable: bool, fix_hint: str) -> BrokerIntakeItem:
    item.status = "failed"
    item.error_code = code
    item.error_message = message
    item.retryable = retryable
    item.fix_hint = fix_hint
    return item


def plan_item(
    meta: dict[str, Any],
    line_no: int,
    data_root: Path,
    seen_hashes: set[str],
) -> BrokerIntakeItem:
    """Validate one meta line and compute the F0 artifacts it would produce.

    Read-only: hashes source bytes but writes nothing.
    """
    item = BrokerIntakeItem(
        line_no=line_no,
        meta=meta,
        request_id=uuid.uuid4().hex[:16],
        status="new",
    )

    filepath = meta.get("filepath")
    if not isinstance(filepath, str) or not filepath.strip():
        return _fail(
            item,
            "F0_BROKER_META_INVALID",
            f"meta line {line_no} has no filepath",
            retryable=False,
            fix_hint="修复 meta JSONL 该行的 filepath 字段后重跑",
        )
    source_path = Path(filepath)
    item.source_path = source_path
    item.storage_volume = storage_volume_of(source_path)

    # published_at: meta date ONLY — never file mtime (spec §3 A1).
    raw_date = meta.get("date")
    published_at = parse_meta_date(raw_date)
    if published_at is None:
        code = "F0_BROKER_DATE_MISSING" if not (isinstance(raw_date, str) and raw_date.strip()) else "F0_BROKER_DATE_INVALID"
        return _fail(
            item,
            code,
            f"meta line {line_no} date={raw_date!r} is missing or not YYYY-MM-DD",
            retryable=False,
            fix_hint=(
                "补齐 meta JSONL 该行的 date 字段（YYYY-MM-DD）后重跑；"
                "禁止回退到文件 mtime（等于伪造发布日）"
            ),
        )
    item.published_at = published_at

    if not source_path.exists():
        volume_root = _expected_volume_root(source_path)
        if volume_root is not None and not volume_root.exists():
            return _fail(
                item,
                "F0_BROKER_VOLUME_MISSING",
                f"storage volume {volume_root} is not mounted (source: {source_path})",
                retryable=True,
                fix_hint=f"挂载外置盘 {volume_root} 后重跑",
            )
        return _fail(
            item,
            "F0_BROKER_FILE_MISSING",
            f"source file not found: {source_path}",
            retryable=False,
            fix_hint="核对 meta JSONL 的 filepath 是否已被移动或删除",
        )

    try:
        content_hash = sha256_file(source_path)
    except OSError as exc:
        return _fail(
            item,
            "F0_BROKER_READ_ERROR",
            f"cannot read {source_path}: {type(exc).__name__}: {exc}",
            retryable=True,
            fix_hint="检查文件权限与外置盘连接后重跑",
        )

    item.content_hash = content_hash
    item.content_id = f"broker_{content_hash[:24]}"
    # Relative to data_root (driver contract); MUST live under raw/broker/,
    # never raw/local/ (driver silently drops PDFs under /raw/local/ — R1).
    item.raw_path_rel = f"raw/{BROKER_PLATFORM}/{item.content_id}.pdf"
    item.archive_path = data_root / item.raw_path_rel
    item.record_path = data_root / "F0_intake" / BROKER_PLATFORM / f"{item.content_id}.json"

    if content_hash in seen_hashes:
        item.status = "duplicate"
    elif item.record_path.exists():
        item.status = "exists"
        seen_hashes.add(content_hash)
    else:
        item.status = "new"
        seen_hashes.add(content_hash)
    return item


# ---------------------------------------------------------------------------
# Record / receipt builders
# ---------------------------------------------------------------------------


def build_record(item: BrokerIntakeItem, collected_at: datetime, archive_mode: str) -> ContentRecord:
    """Construct the canonical ContentRecord for one planned broker item."""
    meta = item.meta
    broker = (meta.get("broker") or meta.get("broker_raw") or "").strip() or None
    assert item.content_id and item.content_hash and item.raw_path_rel and item.source_path
    return ContentRecord(
        content_id=item.content_id,
        source_type="research_report",
        source_platform=BROKER_PLATFORM,
        creator_id=broker,
        creator_name=broker,
        published_at=item.published_at,
        collected_at=collected_at,
        title=meta.get("filename") or item.source_path.name,
        raw_path=item.raw_path_rel,
        file_type="pdf",
        metadata={
            "registered_via": "broker_research_intake",
            "content_sha256": item.content_hash,
            "published_at_source": "meta_date",
            "archive_mode": archive_mode,
            "source_filepath": str(item.source_path),
            "storage_volume": item.storage_volume,
            "meta": {k: meta.get(k) for k in _META_PASSTHROUGH},
        },
        external_source_id=f"broker_raw:{item.content_hash}",
        dedupe_fingerprint=item.content_hash,
        language="zh",
    )


def build_receipt(
    item: BrokerIntakeItem,
    *,
    run_id: str,
    archive_mode: str,
    collected_at: datetime,
    started_at: datetime,
) -> ImportReceipt:
    """Build the canonical ImportReceipt for one item (any status)."""
    finished = datetime.now(timezone.utc)
    raw_paths: dict[str, str] = {}
    if item.raw_path_rel:
        raw_paths["pdf"] = item.raw_path_rel
    if item.source_path is not None:
        raw_paths["source"] = str(item.source_path)
    if item.storage_volume:
        # ImportReceipt has no dedicated field; the volume rides in raw_paths
        # so the Import Console can surface "which disk must be mounted" (R8).
        raw_paths["storage_volume"] = item.storage_volume
    raw_paths["archive_mode"] = archive_mode

    if item.status == "failed":
        status = "failed"
        error: Optional[ImportErrorEnvelope] = ImportErrorEnvelope(
            code=item.error_code or "F0_BROKER_UNKNOWN",
            message=item.error_message or "unknown broker intake failure",
            request_id=item.request_id,
            stage="F0",
            operation="broker_research_intake",
            retryable=item.retryable,
            fix_hint=item.fix_hint,
            source_channel=BROKER_PLATFORM,
        )
    else:
        status = "completed" if item.status == "new" else "skipped"
        error = None

    return ImportReceipt(
        run_id=run_id,
        request_id=item.request_id,
        source_channel=BROKER_PLATFORM,
        source_kind=BROKER_SOURCE_KIND,
        status=status,
        content_id=item.content_id,
        external_source_id=f"broker_raw:{item.content_hash}" if item.content_hash else None,
        dedupe_fingerprint=item.content_hash,
        collected_at=collected_at,
        started_at=started_at,
        finished_at=finished,
        raw_sha256={"pdf": item.content_hash} if item.content_hash else {},
        raw_paths=raw_paths,
        record_path=str(item.record_path) if item.record_path else None,
        records_created=1 if item.status == "new" else 0,
        records_skipped=1 if item.status in ("duplicate", "exists") else 0,
        error=error,
    )


# ---------------------------------------------------------------------------
# Archive + persist
# ---------------------------------------------------------------------------


def _archive_raw(item: BrokerIntakeItem, mode: str) -> None:
    """Land the raw PDF under data/raw/broker/ (symlink default, copy optional).

    The archive filename IS the content hash, so an already-present path is
    byte-identical by construction — never deleted, never overwritten.
    """
    assert item.archive_path is not None and item.source_path is not None
    archive_path = item.archive_path
    if archive_path.is_symlink() or archive_path.exists():
        return
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "symlink":
        os.symlink(item.source_path.resolve(), archive_path)
    else:
        shutil.copyfile(item.source_path, archive_path)


def _receipt_write_path(f0_dir: Path, key: str, run_id: str) -> Path:
    """Canonical receipt path; never clobbers an earlier run's receipt."""
    primary = f0_dir / f"{key}.receipt.json"
    if not primary.exists():
        return primary
    return f0_dir / f"{key}.receipt.{run_id}.json"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def run_intake(
    meta_jsonl: Path,
    data_root: Path,
    *,
    limit: Optional[int] = None,
    execute: bool = False,
    mode: str = "symlink",
    collected_at: Optional[datetime] = None,
    index_writer: "Optional[F0IndexWriter]" = None,
) -> BrokerIntakeResult:
    """Plan (and with ``execute=True`` persist) F0 intake for meta JSONL lines.

    Dry-run (default) reads meta + source bytes only and writes NOTHING.
    Execute archives raw PDFs, writes ContentRecords and ImportReceipts under
    ``data_root``. Records/receipts are validated (constructed) in both modes
    so schema problems surface before any disk write.

    When ``index_writer`` is supplied (and ``execute`` is True), each newly
    written ContentRecord is also registered into Project Memory stage_status /
    asset_index via ``F0IndexWriter.record_imported`` — the same F0-index path
    the other channels use. Registration is **opt-in** (default off) so library
    callers and unit tests never touch the live project DB; the CLI injects a
    writer bound to the real DB. A registration failure is best-effort: the
    record file on disk stays the F0 truth and the backfill script can
    re-register idempotently.
    """
    if mode not in _ARCHIVE_MODES:
        raise ValueError(f"mode must be one of {_ARCHIVE_MODES}, got {mode!r}")

    run_id = _new_run_id()
    started_at = datetime.now(timezone.utc)
    collected = collected_at or started_at
    result = BrokerIntakeResult(run_id=run_id, dry_run=not execute)
    seen_hashes: set[str] = set()
    f0_dir = data_root / "F0_intake" / BROKER_PLATFORM

    with meta_jsonl.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if limit is not None and result.scanned >= limit:
                break
            stripped = line.strip()
            if not stripped:
                continue
            result.scanned += 1

            try:
                meta = json.loads(stripped)
                if not isinstance(meta, dict):
                    raise ValueError("meta line is not a JSON object")
            except ValueError as exc:
                item = _fail(
                    BrokerIntakeItem(
                        line_no=line_no,
                        meta={},
                        request_id=uuid.uuid4().hex[:16],
                        status="failed",
                    ),
                    "F0_BROKER_META_INVALID",
                    f"meta line {line_no} is not valid JSON: {exc}",
                    retryable=False,
                    fix_hint="修复 meta JSONL 该行的 JSON 语法后重跑",
                )
            else:
                item = plan_item(meta, line_no, data_root, seen_hashes)

            result.items.append(item)
            if item.status == "new":
                result.new += 1
            elif item.status == "duplicate":
                result.duplicates += 1
            elif item.status == "exists":
                result.existing += 1
            else:
                result.failed += 1

            receipt = build_receipt(
                item,
                run_id=run_id,
                archive_mode=mode,
                collected_at=collected,
                started_at=started_at,
            )
            result.receipts.append(receipt)

            if not execute:
                continue

            if item.status == "new":
                record = build_record(item, collected, mode)
                _archive_raw(item, mode)
                assert item.record_path is not None
                item.record_path.parent.mkdir(parents=True, exist_ok=True)
                item.record_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
                result.written_records += 1

                # F0-index registration (opt-in; record file is already durable
                # above, so the write-atomicity guard passes). Best-effort: never
                # fail the intake on an index hiccup.
                if index_writer is not None:
                    try:
                        index_writer.record_imported(record, receipt)
                        result.registered += 1
                    except Exception as exc:  # noqa: BLE001 - PM index is a hot projection
                        result.register_failed += 1
                        item.register_error = f"{type(exc).__name__}: {exc}"

            receipt_key = item.content_id or _error_key(item, meta_jsonl)
            f0_dir.mkdir(parents=True, exist_ok=True)
            receipt_path = _receipt_write_path(f0_dir, receipt_key, run_id)
            receipt_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
            result.written_receipts += 1

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_item(item: BrokerIntakeItem) -> str:
    label = {
        "new": "NEW      ",
        "duplicate": "DUPLICATE",
        "exists": "EXISTS   ",
        "failed": "FAILED   ",
    }[item.status]
    name = item.meta.get("filename") or (item.source_path.name if item.source_path else f"line {item.line_no}")
    if item.status == "failed":
        return f"  {label} line={item.line_no} {name} [{item.error_code}] {item.error_message} fix_hint={item.fix_hint}"
    date = item.published_at.date().isoformat() if item.published_at else "?"
    return f"  {label} {item.content_id} date={date} vol={item.storage_volume} {name} -> {item.raw_path_rel}"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m finer.ingestion.broker_research_intake",
        description="F0 intake for broker research PDFs from a meta JSONL (dry-run by default).",
    )
    parser.add_argument("--meta-jsonl", type=Path, required=True, help="meta JSONL path (one report per line)")
    parser.add_argument("--limit", type=int, default=None, help="max meta lines to process")
    parser.add_argument("--execute", action="store_true", help="actually write records/receipts/archive (requires --limit)")
    parser.add_argument("--data-root", type=Path, default=None, help=f"data root (default: {DATA_ROOT})")
    parser.add_argument("--mode", choices=_ARCHIVE_MODES, default="symlink", help="raw archive mode (default: symlink)")
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="skip Project Memory F0-index registration (stage_status / asset_index)",
    )
    args = parser.parse_args(argv)

    if args.execute and args.limit is None:
        parser.error("--execute requires --limit N (batch-size guard against accidental full-volume import)")

    # C6: broker raw PDFs live on an external volume. If it's unmounted, skip the
    # whole broker intake with a warning alert instead of erroring (or flooding
    # per-item VOLUME_MISSING). Checked before the meta-exists guard so a meta
    # file that lives on the unmounted volume degrades gracefully too.
    from finer.ops.mount_health import broker_mount_alert, broker_source_volume, broker_volume_available

    if not broker_volume_available():
        from finer.ops.alerts import send_alert

        alert = broker_mount_alert(skipped=0, job="broker_intake")
        send_alert(alert)
        print(
            f"[skipped] broker source volume {broker_source_volume()} is not mounted; "
            f"skipping broker intake. {alert.fix_hint}"
        )
        return 0

    if not args.meta_jsonl.exists():
        parser.error(f"meta JSONL not found: {args.meta_jsonl}")

    data_root = args.data_root or DATA_ROOT

    # Register imported records into Project Memory by default so new broker
    # imports appear in stage_status / the Import Console. Dry-runs never
    # register; --no-register opts out explicitly.
    index_writer = None
    if args.execute and not args.no_register:
        from finer.ingestion.f0_index_writer import F0IndexWriter

        pm_db_path = data_root / "project_memory" / "finer.project.sqlite3"
        index_writer = F0IndexWriter(db_path=pm_db_path)

    result = run_intake(
        args.meta_jsonl,
        data_root,
        limit=args.limit,
        execute=args.execute,
        mode=args.mode,
        index_writer=index_writer,
    )

    header = "[execute]" if args.execute else "[dry-run]"
    print(
        f"{header} broker intake run_id={result.run_id} meta={args.meta_jsonl} "
        f"limit={args.limit} mode={args.mode} data_root={data_root}"
    )
    for item in result.items:
        print(_format_item(item))
    print(
        f"summary: scanned={result.scanned} new={result.new} duplicate={result.duplicates} "
        f"exists={result.existing} failed={result.failed} "
        f"written_records={result.written_records} written_receipts={result.written_receipts} "
        f"registered={result.registered} register_failed={result.register_failed}"
    )
    if not args.execute:
        print("dry-run: nothing written. Re-run with --execute --limit N to persist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
