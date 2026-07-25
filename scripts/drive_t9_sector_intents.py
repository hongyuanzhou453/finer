#!/usr/bin/env python
"""Drive T9 sector transmission chains into F3 sector intents (t9i_*) — D1.

Thin CLI shell over ``extraction.sector_transmission_adapter`` (adapt) and
``pipeline.broker_runner`` (F4→F5, same canonical entry as bri_*, separate
``t9i_`` namespace). Mirrors the A3 operating discipline:

  * dry-run default — full funnel report, zero writes;
  * ``--execute`` writes ONLY the t9i F3 intent files (byte-stable ids);
  * ``--drive-f5`` (requires --execute) additionally runs the declarative
    F4→F5 executor over the t9i family — use with ``--limit`` for the
    small-sample gate before any full run;
  * NAMEZY mount checked before touching the burn products.

The funnel is the point: themes that don't map to a configured sector proxy
are counted per-theme — that distribution IS the sector_proxies.yaml backlog.

Usage:
    python scripts/drive_t9_sector_intents.py                       # dry-run
    python scripts/drive_t9_sector_intents.py --limit 50 --execute  # small sample
    python scripts/drive_t9_sector_intents.py --limit 50 --execute --drive-f5
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from finer.enrichment.sector_proxy import get_sector_proxy_registry  # noqa: E402
from finer.extraction.broker_recommendation_adapter import _build_f0_index  # noqa: E402
from finer.extraction.sector_transmission_adapter import adapt_t9_record  # noqa: E402
from finer.ops.mount_health import broker_volume_available  # noqa: E402

DEFAULT_T9_DIR = Path(
    "/Volumes/NAMEZY/外资研报/rag_data/burn_rescue_20260725/products/t9_sector_deep"
)


def _iter_t9_rows(t9_dir: Path) -> Iterator[Dict[str, Any]]:
    for name in ("burn_t9.jsonl", "burn_t9_r2.jsonl"):
        path = t9_dir / name
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (row.get("validation") or {}).get("json_ok"):
                    yield row


def _envelope_id_for(data_root: Path, content_id: str) -> Optional[str]:
    env_path = data_root / "F1_standardized" / content_id / "content_envelope.json"
    if not env_path.exists():
        return None
    try:
        return json.loads(env_path.read_text(encoding="utf-8")).get("envelope_id")
    except (OSError, json.JSONDecodeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--t9-dir", type=Path, default=DEFAULT_T9_DIR)
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap ADAPTED intents (small-sample gate)")
    parser.add_argument("--execute", action="store_true",
                        help="write t9i F3 intent files (default: dry-run)")
    parser.add_argument("--drive-f5", action="store_true",
                        help="after writing intents, run declarative F4->F5 "
                             "over the t9i family (requires --execute)")
    parser.add_argument("--samples", type=int, default=20,
                        help="dry-run: how many sample intents to print")
    args = parser.parse_args()

    if args.drive_f5 and not args.execute:
        parser.error("--drive-f5 requires --execute")
    if not broker_volume_available():
        print("ERROR: broker source volume (NAMEZY) not mounted — aborting.")
        return 2

    data_root = args.data_root.resolve()
    registry = get_sector_proxy_registry(REPO_ROOT)
    sector_names = {
        key: registry.resolve(key).sector_name
        for key in registry.known_sectors()
        if registry.resolve(key) is not None
    }
    print(f"configured sector proxies: {len(sector_names)}")

    f0_index = _build_f0_index(data_root)
    print(f"F0 index (source_filepath -> record): {len(f0_index)}")

    funnel: Counter = Counter()
    unmapped_themes: Counter = Counter()
    adapted = []
    envelope_cache: Dict[str, Optional[str]] = {}

    for row in _iter_t9_rows(args.t9_dir):
        funnel["rows_scanned"] += 1
        filepath = row.get("filepath") or ""
        f0_record = f0_index.get(filepath)
        if f0_record is None:
            funnel["no_f0"] += 1
            continue
        content_id = f0_record.get("content_id")
        if not content_id:
            funnel["no_f0"] += 1
            continue
        if content_id not in envelope_cache:
            envelope_cache[content_id] = _envelope_id_for(data_root, content_id)
        envelope_id = envelope_cache[content_id]
        if envelope_id is None:
            funnel["no_envelope"] += 1
            continue

        intent, skip_reason = adapt_t9_record(row, f0_record, envelope_id, sector_names)
        if intent is None:
            funnel[skip_reason] += 1
            if skip_reason == "theme_unmapped":
                theme = (row.get("extraction") or {}).get("industry_or_theme")
                if theme:
                    unmapped_themes[theme.strip()] += 1
            continue

        funnel["adapted"] += 1
        adapted.append((content_id, intent))
        if args.limit is not None and len(adapted) >= args.limit:
            funnel["stopped_at_limit"] = 1
            break

    print("\n== adapt funnel ==")
    for key, val in funnel.most_common():
        print(f"  {key}: {val}")
    print("\n== top unmapped themes (sector_proxies.yaml backlog) ==")
    for theme, n in unmapped_themes.most_common(25):
        print(f"  {n:>4}  {theme}")

    sector_dist = Counter(i.target_symbol for _, i in adapted)
    direction_dist = Counter(i.direction for _, i in adapted)
    print(f"\nadapted sector distribution: {dict(sector_dist)}")
    print(f"adapted direction distribution: {dict(direction_dist)}")

    if not args.execute:
        for cid, intent in adapted[: args.samples]:
            print(f"\n--- sample ({cid}) ---")
            print(intent.model_dump_json(indent=2))
        print(f"\n[dry-run] {len(adapted)} intents adaptable. "
              f"Use --execute to write t9i F3 files.")
        return 0

    f3_dir = data_root / "F3_intents"
    f3_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for _cid, intent in adapted:
        out = f3_dir / f"{intent.intent_id}.json"
        out.write_text(intent.model_dump_json(indent=2), encoding="utf-8")
        written += 1
    print(f"\nt9i F3 intents written: {written} -> {f3_dir}")

    if args.drive_f5:
        import asyncio

        from finer.pipeline.broker_runner import run_broker_declarative_f5

        report = asyncio.run(
            run_broker_declarative_f5(
                data_root,
                content_ids={cid for cid, _ in adapted},
                execute=True,
                intent_glob="t9i_*.json",
                output_prefix="t9i_",
            )
        )
        print("\n== t9i F4->F5 report ==")
        for key, val in report.to_dict().items():
            if key in ("skip_detail", "written_files", "planned"):
                continue
            print(f"  {key}: {val}")
        print(f"  files written: {len(report.written_files)}")
        for p in report.written_files[:10]:
            print(f"    {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
