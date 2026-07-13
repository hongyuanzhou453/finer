"""Tests for scripts/apply_f2_gap_reviews.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.apply_f2_gap_reviews import (
    plan_registry_gap_apply,
    write_registry_gap_plan,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_plan_registry_gap_apply_dry_run_writes_nothing(tmp_path: Path):
    review = tmp_path / "review.jsonl"
    dpo = tmp_path / "dpo"
    _write_jsonl(
        review,
        [
            {
                "alias_candidate": "星河出行科技",
                "source_record_id": "local_1",
                "review_status": "approved",
            }
        ],
    )

    plan = plan_registry_gap_apply(review, dpo_dir=dpo)

    assert plan.scanned == 1
    assert plan.approved == 1
    assert plan.to_write == 1
    assert plan.written == 0
    assert not (dpo / "registry_gaps.jsonl").exists()


def test_write_registry_gap_plan_appends_approved_rows(tmp_path: Path):
    review = tmp_path / "review.jsonl"
    dpo = tmp_path / "dpo"
    _write_jsonl(
        review,
        [
            {
                "alias_candidate": "星河出行科技",
                "source_record_id": "local_1",
                "review_status": "approved",
                "suggested_ticker": "2498.hk",
                "market": "hk",
            }
        ],
    )

    plan = plan_registry_gap_apply(review, dpo_dir=dpo)
    write_registry_gap_plan(plan, reviewer_id="reviewer_a")

    rows = _read_jsonl(dpo / "registry_gaps.jsonl")
    assert plan.written == 1
    assert rows[0]["alias"] == "星河出行科技"
    assert rows[0]["item_id"] == "local_1"
    assert rows[0]["suggested_ticker"] == "2498.HK"
    assert rows[0]["market"] == "HK"
    assert rows[0]["reviewer_id"] == "reviewer_a"


def test_plan_registry_gap_apply_skips_duplicates_and_non_approved(tmp_path: Path):
    review = tmp_path / "review.jsonl"
    dpo = tmp_path / "dpo"
    _write_jsonl(
        dpo / "registry_gaps.jsonl",
        [{"alias": "星河出行科技", "item_id": "local_1"}],
    )
    _write_jsonl(
        review,
        [
            {
                "alias_candidate": "星河出行科技",
                "source_record_id": "local_1",
                "review_status": "approved",
            },
            {
                "alias_candidate": "未来机器人",
                "source_record_id": "local_2",
                "review_status": "rejected",
            },
            {
                "alias_candidate": "未来出行科技",
                "source_record_id": "local_3",
                "review_status": "",
            },
        ],
    )

    plan = plan_registry_gap_apply(review, dpo_dir=dpo)

    assert plan.scanned == 3
    assert plan.approved == 1
    assert plan.duplicates == 1
    assert plan.skipped == 2
    assert plan.to_write == 0


def test_plan_registry_gap_apply_reports_bad_review_rows(tmp_path: Path):
    review = tmp_path / "review.jsonl"
    _write_jsonl(
        review,
        [
            {
                "alias_candidate": "",
                "source_record_id": "local_1",
                "review_status": "approved",
            },
            {
                "alias_candidate": "未来出行科技",
                "source_record_id": "local_2",
                "review_status": "maybe",
            },
        ],
    )

    plan = plan_registry_gap_apply(review, dpo_dir=tmp_path / "dpo")

    assert plan.to_write == 0
    assert len(plan.errors) == 2
    assert "alias_candidate" in plan.errors[0]
    assert "unsupported review_status" in plan.errors[1]


def test_apply_gap_reviews_cli_is_dry_run_first_and_requires_reviewer(tmp_path: Path):
    review = tmp_path / "review.jsonl"
    dpo = tmp_path / "dpo"
    script = Path("scripts/apply_f2_gap_reviews.py").resolve()
    _write_jsonl(
        review,
        [
            {
                "alias_candidate": "星河出行科技",
                "source_record_id": "local_1",
                "review_status": "approved",
            }
        ],
    )

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--review-in",
            str(review),
            "--dpo-dir",
            str(dpo),
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not (dpo / "registry_gaps.jsonl").exists()

    missing_reviewer = subprocess.run(
        [
            sys.executable,
            str(script),
            "--review-in",
            str(review),
            "--dpo-dir",
            str(dpo),
            "--write",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_reviewer.returncode == 2
    assert "reviewer-id" in missing_reviewer.stderr

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--review-in",
            str(review),
            "--dpo-dir",
            str(dpo),
            "--write",
            "--reviewer-id",
            "reviewer_a",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _read_jsonl(dpo / "registry_gaps.jsonl")[0]["alias"] == "星河出行科技"
