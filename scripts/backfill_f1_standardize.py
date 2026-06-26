#!/usr/bin/env python
"""F1 full backfill — standardize intake images/PDFs via StandardizationRouter.

Loads the ContentRecords written by local_raw_intake, excludes bilibili video
covers and the non-investment tutorial PDF, and runs each remaining item through
the F1 router (which calls MiMo vision for images with no pre-extracted text).
ContentEnvelopes land at data/F1_standardized/{content_id}/content_envelope.json.

Concurrent, resumable (skips items whose envelope already exists), with a hard
guard that the MiMo vision client is actually reachable — so images never
silently degrade to non-OCR placeholder blocks.

    python scripts/backfill_f1_standardize.py --dry-run           # plan only
    python scripts/backfill_f1_standardize.py --limit 8           # try a few
    python scripts/backfill_f1_standardize.py --concurrency 4     # full run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock

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
from finer.parsing.ocr_quality import envelope_failure_tag  # noqa: E402


def load_records(data_root: Path) -> list[ContentRecord]:
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


def is_excluded(rec: ContentRecord) -> bool:
    """Skip bilibili video covers (no text) and the non-investment tutorial PDF.

    Note: bilibili dirs map to creator_id=None (infra bucket), so we test the
    raw_path rather than creator_id.
    """
    rp = (rec.raw_path or "").replace("\\", "/")
    if "/bilibili/" in rp:
        return True
    if rec.file_type == "pdf" and "/raw/local/" in rp:
        return True
    if "教程" in (rec.title or ""):
        return True
    return False


def envelope_path(data_root: Path, rec: ContentRecord) -> Path:
    return data_root / "F1_standardized" / rec.content_id / "content_envelope.json"


def needs_reprocess(path: Path) -> bool:
    """True if a stored envelope is a hard failure that must be re-standardized
    rather than skipped by resume: a vision fallback (429/unreachable), a captured
    refusal message, or fabricated placeholder URLs. 'thin' is NOT reprocessed —
    it may be a genuinely text-free image.
    """
    try:
        e = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return envelope_failure_tag(e) in ("fallback", "refusal", "hallucination")


def process_one(router: StandardizationRouter, rec: ContentRecord, data_root: Path) -> dict:
    raw_path = Path(rec.raw_path)
    if not raw_path.exists():
        return {"content_id": rec.content_id, "status": "raw_missing"}
    t0 = time.time()
    env, report = router.route(rec, raw_path)
    dt = time.time() - t0
    out = envelope_path(data_root, rec)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(env.model_dump_json(indent=2), encoding="utf-8")
    return {
        "content_id": rec.content_id,
        "file_type": rec.file_type,
        "adapter": report["adapter"],
        "blocks": report["block_count"],
        "canonical_ok": report["canonical_validation_passed"],
        "low_quality": report["low_quality_block_count"],
        "secs": round(dt, 1),
        "status": "ok",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=Path("data"))
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="cap todo count (0 = all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    recs = load_records(args.data_root)
    todo: list[ContentRecord] = []
    excluded = done_already = 0
    for r in recs:
        if is_excluded(r):
            excluded += 1
            continue
        ep = envelope_path(args.data_root, r)
        if ep.exists() and not needs_reprocess(ep):
            done_already += 1
            continue
        todo.append(r)
    if args.limit:
        todo = todo[: args.limit]

    print(f"records={len(recs)} excluded={excluded} already_done={done_already} todo={len(todo)}")
    print("todo by file_type:", dict(Counter(r.file_type for r in todo)))
    print("todo by creator:  ", dict(Counter(r.creator_id for r in todo)))
    if args.dry_run:
        print("\nDRY-RUN — no processing.")
        return
    if not todo:
        print("\nNothing to do.")
        return

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
    lock = Lock()
    done = 0
    t_start = time.time()

    def work(rec: ContentRecord) -> dict:
        nonlocal done
        try:
            row = process_one(router, rec, args.data_root)
        except Exception as e:
            row = {
                "content_id": rec.content_id,
                "file_type": rec.file_type,
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
            }
        with lock:
            done += 1
            tag = row.get("status", "?")
            extra = (
                f"blocks={row.get('blocks')} {row.get('secs')}s"
                if tag == "ok"
                else row.get("error", "")
            )
            print(f"[{done}/{len(todo)}] {tag:11s} {rec.file_type:5s} {rec.content_id} {extra}")
        return row

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [ex.submit(work, r) for r in todo]
        for fut in as_completed(futures):
            rows.append(fut.result())

    run_dir = args.data_root / "F1_standardized" / "_backfill_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest = run_dir / f"backfill_{ts}.json"
    manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = [r for r in rows if r.get("status") == "ok"]
    failed = [r for r in rows if r.get("status") != "ok"]
    wall = time.time() - t_start
    print(f"\n=== done: {len(ok)}/{len(rows)} ok, {len(failed)} failed, wall {wall:.0f}s ===")
    if ok:
        print(f"canonical_ok:                {sum(1 for r in ok if r.get('canonical_ok'))}/{len(ok)}")
        print(f"items w/ low-quality blocks: {sum(1 for r in ok if r.get('low_quality', 0) > 0)}/{len(ok)}")
        secs = [r["secs"] for r in ok if "secs" in r]
        if secs:
            print(f"avg secs/item: {sum(secs) / len(secs):.1f}")
    for r in failed[:20]:
        print(f"  FAIL {r['content_id']}: {r.get('status')} {r.get('error', '')}")
    print(f"\nmanifest → {manifest}")


if __name__ == "__main__":
    main()
