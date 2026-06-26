from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path

from finer.pipeline import dry_run_pipeline, init_storage, register_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finer",
        description="Finer — Investment Research Automation System",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── Existing commands ──────────────────────────────────────
    init_cmd = subparsers.add_parser("init-storage", help="Create canonical data directories")
    init_cmd.add_argument("--root", type=Path, default=Path.cwd())

    register_cmd = subparsers.add_parser(
        "register-dir",
        help="Register source files from a directory into content manifests",
    )
    register_cmd.add_argument("--root", type=Path, default=Path.cwd())
    register_cmd.add_argument("--creator", required=True)
    register_cmd.add_argument("--content-type", required=True)
    register_cmd.add_argument("--source-dir", type=Path, required=True)
    register_cmd.add_argument("--pattern", default="*")
    register_cmd.add_argument("--dry-run", action="store_true")

    dry_cmd = subparsers.add_parser(
        "dry-run",
        help="Run the current skeleton pipeline without OCR/ASR backends",
    )
    dry_cmd.add_argument("--root", type=Path, default=Path.cwd())

    # ── Feishu file management commands ────────────────────────
    feishu_sync_cmd = subparsers.add_parser(
        "feishu-sync",
        help="Pull new files from watched Feishu chats, classify, archive, and sync to NLM",
    )
    feishu_sync_cmd.add_argument("--root", type=Path, default=Path.cwd())
    feishu_sync_cmd.add_argument("--dry-run", action="store_true", help="Preview without downloading")
    feishu_sync_cmd.add_argument("--no-nlm", action="store_true", help="Skip NotebookLM sync")

    feishu_watch_cmd = subparsers.add_parser(
        "feishu-watch",
        help="Continuously poll Feishu chats for new files (daemon mode)",
    )
    feishu_watch_cmd.add_argument("--root", type=Path, default=Path.cwd())
    feishu_watch_cmd.add_argument("--interval", type=int, default=300, help="Poll interval in seconds")
    feishu_watch_cmd.add_argument("--no-nlm", action="store_true", help="Skip NotebookLM sync")

    inbox_cmd = subparsers.add_parser(
        "inbox-status",
        help="Show current inbox contents and sync state",
    )
    inbox_cmd.add_argument("--root", type=Path, default=Path.cwd())

    # ── Market data commands ────────────────────────────────────
    md_cmd = subparsers.add_parser(
        "market-data",
        help="Tushare market data sync and status",
    )
    md_sub = md_cmd.add_subparsers(dest="md_command", required=True)

    md_sync = md_sub.add_parser("sync", help="Sync market data from Tushare")
    md_sync.add_argument("--all", action="store_true", help="Sync all tables")
    md_sync.add_argument(
        "--table",
        choices=["trade_cal", "basic", "daily_kline", "adj_factor"],
        help="Sync a specific table",
    )
    md_sync.add_argument("--start", help="Start date (YYYYMMDD)")
    md_sync.add_argument("--end", help="End date (YYYYMMDD)")
    md_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan sync without requiring TUSHARE_TOKEN, network calls, or writes",
    )

    md_status = md_sub.add_parser("status", help="Show sync status")

    # ── Backtest commands ──────────────────────────────────────
    bt_cmd = subparsers.add_parser(
        "backtest",
        help="Run and manage backtests",
    )
    bt_sub = bt_cmd.add_subparsers(dest="bt_command", required=True)

    bt_run = bt_sub.add_parser("run", help="Run a backtest from TradeAction files")
    bt_run.add_argument("--actions", type=Path, required=True, help="Path to TradeAction JSON file or directory")
    bt_run.add_argument("--start", help="Start date (YYYYMMDD or YYYY-MM-DD)")
    bt_run.add_argument("--end", help="End date (YYYYMMDD or YYYY-MM-DD)")
    bt_run.add_argument("--capital", type=float, default=100000.0, help="Initial capital (default: 100000)")
    bt_run.add_argument("--adj", default="qfq", choices=["qfq", "hfq", "none"], help="Price adjustment mode")
    bt_run.add_argument("--no-snapshots", action="store_true", help="Omit portfolio snapshots from saved result")

    bt_status = bt_sub.add_parser("status", help="List saved backtest results")

    bt_show = bt_sub.add_parser("show", help="Show details of a saved backtest")
    bt_show.add_argument("backtest_id", help="Backtest ID to show")

    return parser


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _cmd_feishu_sync(args: argparse.Namespace) -> dict:
    from finer.ingestion.orchestrator import sync_all_chats
    return sync_all_chats(
        root=args.root,
        dry_run=args.dry_run,
        auto_nlm=not args.no_nlm,
    )


