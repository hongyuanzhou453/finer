"""Tests for the F0-only broker research intake channel (A1).

All disk interaction goes through tmp_path with fake PDF bytes — the suite
never touches the real data/ tree or the external research volume.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, get_args

import pytest

from finer.ingestion.broker_research_intake import (
    BEIJING_TZ,
    main,
    parse_meta_date,
    run_intake,
    storage_volume_of,
)
from finer.schemas.content import ContentRecord
from finer.schemas.import_receipt import ImportReceipt, SourceChannel

FAKE_PDF = b"%PDF-1.4 fake broker research bytes\n%%EOF\n"


def _meta_line(filepath: Path, **overrides: Any) -> dict[str, Any]:
    meta = {
        "filepath": str(filepath),
        "filename": filepath.name,
        "broker": "摩根士丹利",
        "broker_raw": "大摩",
        "date": "2026-05-31",
        "topic": "风险回报更新",
        "company_name": "微博公司",
        "stock_code": "WB.US",
        "industry_l1": "科技与互联网",
        "industry_l2": "",
        "is_industry_report": False,
        "rating": "",
        "rating_action": "",
    }
    meta.update(overrides)
    return meta


def _write_fixture(tmp_path: Path, metas: list[dict[str, Any]]) -> Path:
    meta_jsonl = tmp_path / "meta.jsonl"
    meta_jsonl.write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in metas) + "\n",
        encoding="utf-8",
    )
    return meta_jsonl


def _make_pdf(tmp_path: Path, name: str, payload: bytes = FAKE_PDF) -> Path:
    pdf = tmp_path / "source" / name
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(payload)
    return pdf


# ---------------------------------------------------------------------------
# 1. Schema: SourceChannel literal accepts "broker"
# ---------------------------------------------------------------------------


def test_source_channel_literal_accepts_broker() -> None:
    assert "broker" in get_args(SourceChannel)
    receipt = ImportReceipt(
        run_id="r", source_channel="broker", source_kind="broker_research_pdf", status="completed"
    )
    assert receipt.source_channel == "broker"
    assert receipt.to_import_run()["source_channel"] == "broker"


# ---------------------------------------------------------------------------
# 2. Dry-run writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "大摩-微博公司（WB.US）：风险回报更新-260531.pdf")
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(pdf)])
    data_root = tmp_path / "data"

    result = run_intake(meta_jsonl, data_root, limit=5, execute=False)

    assert result.dry_run is True
    assert result.scanned == 1
    assert result.new == 1
    assert result.failed == 0
    assert result.written_records == 0
    assert result.written_receipts == 0
    assert not data_root.exists(), "dry-run must not create anything under data_root"

    item = result.items[0]
    expected_hash = hashlib.sha256(FAKE_PDF).hexdigest()
    assert item.content_id == f"broker_{expected_hash[:24]}"
    assert item.published_at == datetime(2026, 5, 31, tzinfo=BEIJING_TZ)
    # Receipts are still constructed (schema-validated) in dry-run.
    assert result.receipts[0].source_channel == "broker"
    assert result.receipts[0].status == "completed"


# ---------------------------------------------------------------------------
# 3. Execute: symlink mode + storage_volume recorded
# ---------------------------------------------------------------------------


def test_execute_symlink_archives_and_records_storage_volume(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "大摩-微博公司（WB.US）：风险回报更新-260531.pdf")
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(pdf)])
    data_root = tmp_path / "data"

    result = run_intake(meta_jsonl, data_root, limit=5, execute=True, mode="symlink")

    assert result.new == 1
    assert result.written_records == 1
    assert result.written_receipts == 1

    item = result.items[0]
    # raw archive: symlink under data/raw/broker/ resolving to the source bytes
    archive = data_root / item.raw_path_rel
    assert archive.is_symlink()
    assert archive.read_bytes() == FAKE_PDF
    assert archive.parent == data_root / "raw" / "broker"

    # ContentRecord: canonical fields
    record = ContentRecord.model_validate_json(item.record_path.read_text(encoding="utf-8"))
    assert record.source_type == "research_report"
    assert record.source_platform == "broker"
    assert record.file_type == "pdf"
    assert record.creator_id == "摩根士丹利"
    assert record.published_at == datetime(2026, 5, 31, tzinfo=BEIJING_TZ)
    assert record.dedupe_fingerprint == hashlib.sha256(FAKE_PDF).hexdigest()
    assert record.metadata["published_at_source"] == "meta_date"
    assert record.metadata["archive_mode"] == "symlink"
    assert record.metadata["meta"]["stock_code"] == "WB.US"

    # raw_path contract: relative to data_root, under raw/broker/, never raw/local/
    assert not Path(record.raw_path).is_absolute()
    assert record.raw_path.startswith("raw/broker/")
    assert "/raw/local/" not in f"/{record.raw_path}"
    assert (data_root / record.raw_path).exists()

    # Receipt: persisted, broker channel, storage_volume recorded
    receipt_path = data_root / "F0_intake" / "broker" / f"{item.content_id}.receipt.json"
    receipt = ImportReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    assert receipt.source_channel == "broker"
    assert receipt.status == "completed"
    assert receipt.records_created == 1
    assert receipt.raw_sha256["pdf"] == record.dedupe_fingerprint
    assert receipt.raw_paths["storage_volume"] == storage_volume_of(pdf)
    assert receipt.raw_paths["pdf"] == record.raw_path


def test_execute_copy_mode_copies_bytes(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "report.pdf")
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(pdf)])
    data_root = tmp_path / "data"

    result = run_intake(meta_jsonl, data_root, limit=5, execute=True, mode="copy")

    item = result.items[0]
    archive = data_root / item.raw_path_rel
    assert archive.exists() and not archive.is_symlink()
    assert archive.read_bytes() == FAKE_PDF


# ---------------------------------------------------------------------------
# 4. Missing/invalid date: skip with fix_hint, never mtime fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_date", ["", None, "31/05/2026", "not-a-date"])
def test_missing_or_invalid_date_skips_with_fix_hint(tmp_path: Path, bad_date: Any) -> None:
    pdf = _make_pdf(tmp_path, "no_date.pdf")
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(pdf, date=bad_date)])
    data_root = tmp_path / "data"

    result = run_intake(meta_jsonl, data_root, limit=5, execute=True)

    assert result.new == 0
    assert result.failed == 1
    assert result.written_records == 0

    item = result.items[0]
    assert item.status == "failed"
    assert item.published_at is None, "must NOT fall back to file mtime"
    assert item.error_code in ("F0_BROKER_DATE_MISSING", "F0_BROKER_DATE_INVALID")

    receipt = result.receipts[0]
    assert receipt.status == "failed"
    assert receipt.error is not None
    assert receipt.error.stage == "F0"
    assert receipt.error.source_channel == "broker"
    assert receipt.error.retryable is False
    assert receipt.error.request_id
    assert "date" in receipt.error.fix_hint
    # failed receipt still persisted for the audit trail; no ContentRecord written
    assert result.written_receipts == 1
    f0_dir = data_root / "F0_intake" / "broker"
    on_disk = list(f0_dir.iterdir())
    assert len(on_disk) == 1
    assert all(p.name.endswith(".receipt.json") for p in on_disk)


def test_parse_meta_date_strict() -> None:
    assert parse_meta_date("2026-05-31") == datetime(2026, 5, 31, tzinfo=BEIJING_TZ)
    assert parse_meta_date("") is None
    assert parse_meta_date(None) is None
    assert parse_meta_date("2026-13-01") is None
    assert parse_meta_date(20260531) is None


# ---------------------------------------------------------------------------
# 5. Content-hash dedupe
# ---------------------------------------------------------------------------


def test_content_hash_dedupe_within_run_and_across_runs(tmp_path: Path) -> None:
    pdf_a = _make_pdf(tmp_path, "a.pdf")
    pdf_b = _make_pdf(tmp_path, "b_same_bytes.pdf")  # byte-identical re-export
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(pdf_a), _meta_line(pdf_b)])
    data_root = tmp_path / "data"

    result = run_intake(meta_jsonl, data_root, limit=5, execute=True)

    assert result.new == 1
    assert result.duplicates == 1
    assert result.written_records == 1
    dup_receipt = result.receipts[1]
    assert dup_receipt.status == "skipped"
    assert dup_receipt.records_skipped == 1
    assert dup_receipt.content_id == result.items[0].content_id

    # second run: record already on disk -> "exists", still no new record
    rerun = run_intake(meta_jsonl, data_root, limit=5, execute=True)
    assert rerun.new == 0
    assert rerun.existing == 1
    assert rerun.duplicates == 1
    assert rerun.written_records == 0
    records = list((data_root / "F0_intake" / "broker").glob("*.json"))
    record_files = [p for p in records if ".receipt" not in p.name]
    assert len(record_files) == 1


# ---------------------------------------------------------------------------
# 6. Volume not mounted -> explicit retryable error
# ---------------------------------------------------------------------------


def test_missing_volume_reports_explicit_error(tmp_path: Path) -> None:
    meta = _meta_line(Path("/Volumes/NO_SUCH_VOLUME_finer_test/外资研报/x.pdf"))
    meta_jsonl = _write_fixture(tmp_path, [meta])

    result = run_intake(meta_jsonl, tmp_path / "data", limit=5, execute=False)

    item = result.items[0]
    assert item.status == "failed"
    assert item.error_code == "F0_BROKER_VOLUME_MISSING"
    receipt = result.receipts[0]
    assert receipt.error is not None
    assert receipt.error.retryable is True
    assert "/Volumes/NO_SUCH_VOLUME_finer_test" in receipt.error.message


# ---------------------------------------------------------------------------
# 7. F0 boundary guard: no parsing / pipeline / extraction imports
# ---------------------------------------------------------------------------


def test_module_source_has_no_cross_stage_or_pdf_parsing() -> None:
    source = Path("src/finer/ingestion/broker_research_intake.py").read_text(encoding="utf-8")
    forbidden = [
        "finer.parsing",
        "finer.pipeline",
        "finer.extraction",
        "finer.policy",
        "finer.backtest",
        "VisionDescriptor",
        "SummaryGenerator",
        "NLMSync",
        "subprocess",
        "lark-cli",
        # F0 must never open PDF content
        "pypdf",
        "pdfplumber",
        "PdfReader",
        "fitz",
    ]
    for token in forbidden:
        assert token not in source, f"F0 boundary violation: {token!r} found in module source"


# ---------------------------------------------------------------------------
# 8. CLI guards
# ---------------------------------------------------------------------------


def test_cli_execute_requires_limit(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "x.pdf")
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(pdf)])
    with pytest.raises(SystemExit) as exc_info:
        main(["--meta-jsonl", str(meta_jsonl), "--execute"])
    assert exc_info.value.code == 2  # argparse error


def test_cli_dry_run_prints_plan_and_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pdf = _make_pdf(tmp_path, "大摩-report.pdf")
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(pdf)])
    data_root = tmp_path / "data"

    rc = main(["--meta-jsonl", str(meta_jsonl), "--limit", "5", "--data-root", str(data_root)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert "NEW" in out
    assert "raw/broker/" in out
    assert "nothing written" in out
    assert not data_root.exists()


def test_cli_limit_caps_processing(tmp_path: Path) -> None:
    pdfs = [_make_pdf(tmp_path, f"r{i}.pdf", payload=FAKE_PDF + bytes([i])) for i in range(4)]
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(p) for p in pdfs])

    result = run_intake(meta_jsonl, tmp_path / "data", limit=2, execute=False)
    assert result.scanned == 2


# ---------------------------------------------------------------------------
# 9. Receipt construction sanity
# ---------------------------------------------------------------------------


def test_build_receipt_duplicate_has_no_error_envelope(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "dup.pdf")
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(pdf), _meta_line(pdf)])

    result = run_intake(meta_jsonl, tmp_path / "data", limit=5, execute=False)

    dup = result.receipts[1]
    assert dup.status == "skipped"
    assert dup.error is None
    assert dup.raw_paths["archive_mode"] == "symlink"


def test_receipt_never_carries_forbidden_key_material(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "sec.pdf")
    meta_jsonl = _write_fixture(tmp_path, [_meta_line(pdf)])

    result = run_intake(meta_jsonl, tmp_path / "data", limit=5, execute=False)

    payload = result.receipts[0].model_dump_json().lower()
    for forbidden in ("token", "secret", "password", "cookie", "authorization", "api_key"):
        assert forbidden not in payload
