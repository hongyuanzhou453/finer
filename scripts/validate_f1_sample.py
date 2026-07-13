#!/usr/bin/env python
"""F1 small-sample validation — run StandardizationRouter over sampled raw files.

Loads the ContentRecords written by local_raw_intake, stratified-samples images
by creator (plus optional borrowed PDFs that cover types missing from data/raw),
runs each through StandardizationRouter — which calls MiMo vision for images that
have no pre-extracted text — saves every ContentEnvelope, and prints a per-item
and aggregate report so OCR/standardization quality can be inspected by hand.

    python scripts/validate_f1_sample.py --smoke          # 2 imgs/creator, no PDFs
    python scripts/validate_f1_sample.py --img-per-creator 10 --pdfs
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from finer.schemas.content import ContentRecord  # noqa: E402
from finer.parsing.standardization_router import StandardizationRouter  # noqa: E402
from finer.llm.client import LLMClient  # noqa: E402
from finer.model_config import get_vision_registry  # noqa: E402
from finer.ingestion.local_raw_intake import (  # noqa: E402
    sha256_file,
    infer_published_at,
    infer_file_type,
)

# PDFs borrowed from outside data/raw to cover types absent there
# (real research-report / livestream-transcript / weekly-strategy PDFs).
_BORROW_PDFS = [
    (
        "data/L0_ingest/trader_ji/trader韭（截止3月20）/3号文件夹：内部直播回放/三月/20260315内部直播文稿.pdf",
        "livestream_audio",
        "trader_ji",
    ),
    (
        "data/L0_ingest/trader_ji/trader韭（截止3月20）/4号文件夹：周度策略/三月/20260315课代表整理.pdf",
        "weekly_strategy",
        "trader_ji",
    ),
    ("F1训练集/广发：CPO设备.pdf", "research_report", None),
]


def load_intake_records(data_root: Path) -> list[ContentRecord]:
    recs: list[ContentRecord] = []
    for f in sorted((data_root / "F0_intake" / "local").rglob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (
            isinstance(d, dict)
            and d.get("metadata", {}).get("registered_via") == "local_raw_intake"
        ):
            try:
                recs.append(ContentRecord.model_validate(d))
            except Exception:
                continue
    return recs


def stratified_images(recs: list[ContentRecord], per_creator: int) -> list[ContentRecord]:
    by_creator: dict[str, list[ContentRecord]] = defaultdict(list)
    for r in recs:
        if r.file_type == "image":
            by_creator[r.creator_id or "misc"].append(r)
    out: list[ContentRecord] = []
    for _creator, items in sorted(by_creator.items()):
        items.sort(key=lambda r: r.published_at.timestamp() if r.published_at else 0.0)
        if len(items) <= per_creator:
            out.extend(items)
        else:
            step = len(items) / per_creator
            out.extend(items[int(i * step)] for i in range(per_creator))
    return out


def adhoc_record(path: Path, source_type: str, creator_id) -> ContentRecord:
    h = sha256_file(path)
    pub, _ = infer_published_at(path)
    return ContentRecord(
        content_id=f"sample_{h[:24]}",
        source_type=source_type,
        source_platform="local",
        creator_id=creator_id,
        creator_name=creator_id,
        published_at=pub,
        title=path.name,
        raw_path=str(path),
        file_type=infer_file_type(path),
        metadata={"registered_via": "sample_adhoc", "content_sha256": h},
        dedupe_fingerprint=h,
        language="zh",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=Path("data"))
    ap.add_argument("--img-per-creator", type=int, default=8)
    ap.add_argument("--pdfs", action="store_true", help="include real + borrowed PDFs")
    ap.add_argument("--smoke", action="store_true", help="tiny run: 2 imgs/creator, no PDFs")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    if args.smoke:
        args.img_per_creator = 2

    recs = load_intake_records(args.data_root)
    samples = stratified_images(recs, args.img_per_creator)

    if args.pdfs and not args.smoke:
        samples += [
            r for r in recs if r.file_type == "pdf" and "教程" not in (r.title or "")
        ]
        for rel, st, cr in _BORROW_PDFS:
            p = Path(rel)
            if p.exists():
                samples.append(adhoc_record(p, st, cr))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = args.label or ("smoke" if args.smoke else "sample")
    out_dir = args.data_root / "F1_validation_runs" / f"{label}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    vision_llm = LLMClient.from_registry(get_vision_registry())
    if vision_llm is None:
        print(
            "FATAL: vision LLMClient is None — check MIMO_API_KEY in .env. "
            "(Without it, images silently fall back to non-OCR placeholder blocks.)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    router = StandardizationRouter(llm_client=vision_llm)

    rows: list[dict] = []
    print(f"Running {len(samples)} items → {out_dir}\n")
    for i, rec in enumerate(samples, 1):
        raw_path = Path(rec.raw_path)
        row: dict = {
            "content_id": rec.content_id,
            "file_type": rec.file_type,
            "creator": rec.creator_id,
            "title": rec.title,
        }
        if not raw_path.exists():
            row["error"] = "raw_missing"
            rows.append(row)
            print(f"[{i}/{len(samples)}] MISSING {raw_path}")
            continue
        t0 = time.time()
        try:
            env, report = router.route(rec, raw_path)
            dt = time.time() - t0
            (out_dir / f"{rec.content_id}.envelope.json").write_text(
                env.model_dump_json(indent=2), encoding="utf-8"
            )
            text_chars = sum(len(b.text or "") for b in env.blocks)
            row.update(
                adapter=report["adapter"],
                blocks=report["block_count"],
                low_quality=report["low_quality_block_count"],
                canonical_ok=report["canonical_validation_passed"],
                text_chars=text_chars,
                secs=round(dt, 1),
                block_types=",".join(sorted({b.block_type for b in env.blocks})),
            )
            print(
                f"[{i}/{len(samples)}] {rec.file_type:5s} {report['adapter']:6s} "
                f"blocks={report['block_count']:2d} chars={text_chars:5d} "
                f"canon={report['canonical_validation_passed']} {dt:5.1f}s "
                f"{(rec.title or '')[:38]}"
            )
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
            print(f"[{i}/{len(samples)}] ERROR {type(e).__name__}: {e}")
        rows.append(row)

    (out_dir / "_summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    done = [r for r in rows if "error" not in r]
    print(f"\n=== summary: {len(done)}/{len(rows)} ok ===")
    if done:
        secs = [r["secs"] for r in done if "secs" in r]
        print(f"canonical_ok:  {sum(1 for r in done if r.get('canonical_ok'))}/{len(done)}")
        print(f"avg secs/item: {statistics.mean(secs):.1f}   total: {sum(secs):.0f}s")
        print(f"avg blocks:    {statistics.mean([r['blocks'] for r in done]):.1f}")
        print(
            f"items w/ low-quality blocks: "
            f"{sum(1 for r in done if r.get('low_quality', 0) > 0)}/{len(done)}"
        )
    errs = [r for r in rows if "error" in r]
    if errs:
        print(f"errors: {len(errs)}")
        for r in errs[:10]:
            print(f"  {r.get('content_id')}: {r['error']}")
    print(f"\nenvelopes → {out_dir}")


if __name__ == "__main__":
    main()
