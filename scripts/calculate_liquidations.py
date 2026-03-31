#!/usr/bin/env python3
"""CLI script to calculate liquidation levels and store in DuckDB.

Usage:
    python scripts/calculate_liquidations.py --symbol BTCUSDT --model binance_standard
    python scripts/calculate_liquidations.py --symbol BTCUSDT --model ensemble --funding-rate 0.0001
"""

import argparse
import time
from decimal import Decimal

from rich.console import Console
from rich.table import Table

from src.liquidationheatmap.ingestion.db_service import DuckDBService
from src.liquidationheatmap.models.binance_standard import BinanceStandardModel
from src.liquidationheatmap.models.ensemble import EnsembleModel
from src.liquidationheatmap.models.funding_adjusted import FundingAdjustedModel

console = Console()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Calculate liquidation levels and store in DuckDB")
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading pair symbol (default: BTCUSDT)",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["binance_standard", "funding_adjusted", "ensemble"],
        default="binance_standard",
        help="Liquidation model to use",
    )
    parser.add_argument(
        "--funding-rate",
        type=float,
        default=None,
        help="Current funding rate (optional, fetched from DB if not provided)",
    )
    parser.add_argument(
        "--leverage",
        type=int,
        nargs="+",
        default=[5, 10, 25, 50, 100],
        help="Leverage tiers to calculate (default: 5 10 25 50 100)",
    )

    args = parser.parse_args()

    console.print("\n[bold cyan]Liquidation Calculator[/bold cyan]")
    console.print(f"Symbol: {args.symbol}")
    console.print(f"Model: {args.model}")
    console.print(f"Leverage tiers: {args.leverage}\n")

    # Fetch data from DuckDB
    with DuckDBService() as db:
        console.print("[yellow]Fetching data from DuckDB...[/yellow]")
        current_price, open_interest = db.get_historical_latest_open_interest(args.symbol)

        if args.funding_rate is not None:
            funding_rate = Decimal(str(args.funding_rate))
        else:
            funding_rate = db.get_historical_latest_funding_rate(args.symbol)

        console.print(f"✓ Current Price: ${current_price:,.2f}")
        console.print(f"✓ Open Interest: ${open_interest:,.2f}")
        console.print(f"✓ Funding Rate: {funding_rate:.4%}\n")

        # Select model
        if args.model == "ensemble":
            model = EnsembleModel()
        elif args.model == "funding_adjusted":
            model = FundingAdjustedModel()
        else:
            model = BinanceStandardModel()

        # Calculate liquidations
        console.print(f"[yellow]Calculating liquidations with {model.model_name}...[/yellow]")
        start_time = time.time()

        if args.model == "funding_adjusted":
            liquidations = model.calculate_liquidations(
                current_price=current_price,
                open_interest=open_interest,
                symbol=args.symbol,
                leverage_tiers=args.leverage,
                funding_rate=funding_rate,
            )
        else:
            liquidations = model.calculate_liquidations(
                current_price=current_price,
                open_interest=open_interest,
                symbol=args.symbol,
                leverage_tiers=args.leverage,
            )

        calc_time = time.time() - start_time
        console.print(f"✓ Calculated {len(liquidations)} liquidation levels in {calc_time:.3f}s\n")

        # Create liquidation_levels table if not exists
        db.conn.execute("""
            CREATE TABLE IF NOT EXISTS liquidation_levels (
                id BIGINT PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                model VARCHAR(50) NOT NULL,
                price_level DECIMAL(18, 2) NOT NULL,
                liquidation_volume DECIMAL(18, 8) NOT NULL,
                leverage_tier VARCHAR(10),
                side VARCHAR(10) NOT NULL,
                confidence DECIMAL(3, 2) NOT NULL,
                UNIQUE(timestamp, symbol, model, leverage_tier, side)
            )
        """)

        # Insert results
        console.print("[yellow]Storing results in DuckDB...[/yellow]")

        for idx, liq in enumerate(liquidations):
            db.conn.execute(
                """
                INSERT OR IGNORE INTO liquidation_levels VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    idx + 1,
                    liq.timestamp,
                    liq.symbol,
                    model.model_name,
                    float(liq.price_level),
                    float(liq.liquidation_volume),
                    liq.leverage_tier,
                    liq.side,
                    float(liq.confidence),
                ],
            )

        console.print(f"✓ Stored {len(liquidations)} liquidation levels\n")

        # Display summary table
        table = Table(title="Liquidation Levels Summary")
        table.add_column("Leverage", style="cyan")
        table.add_column("Side", style="magenta")
        table.add_column("Price", justify="right", style="green")
        table.add_column("Volume (USDT)", justify="right", style="yellow")
        table.add_column("Confidence", justify="right", style="blue")

        for liq in liquidations[:10]:  # Show first 10
            table.add_row(
                liq.leverage_tier,
                liq.side,
                f"${float(liq.price_level):,.2f}",
                f"${float(liq.liquidation_volume):,.0f}",
                f"{float(liq.confidence):.2%}",
            )

        console.print(table)
        console.print(
            f"\n[green]✓ Complete![/green] Model confidence: {model.confidence_score():.2%}"
        )


if __name__ == "__main__":
    main()
