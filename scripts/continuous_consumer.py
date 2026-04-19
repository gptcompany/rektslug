#!/usr/bin/env python3
"""Continuous real-signal consumer for dry-run mode (Phase 3).

Subscribes to Redis liquidation signals, applies runtime config,
and tracks lifecycle states (RECEIVED, ACCEPTED, REJECTED) without execution.
"""

import argparse
import json
import logging
import time
from datetime import datetime, timezone

from src.liquidationheatmap.signals.lifecycle import LifecycleState, SignalLifecycleTracker
from src.liquidationheatmap.signals.lifecycle_store import DuckDBLifecycleStore
from src.liquidationheatmap.signals.models import LiquidationSignal
from src.liquidationheatmap.signals.redis_client import get_redis_client

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Continuous mode dry-run signal consumer")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"], help="Symbol allowlist")
    parser.add_argument("--min-confidence", type=float, default=0.7, help="Minimum confidence to accept")
    parser.add_argument("--max-size", type=float, default=0.01, help="Max position size equivalent")
    parser.add_argument("--max-signals", type=int, default=10, help="Max accepted signals before stopping")
    parser.add_argument("--window-secs", type=int, default=300, help="Max runtime window in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Run without venue orders (records decisions only)")
    parser.add_argument("--report-path", type=str, default="/tmp/dry_run_report.json")
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()

    if not args.dry_run:
        logger.error("This script is currently only for --dry-run. Use nautilus_dev/scripts/hyperliquid/run_live.py for testnet.")
        return

    logger.info(f"Starting continuous dry-run consumer.")
    logger.info(f"Config: symbols={args.symbols}, min_confidence={args.min_confidence}, window={args.window_secs}s")

    store = DuckDBLifecycleStore()
    tracker = SignalLifecycleTracker(store=store)
    redis_client = get_redis_client()

    channels = [f"liquidation:signals:{sym}" for sym in args.symbols]

    start_time = time.time()
    accepted_count = 0
    signals_seen = 0
    rejected_count = 0
    report = {
        "config": vars(args),
        "signals": []
    }

    try:
        with redis_client.pubsub() as pubsub:
            if pubsub is None:
                logger.error("Failed to connect to Redis. Exiting.")
                return
            
            pubsub.subscribe(*channels)
            logger.info(f"Listening for signals on {channels}...")
            
            while True:
                if time.time() - start_time > args.window_secs:
                    logger.info("Runtime window expired.")
                    break

                if accepted_count >= args.max_signals:
                    logger.info("Max accepted signals reached.")
                    break

                message = pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    signals_seen += 1
                    data = json.loads(message["data"])
                    signal = LiquidationSignal(**data)
                    sig_id = signal.signal_id or f"dry-run-{signals_seen}"
                    
                    tracker.record_signal(sig_id)
                    
                    # Evaluate
                    reject_reason = None
                    if signal.symbol not in args.symbols:
                        reject_reason = f"Symbol {signal.symbol} not in allowlist"
                    elif signal.confidence < args.min_confidence:
                        reject_reason = f"Confidence {signal.confidence} < {args.min_confidence}"
                    
                    if reject_reason:
                        tracker.transition(sig_id, LifecycleState.REJECTED)
                        rejected_count += 1
                        logger.info(f"REJECTED {sig_id}: {reject_reason}")
                        report["signals"].append({"id": sig_id, "state": "REJECTED", "reason": reject_reason})
                    else:
                        tracker.transition(sig_id, LifecycleState.ACCEPTED)
                        accepted_count += 1
                        logger.info(f"ACCEPTED {sig_id} for dry-run execution")
                        report["signals"].append({"id": sig_id, "state": "ACCEPTED"})

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        redis_client.disconnect()
        store.close()

        # Save report
        summary = {
            "signals_seen": signals_seen,
            "accepted": accepted_count,
            "rejected": rejected_count,
            "runtime_secs": time.time() - start_time,
            "venue_orders_submitted": 0  # True by definition in dry-run
        }
        report["summary"] = summary
        
        with open(args.report_path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Dry-run report saved to {args.report_path}")
        logger.info(f"Summary: {summary}")


if __name__ == "__main__":
    main()
