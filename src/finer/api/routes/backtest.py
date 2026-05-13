"""Backtest API Routes — REST endpoints for backtest operations.

Provides endpoints for:
- Running backtests on KOL trade actions
- Retrieving backtest results
- Comparing multiple KOL strategies
- Managing backtest result storage

Storage location: data/L8_metrics/
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Body, Query
from pydantic import BaseModel, Field

from finer.paths import DATA_ROOT
from finer.backtest.engine import BacktestConfig, BacktestEngine
from finer.backtest.prices import CachedPriceProvider, MockPriceProvider
from finer.errors.codes import ErrorCode
from finer.errors.exceptions import FinerError

logger = logging.getLogger(__name__)

router = APIRouter()

# Storage directory for backtest results
L8_METRICS_DIR = DATA_ROOT / "L8_metrics"
L8_METRICS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Request/Response Models
# =============================================================================

class BacktestRequest(BaseModel):
    """Request to run a backtest."""
    # Trade actions to backtest
    actions: List[Dict[str, Any]] = Field(
        ...,
        description="List of trade actions (each with timestamp, ticker, direction, etc.)"
    )

    # Price data (optional, will use provider if not provided)
    price_data: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Price data as list of {date, ticker, open, high, low, close, volume} dicts"
    )

    # Configuration
    initial_capital: float = Field(100000.0, description="Starting capital")
    commission_pct: float = Field(0.001, description="Commission rate (0.1% default)")
    slippage_pct: float = Field(0.0005, description="Slippage rate (0.05% default)")
    default_position_pct: float = Field(0.1, description="Default position size (10% default)")
    max_position_pct: float = Field(0.25, description="Max position size (25% default)")

    # Date range
    start_date: Optional[str] = Field(None, description="Start date (ISO format)")
    end_date: Optional[str] = Field(None, description="End date (ISO format)")

    # Identification
    kol_id: Optional[str] = Field(None, description="KOL ID for attribution")
    backtest_name: Optional[str] = Field(None, description="Human-readable name")


class PriceDataRequest(BaseModel):
    """Request for price data."""
    ticker: str = Field(..., description="Ticker symbol")
    start_date: str = Field(..., description="Start date (ISO format)")
    end_date: str = Field(..., description="End date (ISO format)")
    use_mock: bool = Field(False, description="Use mock data instead of API")


class BacktestSummary(BaseModel):
    """Summary of a backtest result."""
    backtest_id: str
    kol_id: Optional[str]
    start_date: str
    end_date: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    created_at: str


# =============================================================================
# Helper Functions
# =============================================================================

def _save_backtest_result(result, kol_id: Optional[str] = None) -> Path:
    """Save backtest result to file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backtest_{result.backtest_id}_{timestamp}.json"
    if kol_id:
        filename = f"backtest_{kol_id}_{result.backtest_id}_{timestamp}.json"

    filepath = L8_METRICS_DIR / filename

    # Convert to dict for JSON serialization
    data = result.model_dump(mode='json')

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"Saved backtest result to {filepath}")
    return filepath