def _cmd_feishu_watch(args: argparse.Namespace) -> dict:
    from finer.ingestion.orchestrator import sync_all_chats

    interval = args.interval
    auto_nlm = not args.no_nlm
    running = True

    def _sigint_handler(sig, frame):
        nonlocal running
        print("\n⏹  Stopping watcher...")
        running = False

    signal.signal(signal.SIGINT, _sigint_handler)
    print(f"👁  Watching Feishu chats (interval: {interval}s, NLM: {auto_nlm})")
    print("   Press Ctrl+C to stop.\n")

    cycle = 0
    while running:
        cycle += 1
        print(f"── Cycle {cycle} ──")
        try:
            result = sync_all_chats(root=args.root, auto_nlm=auto_nlm)
            total_files = sum(
                r.get("files_processed", 0) for r in result.get("results", [])
            )
            print(f"   Processed {total_files} files across {result['chats_synced']} chats")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        if running:
            for _ in range(interval):
                if not running:
                    break
                time.sleep(1)

    return {"status": "stopped", "cycles": cycle}


def _cmd_inbox_status(args: argparse.Namespace) -> dict:
    import json as json_mod
    from finer.config import load_feishu_config

    root = args.root
    inbox_dir = root / "data" / "inbox"
    
    # List inbox files
    inbox_files = []
    if inbox_dir.exists():
        inbox_files = [
            {"name": f.name, "size_kb": f.stat().st_size / 1024}
            for f in sorted(inbox_dir.iterdir())
            if f.is_file() and not f.name.startswith(".")
        ]

    # Load sync state
    try:
        config = load_feishu_config(root)
        state_file = root / config.get("feishu", {}).get(
            "state_file", "data/.feishu_sync_state.json"
        )
        if state_file.exists():
            sync_state = json_mod.loads(state_file.read_text())
        else:
            sync_state = {}
    except FileNotFoundError:
        sync_state = {"error": "feishu.yaml not found"}

    return {
        "inbox_dir": str(inbox_dir),
        "pending_files": len(inbox_files),
        "files": inbox_files,
        "sync_state": sync_state,
    }


def _cmd_market_data_sync(args: argparse.Namespace) -> dict:
    from finer.market_data.config import load_market_data_config
    from finer.market_data.service import MarketDataSyncService
    from finer.market_data.status import build_sync_plan

    start = _parse_date_arg(args.start) if args.start else None
    end = _parse_date_arg(args.end) if args.end else None
    if not args.all and not args.table:
        return {"error": "specify --all or --table"}
    if getattr(args, "dry_run", False):
        return build_sync_plan(
            table=args.table,
            sync_all=args.all,
            start=start,
            end=end,
        )

    try:
        config = load_market_data_config(require_token=True)
    except ValueError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "token_configured": False,
            "hint": "Set TUSHARE_TOKEN for real sync, or run with --dry-run to inspect the local plan.",
        }

    try:
        svc_context = MarketDataSyncService(config)
    except ImportError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "token_configured": True,
            "hint": "Install market data extras before real sync: pip install 'finer[market-data]'",
        }

    with svc_context as svc:
        if args.all:
            return svc.sync_all()
        elif args.table == "trade_cal":
            svc.sync_trade_cal()
            return {"trade_cal": "ok"}
        elif args.table == "basic":
            svc.sync_basic()
            return {"basic": "ok"}
        elif args.table == "daily_kline":
            svc.sync_daily_kline(start, end)
            return {"daily_kline": "ok"}
        elif args.table == "adj_factor":
            svc.sync_adj_factor(start, end)
            return {"adj_factor": "ok"}
        else:
            return {"error": "specify --all or --table"}


def _cmd_market_data_status(_args: argparse.Namespace) -> dict:
    from finer.market_data.status import inspect_market_data

    return inspect_market_data()


