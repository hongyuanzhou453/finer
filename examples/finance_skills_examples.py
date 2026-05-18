"""
Finance Skills Integration Examples (P0)

This script demonstrates how to use the new Finance Skills integration
for market data enrichment.

Requirements:
- Set FINANCE_SKILLS_API_KEY environment variable
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from finer.services.finance_skills_client import FinanceSkillsClient, SkillName
from finer.enrichment.market_context import MarketContextEnricher, PriceRangeValidator
from finer.schemas.event import EventWithActions, TradingAction
from finer.schemas.enriched_event import MarketDataSnapshot


async def example_basic_client():
    """Example 1: Basic Finance Skills Client usage."""
    print("\n=== Example 1: Basic Client Usage ===\n")

    client = FinanceSkillsClient()

    if not os.getenv("FINANCE_SKILLS_API_KEY"):
        print("Warning: FINANCE_SKILLS_API_KEY not set. Using mock data.")
        return

    print("Fetching market data for AAPL...")
    data = await client.get_market_data("AAPL")

    if data:
        print(f"Current price: ${data.get('current_price')}")
        print(f"Change: {data.get('change_pct')}%")
        print(f"52-week range: ${data.get('52wk_low')} - ${data.get('52wk_high')}")

    await client.close()


async def example_batch_calls():
    """Example 2: Batch parallel API calls."""
    print("\n=== Example 2: Batch Parallel Calls ===\n")

    if not os.getenv("FINANCE_SKILLS_API_KEY"):
        print("Skipping - no API key")
        return

    client = FinanceSkillsClient()

    tickers = ["AAPL", "TSLA", "NVDA"]

    print(f"Fetching data for {tickers} in parallel...")
    results = await client.call_batch([
        (SkillName.YFINANCE_DATA, {"ticker": ticker})
        for ticker in tickers
    ])

    for ticker, data in zip(tickers, results):
        if data:
            print(f"{ticker}: ${data.get('current_price', 'N/A')}")
        else:
            print(f"{ticker}: Failed to fetch")

    await client.close()


async def example_price_validation():
    """Example 3: Price range validation."""
    print("\n=== Example 3: Price Validation ===\n")

    validator = PriceRangeValidator()

    market_data = MarketDataSnapshot(
        ticker="AAPL",
        current_price=175.0,
        high_52wk=199.62,
        low_52wk=124.17,
    )

    action = TradingAction(
        action_type="long",
        target_price_low=170.0,
        target_price_high=200.0,
        confidence=0.8,
    )

    result = validator.validate(action, market_data)

    print(f"Action: {action.action_type}")
    print(f"Target range: ${action.target_price_low} - ${action.target_price_high}")
    print(f"Current price: ${market_data.current_price}")
    print(f"Valid: {result.is_valid}")
    if result.issues:
        print(f"Issues: {result.issues}")
    if result.warnings:
        print(f"Warnings: {result.warnings}")
    print(f"Price position: {result.price_position}")


async def example_enrichment():
    """Example 4: Full event enrichment."""
    print("\n=== Example 4: Event Enrichment ===\n")

    event = EventWithActions(
        ticker="AAPL",
        direction="bullish",
        evidence_text="AAPL at 170 is a good entry point. Target 190-200.",
        action_chain=[
            TradingAction(
                action_type="long",
                target_price_low=170.0,
                target_price_high=200.0,
                confidence=0.85,
            )
        ],
    )

    enricher = MarketContextEnricher()

    print(f"Enriching event for {event.ticker}...")
    enriched, issues = await enricher.enrich_event(event)

    print(f"Original confidence: {enriched.base_confidence:.2f}")
    print(f"Market data confidence boost: {enriched.market_data_confidence:.2f}")
    print(f"Overall confidence: {enriched.overall_confidence:.2f}")

    if enriched.market_snapshot:
        snapshot = enriched.market_snapshot
        print(f"\nMarket snapshot:")
        print(f"  Current: ${snapshot.current_price}")
        print(f"  52-week range: ${snapshot.low_52wk} - ${snapshot.high_52wk}")

    if issues:
        print(f"\nValidation issues: {issues}")


async def example_context_manager():
    """Example 5: Using async context manager."""
    print("\n=== Example 5: Context Manager ===\n")

    if not os.getenv("FINANCE_SKILLS_API_KEY"):
        print("Skipping - no API key")
        return

    async with FinanceSkillsClient() as client:
        data = await client.get_market_data("MSFT")
        if data:
            print(f"MSFT current price: ${data.get('current_price')}")


async def main():
    """Run all examples."""
    print("=" * 60)
    print("Finance Skills Integration Examples (P0)")
    print("=" * 60)

    await example_basic_client()
    await example_batch_calls()
    await example_price_validation()
    await example_enrichment()
    await example_context_manager()

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
