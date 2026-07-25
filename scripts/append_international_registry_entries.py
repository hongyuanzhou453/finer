#!/usr/bin/env python
"""Surgically append international-market entries to the committed broker registry.

C9 follow-up #1 (international anchor unlock), the *safe* variant. Instead of
regenerating ``configs/entity_registry_broker.yaml`` wholesale — which drops ~19
existing US-ADR name aliases (ASML / Diageo / ADP …) — this ADDS only the
entries whose market is international (UK / FR / KR / … — anything outside the
committed ``{US, CN, HK, TW, JP}`` domestic set) and whose alias is not already
present. Every existing entry is preserved bit-for-bit; there is no regression to
current anchoring.

Pairs with:
  * the ``broker_entity_registry._VALID_MARKETS`` loader fix (derives valid
    markets from the ticker_normalization tables, so these international entries
    actually LOAD instead of being dropped);
  * ``scripts/c9_reanchor_no_anchor_envelopes.py --execute`` (re-anchor so the new
    aliases produce international anchors);
  * ``scripts/drive_broker_recommendations.py --execute`` (produce the actions).

Build the source registry first (reads the external-disk reports.db):
    python scripts/build_broker_entity_registry.py --out /tmp/registry_rebuilt.yaml

Then:
    python scripts/append_international_registry_entries.py \
        --source /tmp/registry_rebuilt.yaml            # dry-run (default)
    python scripts/append_international_registry_entries.py \
        --source /tmp/registry_rebuilt.yaml --execute  # back up target + write

MUTATION IS A RED LINE. Dry-run by default; ``--execute`` backs up the target
registry (named snapshot) before writing. Existing entries are never modified or
removed — append-only.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

DOMESTIC_MARKETS = frozenset({"US", "CN", "HK", "TW", "JP"})
DEFAULT_TARGET = REPO_ROOT / "configs" / "entity_registry_broker.yaml"


def _suffix(symbol: str) -> Optional[str]:
    return symbol.rsplit(".", 1)[1] if isinstance(symbol, str) and "." in symbol else None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True,
                    help="freshly-built registry (from build_broker_entity_registry.py) "
                         "to harvest international entries from")
    ap.add_argument("--target", type=Path, default=DEFAULT_TARGET,
                    help=f"committed registry to append into (default: {DEFAULT_TARGET})")
    ap.add_argument("--execute", action="store_true",
                    help="back up target then write the merged registry")
    args = ap.parse_args(argv)

    target_text = args.target.read_text(encoding="utf-8")
    # Preserve the AUTO-GENERATED comment header verbatim (safe_dump drops comments).
    header_lines = []
    for line in target_text.splitlines():
        if line.startswith("#"):
            header_lines.append(line)
        else:
            break
    header = ("\n".join(header_lines) + "\n") if header_lines else ""

    target_doc = yaml.safe_load(target_text)
    source_doc = yaml.safe_load(args.source.read_text(encoding="utf-8"))
    tgt_entries = target_doc.get("entries") or {}
    src_entries = source_doc.get("entries") or {}
    print(f"[{'execute' if args.execute else 'dry-run'}] append international entries")
    print(f"  target: {args.target}  ({len(tgt_entries)} entries)")
    print(f"  source: {args.source}  ({len(src_entries)} entries)")

    # International = market outside the domestic set. Append only aliases not
    # already present (never overwrite a curated/committed alias).
    to_add: dict = {}
    collisions = 0
    for alias, spec in src_entries.items():
        if not isinstance(spec, dict):
            continue
        market = spec.get("market")
        if market in DOMESTIC_MARKETS or not isinstance(market, str):
            continue
        if alias in tgt_entries:
            collisions += 1
            continue
        to_add[alias] = spec

    by_suffix = Counter(_suffix(s.get("symbol", "")) for s in to_add.values())
    distinct_symbols = {s.get("symbol") for s in to_add.values()}
    print(f"\ninternational aliases to add: {len(to_add)}  "
          f"(distinct tickers: {len(distinct_symbols)})")
    print(f"  by exchange suffix: {dict(by_suffix)}")
    print(f"  aliases skipped (already in target, preserved): {collisions}")
    # sample
    for alias, spec in list(sorted(to_add.items()))[:10]:
        print(f"    + {alias!r} -> {spec.get('symbol')} ({spec.get('market')})")

    if not args.execute:
        print("\ndry-run: nothing written. --execute backs up target then appends.")
        return 0
    if not to_add:
        print("\nnothing to add.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bak = args.target.with_name(
        f"{args.target.stem}.bak-{stamp}-intl-append-{uuid.uuid4().hex[:8]}{args.target.suffix}"
    )
    shutil.copy2(args.target, bak)
    print(f"\n  backup: {bak}")

    merged = dict(tgt_entries)
    merged.update(to_add)  # append-only: tgt keys already excluded above
    target_doc["entries"] = merged
    if "entry_count" in target_doc:
        target_doc["entry_count"] = len(merged)

    # Header: original AUTO-GENERATED block + one honest provenance line so the
    # file records it was surgically appended (not a clean rebuild).
    append_note = (
        f"# int'l-append: +{len(to_add)} international-market aliases "
        f"({len(distinct_symbols)} tickers) via "
        f"scripts/append_international_registry_entries.py ({stamp})\n"
    )
    body = yaml.safe_dump(
        target_doc, allow_unicode=True, sort_keys=True, default_flow_style=False
    )
    args.target.write_text(header + append_note + body, encoding="utf-8")
    print(f"  wrote {args.target}  ({len(merged)} entries; +{len(to_add)})")
    print("\nNext: re-anchor + drive:")
    print("  python scripts/c9_reanchor_no_anchor_envelopes.py --data-root <data> --execute")
    print("  python scripts/drive_broker_recommendations.py --data-root <data> --execute")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