def _cmd_backtest_run(args: argparse.Namespace) -> dict:
    import json as json_mod
    from finer.backtest.engine import BacktestEngine, BacktestConfig
    from finer.backtest.prices import PriceSnapshotMaterializer
    from finer.backtest.converter import trade_actions_to_records
    from finer.backtest.storage import save_backtest_result
    from finer.schemas.trade_action import TradeAction

    # Load TradeActions
    actions_path = Path(args.actions)
    trade_actions: list[TradeAction] = []

    if actions_path.is_file():
        data = json_mod.loads(actions_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                trade_actions.append(TradeAction.model_validate(item))
        else:
            trade_actions.append(TradeAction.model_validate(data))
    elif actions_path.is_dir():
        for f in sorted(actions_path.glob("*.json")):
            data = json_mod.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    trade_actions.append(TradeAction.model_validate(item))
            else:
                trade_actions.append(TradeAction.model_validate(data))
    else:
        return {"error": f"Path not found: {actions_path}"}

    if not trade_actions:
        return {"error": "No TradeActions found"}

    # Convert to engine records
    records = trade_actions_to_records(trade_actions)
    if not records:
        return {"error": "No backtestable TradeActions (all neutral/watch/hold)"}

    # Materialize price data
    adj = args.adj if args.adj != "none" else None
    materializer = PriceSnapshotMaterializer(adj=adj or "qfq")
    price_df = materializer.materialize_from_actions(
        records, lookback_days=5, lookahead_days=35,
    )

    if price_df.empty:
        return {"error": "No price data available for the tickers in actions"}

    # Run backtest
    config = BacktestConfig(initial_capital=args.capital)
    engine = BacktestEngine(config)
    result = engine.run_backtest(
        actions=records,
        price_data=price_df,
        start_date=_parse_date_arg(args.start) if args.start else None,
        end_date=_parse_date_arg(args.end) if args.end else None,
    )

    # Persist
    result_dict = result.model_dump(mode="json")
    saved_path = save_backtest_result(
        result_dict, include_snapshots=not args.no_snapshots,
    )

    return {
        "backtest_id": result.backtest_id,
        "total_return": round(result.total_return * 100, 2),
        "sharpe_ratio": round(result.sharpe_ratio, 3),
        "max_drawdown": round(result.max_drawdown * 100, 2),
        "total_trades": result.total_trades,
        "win_rate": round(result.win_rate * 100, 1),
        "saved_to": str(saved_path),
    }


def _cmd_backtest_status(_args: argparse.Namespace) -> dict:
    from finer.backtest.storage import list_backtest_results
    results = list_backtest_results()
    return {"total": len(results), "results": results}


def _cmd_backtest_show(args: argparse.Namespace) -> dict:
    from finer.backtest.storage import load_backtest_result
    result = load_backtest_result(args.backtest_id)
    if result is None:
        return {"error": f"Backtest not found: {args.backtest_id}"}
    return result


def _parse_date_arg(value: str) -> "date":
    from datetime import date as _date
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return _date.fromisoformat(value) if "-" in value else _date(
                int(value[:4]), int(value[4:6]), int(value[6:8])
            )
        except (ValueError, IndexError):
            continue
    raise ValueError(f"invalid date: {value}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _setup_logging(getattr(args, "verbose", False))

    if args.command == "init-storage":
        result = init_storage(args.root)
    elif args.command == "register-dir":
        result = register_directory(
            root=args.root,
            creator_id=args.creator,
            content_type=args.content_type,
            source_dir=args.source_dir,
            pattern=args.pattern,
            dry_run=args.dry_run,
        )
    elif args.command == "dry-run":
        result = dry_run_pipeline(args.root)
    elif args.command == "feishu-sync":
        result = _cmd_feishu_sync(args)
    elif args.command == "feishu-watch":
        result = _cmd_feishu_watch(args)
    elif args.command == "inbox-status":
        result = _cmd_inbox_status(args)
    elif args.command == "market-data":
        if args.md_command == "sync":
            result = _cmd_market_data_sync(args)
        elif args.md_command == "status":
            result = _cmd_market_data_status(args)
        else:
            parser.error(f"unknown market-data subcommand: {args.md_command}")
            return
    elif args.command == "backtest":
        if args.bt_command == "run":
            result = _cmd_backtest_run(args)
        elif args.bt_command == "status":
            result = _cmd_backtest_status(args)
        elif args.bt_command == "show":
            result = _cmd_backtest_show(args)
        else:
            parser.error(f"unknown backtest subcommand: {args.bt_command}")
            return
    else:
        parser.error(f"unknown command: {args.command}")
        return

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
