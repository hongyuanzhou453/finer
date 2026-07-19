"""Prune stale local backups (Phase 0 C6 / OPS-6).

Two backup families accumulate under ``data/``:

  * ``data/F5_executed.bak-<YYYYMMDD-HHMMSS>``          — pre-settle snapshots (dirs)
  * ``data/project_memory/finer.project.sqlite3.bak-*`` — DB safety snapshots (files)

Retention policy:
  * keep the ``--keep`` most recent *timestamped* backups per family (default 3);
  * ALWAYS protect *named* snapshots — any ``.bak-<label>`` whose label is not a
    pure ``YYYYMMDD-HHMMSS`` timestamp (e.g. ``.bak-20260718-prebroker``,
    ``.bak-pre-f8f70a-cleanup``). These are deliberate pre-migration safety
    snapshots and are never auto-deleted;
  * a DB backup's ``-wal`` / ``-shm`` siblings are pruned together with it.

DELETION IS A RED LINE. This script is **dry-run by default** and only prints the
plan. ``--execute`` performs deletion, but the intended workflow is: run dry-run,
have a human review the list, then run ``--execute``. (D4 authorized F5/DB
rebuild backups but NOT .bak cleanup — surface the list to the user first.)
"""

from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from finer.paths import DATA_ROOT

TIMESTAMP_RE = re.compile(r"^\d{8}-\d{6}$")
DEFAULT_KEEP = 3


@dataclass
class BackupInfo:
    path: Path
    label: str          # text after ".bak-"
    is_timestamped: bool
    mtime: float
    size_bytes: int


@dataclass
class GroupPlan:
    family: str
    protected: List[BackupInfo]
    kept: List[BackupInfo]
    to_delete: List[BackupInfo]


def _entry_size(path: Path) -> int:
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _label_of(path: Path, base_name: str) -> str:
    return path.name.split(f"{base_name}.bak-", 1)[-1]


def scan_family(parent: Path, base_name: str) -> List[BackupInfo]:
    """All ``{base_name}.bak-*`` entries under ``parent`` (excluding wal/shm siblings)."""
    if not parent.is_dir():
        return []
    out: List[BackupInfo] = []
    for path in sorted(parent.glob(f"{base_name}.bak-*")):
        label = _label_of(path, base_name)
        if label.endswith("-wal") or label.endswith("-shm"):
            continue  # pruned together with its base file
        out.append(
            BackupInfo(
                path=path,
                label=label,
                is_timestamped=bool(TIMESTAMP_RE.match(label)),
                mtime=path.stat().st_mtime,
                size_bytes=_entry_size(path),
            )
        )
    return out


def plan_family(parent: Path, base_name: str, *, keep: int) -> GroupPlan:
    infos = scan_family(parent, base_name)
    protected = [i for i in infos if not i.is_timestamped]
    timestamped = sorted((i for i in infos if i.is_timestamped), key=lambda i: i.mtime, reverse=True)
    return GroupPlan(
        family=base_name,
        protected=protected,
        kept=timestamped[:keep],
        to_delete=timestamped[keep:],
    )


def _sibling_wal_shm(path: Path) -> List[Path]:
    return [p for p in (Path(str(path) + "-wal"), Path(str(path) + "-shm")) if p.exists()]


def delete_backup(info: BackupInfo) -> List[Path]:
    """Delete one backup (and its wal/shm siblings); return what was removed."""
    removed: List[Path] = []
    targets = [info.path] + _sibling_wal_shm(info.path)
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        removed.append(target)
    return removed


def _fmt_size(n: float) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prune_backups",
        description="Prune stale .bak backups (dry-run by default; deletion needs human review).",
    )
    parser.add_argument("--data-root", type=Path, default=None, help=f"data root (default: {DATA_ROOT})")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help=f"timestamped backups to keep per family (default {DEFAULT_KEEP})")
    parser.add_argument("--execute", action="store_true", help="actually delete (default: dry-run). Review the dry-run list first.")
    args = parser.parse_args(argv)

    if args.keep < 0:
        parser.error("--keep must be >= 0")

    data_root: Path = args.data_root or DATA_ROOT
    families = [
        ("F5_executed", data_root),
        ("finer.project.sqlite3", data_root / "project_memory"),
    ]

    header = "[execute]" if args.execute else "[dry-run]"
    print(f"{header} prune_backups  data_root={data_root}  keep={args.keep}")

    total_delete = 0
    total_bytes = 0
    for base_name, parent in families:
        plan = plan_family(parent, base_name, keep=args.keep)
        print(f"\n=== {base_name}  (protected={len(plan.protected)} kept={len(plan.kept)} delete={len(plan.to_delete)}) ===")
        for info in plan.protected:
            print(f"  PROTECT (named)  {info.path.name}  {_fmt_size(info.size_bytes)}")
        for info in plan.kept:
            print(f"  KEEP (recent)    {info.path.name}  {_fmt_size(info.size_bytes)}")
        for info in plan.to_delete:
            total_delete += 1
            total_bytes += info.size_bytes
            action = "DELETE" if args.execute else "WOULD DELETE"
            print(f"  {action}  {info.path.name}  {_fmt_size(info.size_bytes)}")
            if args.execute:
                delete_backup(info)

    print(f"\n{'deleted' if args.execute else 'would delete'} {total_delete} backup(s), ~{_fmt_size(total_bytes)}")
    if not args.execute and total_delete:
        print("dry-run: nothing deleted. Review the list above, then re-run with --execute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