def _load_backtest_result(backtest_id: str):
    """Load backtest result from file."""
    from finer.backtest.engine import BacktestResult

    # Find file with matching backtest_id
    for filepath in L8_METRICS_DIR.glob(f"backtest_*{backtest_id}*.json"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return BacktestResult.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load backtest {filepath}: {e}")

    return None


def _list_backtest_files() -> List[Path]:
    """List all backtest result files."""
    return list(L8_METRICS_DIR.glob("backtest_*.json"))


def _prepare_price_data(
    price_data: Optional[List[Dict[str, Any]]],
    actions: List[Dict[str, Any]],
    start_date: Optional[str],
    end_date: Optional[str],
) -> pd.DataFrame:
    """Prepare price DataFrame for backtest."""
    if price_data:
        # Use provided price data
        df = pd.DataFrame(price_data)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        return df

    # Generate mock price data
    provider = MockPriceProvider()

    # Determine tickers from actions
    tickers = set()
    for action in actions:
        ticker = action.get('ticker')
        if ticker:
            tickers.add(ticker)

    # Determine date range
    if not start_date or not end_date:
        # Extract from actions
        timestamps = []
        for action in actions:
            ts = action.get('timestamp')
            if ts:
                try:
                    timestamps.append(pd.to_datetime(ts))
                except:
                    pass

        if timestamps:
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            start_date = start_date or min_ts.strftime('%Y-%m-%d')
            end_date = end_date or (max_ts + pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        else:
            # Default to last 6 months
            end_date = end_date or datetime.now().strftime('%Y-%m-%d')
            start_date = start_date or (datetime.now() - pd.Timedelta(days=180)).strftime('%Y-%m-%d')

    # Generate price data
    rows = []
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    current = start_dt
    while current <= end_dt:
        date_str = current.strftime('%Y-%m-%d')
        for ticker in tickers:
            price = provider.get_price(ticker, date_str)
            if price:
                rows.append({
                    'date': current,
                    'ticker': ticker,
                    'open': price * 0.99,
                    'high': price * 1.01,
                    'low': price * 0.98,
                    'close': price,
                    'volume': 1000000,
                })
        current += pd.Timedelta(days=1)

    return pd.DataFrame(rows)


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/run")
async def run_backtest(request: BacktestRequest) -> Dict[str, Any]:
    """Run a backtest on trade actions.

    This is the main entry point for backtesting KOL strategies.

    Args:
        request: Backtest request with actions, price data, and config

    Returns:
        Backtest result with performance metrics
    """
    if not request.actions:
        raise FinerError(ErrorCode.F8_IN_001, "No actions provided", stage="F8", operation="backtest_run", retryable=False)

    try:
        # Create config
        config = BacktestConfig(
            initial_capital=request.initial_capital,
            commission_pct=request.commission_pct,
            slippage_pct=request.slippage_pct,
            default_position_pct=request.default_position_pct,
            max_position_pct=request.max_position_pct,
        )

        # Prepare price data
        price_df = _prepare_price_data(
            price_data=request.price_data,
            actions=request.actions,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        if price_df.empty:
            raise FinerError(ErrorCode.F8_EXT_001, "No price data available", stage="F8", operation="price_fetch", retryable=True)

        # Create engine and run
        engine = BacktestEngine(config)

        start_dt = pd.to_datetime(request.start_date) if request.start_date else None
        end_dt = pd.to_datetime(request.end_date) if request.end_date else None

        result = engine.run_backtest(
            actions=request.actions,
            price_data=price_df,
            start_date=start_dt,
            end_date=end_dt,
        )

        # Save result
        filepath = _save_backtest_result(result, request.kol_id)

        # Return result
        return {
            "ok": True,
            "data": result.model_dump(mode='json'),
            "saved_to": str(filepath),
        }

    except FinerError:
        raise
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        raise FinerError(ErrorCode.F8_INT_001, f"Backtest failed: {str(e)}", stage="F8", operation="backtest_run", retryable=False, cause=e)


@router.get("/results/{backtest_id}")
async def get_backtest_result(backtest_id: str) -> Dict[str, Any]:
    """Get a specific backtest result.

    Args:
        backtest_id: Backtest identifier

    Returns:
        Backtest result
    """
    result = _load_backtest_result(backtest_id)

    if not result:
        raise FinerError(ErrorCode.F8_NTF_001, f"Backtest not found: {backtest_id}", stage="F8", operation="get_result", retryable=False)

    return {
        "ok": True,
        "data": result.model_dump(mode='json'),
    }


@router.get("/results")
async def list_backtest_results(
    kol_id: Optional[str] = Query(None, description="Filter by KOL ID"),
    limit: int = Query(20, description="Maximum results to return"),
    sort_by: str = Query("created_at", description="Sort field"),
) -> Dict[str, Any]:
    """List backtest results.

    Args:
        kol_id: Optional filter by KOL ID
        limit: Maximum number of results
        sort_by: Field to sort by

    Returns:
        List of backtest summaries
    """
    results = []

    for filepath in _list_backtest_files()[:limit * 2]:  # Read more for filtering
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Filter by KOL ID if provided
            file_kol_id = filepath.stem.split('_')[1] if len(filepath.stem.split('_')) > 1 else None
            if kol_id and file_kol_id != kol_id:
                continue

            # Extract summary
            summary = {
                "backtest_id": data.get('backtest_id', ''),
                "kol_id": file_kol_id,
                "start_date": data.get('start_date', ''),
                "end_date": data.get('end_date', ''),
                "total_return": data.get('total_return', 0.0),
                "sharpe_ratio": data.get('sharpe_ratio', 0.0),
                "max_drawdown": data.get('max_drawdown', 0.0),
                "win_rate": data.get('win_rate', 0.0),
                "total_trades": data.get('total_trades', 0),
                "created_at": data.get('run_timestamp', ''),
                "filepath": str(filepath),
            }
            results.append(summary)

        except Exception as e:
            logger.warning(f"Failed to read {filepath}: {e}")

    # Sort
    if sort_by in ['total_return', 'sharpe_ratio', 'win_rate']:
        results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    elif sort_by == 'created_at':
        results.sort(key=lambda x: x.get(sort_by, ''), reverse=True)

    # Limit
    results = results[:limit]

    return {
        "ok": True,
        "data": {
            "results": results,
            "total": len(results),
        },
    }


@router.delete("/results/{backtest_id}")
async def delete_backtest_result(backtest_id: str) -> Dict[str, Any]:
    """Delete a backtest result.

    Args:
        backtest_id: Backtest identifier

    Returns:
        Deletion status
    """
    deleted = False

    for filepath in L8_METRICS_DIR.glob(f"backtest_*{backtest_id}*.json"):
        try:
            filepath.unlink()
            deleted = True
            logger.info(f"Deleted backtest file: {filepath}")
        except Exception as e:
            logger.error(f"Failed to delete {filepath}: {e}")

    if not deleted:
        raise FinerError(ErrorCode.F8_NTF_001, f"Backtest not found: {backtest_id}", stage="F8", operation="delete_result", retryable=False)

    return {
        "ok": True,
        "data": {
            "deleted": backtest_id,
            "message": "Backtest result deleted",
        },
    }


@router.post("/compare")
async def compare_strategies(
    kol_actions: Dict[str, List[Dict[str, Any]]] = Body(...),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 100000.0,
) -> Dict[str, Any]:
    """Compare backtest results across multiple KOLs.

    Args:
        kol_actions: Dict mapping KOL ID to list of actions
        start_date: Start date for all backtests
        end_date: End date for all backtests
        initial_capital: Starting capital

    Returns:
        Comparison results for all KOLs
    """
    if not kol_actions:
        raise FinerError(ErrorCode.F8_IN_001, "No KOL actions provided", stage="F8", operation="compare", retryable=False)

    results = {}
    all_actions = []
    all_tickers = set()

    # Collect all tickers and actions
    for kol_id, actions in kol_actions.items():
        all_actions.extend(actions)
        for action in actions:
            ticker = action.get('ticker')
            if ticker:
                all_tickers.add(ticker)

    # Prepare price data for all tickers
    price_df = _prepare_price_data(
        price_data=None,
        actions=all_actions,
        start_date=start_date,
        end_date=end_date,
    )

    # Run backtest for each KOL
    config = BacktestConfig(initial_capital=initial_capital)
    engine = BacktestEngine(config)

    start_dt = pd.to_datetime(start_date) if start_date else None
    end_dt = pd.to_datetime(end_date) if end_date else None

    for kol_id, actions in kol_actions.items():
        try:
            result = engine.run_backtest(
                actions=actions,
                price_data=price_df,
                start_date=start_dt,
                end_date=end_dt,
            )

            # Save result
            _save_backtest_result(result, kol_id)

            # Store summary
            results[kol_id] = {
                "total_return": result.total_return,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown": result.max_drawdown,
                "win_rate": result.win_rate,
                "total_trades": result.total_trades,
                "backtest_id": result.backtest_id,
            }

        except Exception as e:
            logger.error(f"Failed to backtest KOL {kol_id}: {e}")
            results[kol_id] = {"error": str(e)}

    # Sort by total return
    sorted_results = sorted(
        results.items(),
        key=lambda x: x[1].get('total_return', float('-inf')),
        reverse=True,
    )

    return {
        "ok": True,
        "data": {
            "comparison": dict(sorted_results),
            "ranking": [kol_id for kol_id, _ in sorted_results if 'error' not in _],
            "best_performer": sorted_results[0][0] if sorted_results and 'error' not in sorted_results[0][1] else None,
        },
    }


@router.post("/prices")
async def get_price_data(request: PriceDataRequest) -> Dict[str, Any]:
    """Get price data for a ticker.

    Args:
        request: Price data request

    Returns:
        Price series
    """
    try:
        if request.use_mock:
            provider = MockPriceProvider()
        else:
            provider = CachedPriceProvider(fallback_to_mock=True)

        prices = provider.get_prices(
            ticker=request.ticker,
            start=request.start_date,
            end=request.end_date,
        )

        return {
            "ok": True,
            "data": {
                "ticker": request.ticker,
                "prices": prices,
                "count": len(prices),
            },
        }

    except Exception as e:
        logger.error(f"Failed to get prices: {e}")
        raise FinerError(ErrorCode.F8_EXT_001, f"Failed to get prices: {str(e)}", stage="F8", operation="price_fetch", retryable=True, cause=e)


@router.get("/health")
async def backtest_health() -> Dict[str, Any]:
    """Check backtest module health."""
    # Check storage
    storage_ok = L8_METRICS_DIR.exists()

    # Count existing results
    result_count = len(_list_backtest_files())

    return {
        "ok": True,
        "data": {
            "status": "healthy" if storage_ok else "degraded",
            "storage_dir": str(L8_METRICS_DIR),
            "storage_ok": storage_ok,
            "result_count": result_count,
        },
    }
