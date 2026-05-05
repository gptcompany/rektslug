#!/usr/bin/env python3
"""Legacy Hyperliquid liquidation collector.

Usage:
    python scripts/collect_liquidations.py           # Run for 5 min
    python scripts/collect_liquidations.py --minutes 30
"""

import argparse
import sys
from pathlib import Path

OUTPUT = Path("data/validation/hyperliquid_liquidations.jsonl")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
UNSUPPORTED_REASON = (
    "Public Hyperliquid liquidation collection is unsupported. Use "
    "scripts/ingest_hl_fills.py against node_fills_by_block for realized liquidations."
)


def collect(minutes: int = 5):
    print(f"{UNSUPPORTED_REASON} Requested duration: {minutes} min.")
    print(f"Legacy output path retained for reference only: {OUTPUT}")
    raise SystemExit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=5)
    args = parser.parse_args()
    try:
        collect(args.minutes)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"collect_liquidations failed: {exc}", file=sys.stderr)
        sys.exit(1)
