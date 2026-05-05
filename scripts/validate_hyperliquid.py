#!/usr/bin/env python3
"""Legacy Hyperliquid liquidation validation script.

This script used to assume public Hyperliquid WebSocket trades exposed
realized liquidation flags. That path is unsupported in the active runtime.
Use `scripts/ingest_hl_fills.py` over `node_fills_by_block` for realized
liquidations and compare those outcomes against the sidecar/predicted zones.

Usage:
    python scripts/validate_hyperliquid.py --duration 3600  # 1 hour
    python scripts/validate_hyperliquid.py --duration 86400 --output data/validation/  # 24h
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
UNSUPPORTED_REASON = (
    "Public Hyperliquid liquidation collection is unsupported. Use "
    "scripts/ingest_hl_fills.py against node_fills_by_block for realized liquidations."
)


class HyperliquidValidator:
    """Validates Hyperliquid liquidation data against predicted zones."""

    def __init__(self, output_dir: str = "data/validation"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.collected: list[object] = []
        self.predicted_zones: list[dict] = []

    def collect_liquidations(self, duration_seconds: int) -> None:
        """Fail fast with the supported data-source guidance.

        Args:
            duration_seconds: How long to collect data
        """
        logger.error(
            "%s Requested duration was %ss.",
            UNSUPPORTED_REASON,
            duration_seconds,
        )
        raise SystemExit(2)

    def load_predicted_zones(self, zones_file: str | None = None) -> None:
        """Load predicted liquidation zones from file or API.

        Args:
            zones_file: Optional path to zones JSON file
        """
        if zones_file and Path(zones_file).exists():
            with open(zones_file) as f:
                self.predicted_zones = json.load(f)
            logger.info(f"Loaded {len(self.predicted_zones)} predicted zones")
        else:
            # TODO: Load from API /liquidations/heatmap or clusters endpoint
            logger.warning("No zones file provided - using empty zones list")
            self.predicted_zones = []

    def calculate_hit_rate(self) -> dict:
        """Calculate hit rate: what % of liquidations fell within predicted zones.

        Returns:
            Dict with hit rate metrics
        """
        if not self.collected:
            return {
                "hit_rate": 0.0,
                "hits": 0,
                "misses": 0,
                "total": 0,
                "zone_count": len(self.predicted_zones),
            }

        hits = 0
        misses = 0

        for liq in self.collected:
            in_zone = self._is_in_predicted_zone(liq.price)
            if in_zone:
                hits += 1
            else:
                misses += 1

        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0.0

        return {
            "hit_rate": hit_rate,
            "hits": hits,
            "misses": misses,
            "total": total,
            "zone_count": len(self.predicted_zones),
        }

    def _is_in_predicted_zone(self, price: float) -> bool:
        """Check if price falls within any predicted zone.

        Args:
            price: Liquidation price to check

        Returns:
            True if price is in a predicted zone
        """
        for zone in self.predicted_zones:
            price_min = zone.get("price_min", 0)
            price_max = zone.get("price_max", 0)
            if price_min <= price <= price_max:
                return True
        return False

    def save_results(self, results: dict) -> str:
        """Save validation results to JSONL file.

        Args:
            results: Validation results to save

        Returns:
            Path to saved file
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"hyperliquid_validation_{timestamp}.jsonl"

        # Save summary
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "exchange": "hyperliquid",
            "duration_collected": len(self.collected),
            **results,
        }

        with open(output_file, "w") as f:
            f.write(json.dumps(summary) + "\n")

            # Save individual liquidations for analysis
            for liq in self.collected:
                f.write(
                    json.dumps(
                        {
                            "type": "liquidation",
                            "timestamp": liq.timestamp.isoformat(),
                            "symbol": liq.symbol,
                            "side": liq.side,
                            "price": liq.price,
                            "quantity": liq.quantity,
                            "in_zone": self._is_in_predicted_zone(liq.price),
                        }
                    )
                    + "\n"
                )

        logger.info(f"Results saved to {output_file}")
        return str(output_file)


def main():
    parser = argparse.ArgumentParser(description="Validate Hyperliquid liquidation data")
    parser.add_argument(
        "--duration",
        type=int,
        default=3600,
        help="Collection duration in seconds (default: 3600 = 1 hour)",
    )
    parser.add_argument(
        "--zones-file",
        type=str,
        help="Path to predicted zones JSON file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/validation",
        help="Output directory for results",
    )
    args = parser.parse_args()

    validator = HyperliquidValidator(output_dir=args.output)

    # Load predicted zones
    validator.load_predicted_zones(args.zones_file)

    # Collect liquidations
    validator.collect_liquidations(args.duration)

    # Calculate hit rate
    results = validator.calculate_hit_rate()

    # Report results
    logger.info("=" * 50)
    logger.info("HYPERLIQUID VALIDATION RESULTS")
    logger.info("=" * 50)
    logger.info(f"Total liquidations collected: {results['total']}")
    logger.info(f"Hits (in predicted zone): {results['hits']}")
    logger.info(f"Misses (outside zones): {results['misses']}")
    logger.info(f"Predicted zones loaded: {results['zone_count']}")
    logger.info(f"HIT RATE: {results['hit_rate']:.1f}%")
    logger.info("=" * 50)

    # Check against 60% target
    if results["hit_rate"] >= 60:
        logger.info("PASS: Hit rate meets 60% target")
    else:
        logger.warning(f"FAIL: Hit rate {results['hit_rate']:.1f}% below 60% target")

    # Save results
    validator.save_results(results)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        logger.error("Hyperliquid validation failed: %s", exc)
        sys.exit(1)
