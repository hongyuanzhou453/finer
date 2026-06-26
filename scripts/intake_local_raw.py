#!/usr/bin/env python
"""CLI: backfill F0 ContentRecords for local raw images/PDFs (F0-only).

Default is dry-run (scan + stats, no writes). Pass --write to actually emit
ContentRecord JSON under data/F0_intake/local/.

    python scripts/intake_local_raw.py            # dry-run
    python scripts/intake_local_raw.py --write    # write records
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from finer.ingestion.local_raw_intake import run_intake  # noqa: E402


def _print_dist(title: str, dist: dict[str, int]) -> None:
    print(f"{title}:")
    for key, count in sorted(dist.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {key:28s} {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=Path("data"), type=Path)
    parser.add_argument("--raw-subdir", default="raw")
    parser.add_argument(
        "--suffixes",
        default=None,
        help="Comma-separated suffixes to scan, e.g. '.pdf'; default = all image+pdf",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually write records (default: dry-run, no writes)",
    )
    args = parser.parse_args()

    raw_root = args.data_root / args.raw_subdir
    if not raw_root.exists():
        print(f"raw root not found: {raw_root}", file=sys.stderr)
        raise SystemExit(2)

    from finer.ingestion.local_raw_intake import _SUPPORTED_SUFFIXES

    suffixes = (
        {s if s.startswith(".") else "." + s for s in args.suffixes.split(",")}
        if args.suffixes
        else _SUPPORTED_SUFFIXES
    )
    result = run_intake(
        raw_root=raw_root,
        data_root=args.data_root,
        dry_run=not args.write,
        suffixes=suffixes,
    )

    print(f"raw root:   {raw_root}")
    print(f"Scanned:    {result.scanned}")
    print(f"New:        {result.new}")
    print(f"Duplicates: {result.duplicates}  (byte-identical, collapsed)")
    print(f"Existing:   {result.existing}  (record already present)")
    if args.write:
        print(f"Written:    {result.written}")
    print()
    _print_dist("By group/creator", result.by_group)
    _print_dist("By source_type", result.by_source_type)
    _print_dist("By file_type", result.by_file_type)
    _print_dist("By published_at source", result.by_published_source)

    if result.errors:
        print(f"\nERRORS ({len(result.errors)}):")
        for err in result.errors[:20]:
            print(f"  {err}")

    mode = "WROTE RECORDS" if args.write else "DRY-RUN (no files written)"
    print(f"\nMode: {mode}")


if __name__ == "__main__":
    main()
