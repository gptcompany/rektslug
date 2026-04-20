#!/usr/bin/env python3
"""Publish liquidation signals from the latest Hyperliquid expert snapshot.

Reads the most recent expert artifact, extracts top-N liquidation levels
closest to the reference price, and publishes them as signals to Redis.

Usage:
    REDIS_HOST=172.20.0.4 uv run python scripts/publish_signals_from_snapshot.py
    REDIS_HOST=172.20.0.4 uv run python scripts/publish_signals_from_snapshot.py --symbol ETHUSDT --top-n 3
"""

import argparse
import json
import logging
from pathlib import Path

from src.liquidationheatmap.signals.publisher import SignalPublisher

logger = logging.getLogger(__name__)

SNAPSHOTS_DIR = Path("data/validation/expert_snapshots/hyperliquid")


def find_latest_artifact(symbol: str, expert_id: str = "v1") -> Path | None:
    """Find the most recent artifact for a symbol."""
    manifests_dir = SNAPSHOTS_DIR / "manifests" / symbol
    if not manifests_dir.exists():
        return None
    manifests = sorted(manifests_dir.glob("*.json"))
    if not manifests:
        return None
    latest_ts = manifests[-1].stem
    artifact = SNAPSHOTS_DIR / "artifacts" / symbol / latest_ts / f"{expert_id}.json"
    return artifact if artifact.exists() else None


def extract_top_signals(artifact_path: Path, top_n: int = 5):
    """Extract top-N liquidation levels closest to reference price."""
    with open(artifact_path) as f:
        data = json.load(f)

    ref_price = data["reference_price"]
    symbol = data["symbol"]
    signals = []

    for side, dist_key in [("long", "long_distribution"), ("short", "short_distribution")]:
        distribution = data.get(dist_key, {})
        # Sort by proximity to reference price, filter significant volume
        levels = []
        for price_str, volume in distribution.items():
            price = float(price_str)
            if volume > 1000:  # minimum volume threshold
                distance = abs(price - ref_price) / ref_price
                levels.append((price, volume, distance))
        levels.sort(key=lambda x: x[2])  # closest first

        for price, volume, distance in levels[:top_n]:
            # Confidence based on volume and proximity
            # Higher volume + closer to price = higher confidence
            max_vol = max(v for _, v, _ in levels[:top_n]) if levels else 1
            vol_score = min(volume / max_vol, 1.0)
            prox_score = max(1.0 - distance * 10, 0.1)  # within 10% = high
            confidence = round(vol_score * 0.6 + prox_score * 0.4, 3)
            confidence = max(0.1, min(confidence, 0.99))

            signals.append({
                "symbol": symbol,
                "price": price,
                "side": side,
                "confidence": confidence,
            })

    # Sort all signals by confidence descending, take top_n total
    signals.sort(key=lambda x: x["confidence"], reverse=True)
    return signals[:top_n], ref_price


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--expert", default="v1")
    args = parser.parse_args()

    artifact = find_latest_artifact(args.symbol, args.expert)
    if artifact is None:
        logger.error(f"No artifact found for {args.symbol}/{args.expert}")
        return

    logger.info(f"Using artifact: {artifact}")
    signals, ref_price = extract_top_signals(artifact, args.top_n)
    logger.info(f"Reference price: {ref_price}, extracted {len(signals)} signals")

    publisher = SignalPublisher()
    published = 0
    try:
        for sig in signals:
            ok = publisher.publish_signal(
                symbol=sig["symbol"],
                price=sig["price"],
                side=sig["side"],
                confidence=sig["confidence"],
            )
            if ok:
                published += 1
                logger.info(f"  Published: {sig['side']} @ {sig['price']:.1f} conf={sig['confidence']}")
    finally:
        publisher.close()

    logger.info(f"Published {published}/{len(signals)} signals for {args.symbol}")


if __name__ == "__main__":
    main()
