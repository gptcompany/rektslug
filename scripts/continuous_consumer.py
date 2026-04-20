#!/usr/bin/env python3
"""Continuous real-signal consumer with circuit breaker and shadow mode.

Subscribes to Redis liquidation signals, applies runtime config,
tracks lifecycle states, and optionally runs in extended shadow mode
with hypothetical PnL tracking and circuit breaker calibration.
"""

import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone

from src.liquidationheatmap.signals.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)
from src.liquidationheatmap.signals.lifecycle import LifecycleState, SignalLifecycleTracker
from src.liquidationheatmap.signals.lifecycle_store import DuckDBLifecycleStore
from src.liquidationheatmap.signals.models import LiquidationSignal
from src.liquidationheatmap.signals.redis_client import get_redis_client
from src.liquidationheatmap.signals.shadow import ShadowTracker

logger = logging.getLogger(__name__)

_running = True


def _handle_signal(signum, frame):
    global _running
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _running = False


def parse_args():
    parser = argparse.ArgumentParser(description="Continuous mode signal consumer")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--min-confidence", type=float, default=0.7)
    parser.add_argument("--max-size", type=float, default=0.01)
    parser.add_argument("--max-signals", type=int, default=10)
    parser.add_argument("--window-secs", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-path", type=str, default="/tmp/dry_run_report.json")

    # Shadow mode
    parser.add_argument("--shadow-mode", action="store_true",
                        help="Extended observation mode (implies --dry-run, no window cap)")
    parser.add_argument("--report-interval-secs", type=int, default=300,
                        help="Periodic report interval in shadow mode")

    # Circuit breaker
    parser.add_argument("--cb-max-losses", type=int, default=5)
    parser.add_argument("--cb-max-drawdown", type=float, default=-50.0)
    parser.add_argument("--cb-max-per-hour", type=int, default=10)
    parser.add_argument("--cb-cooldown", type=int, default=300)

    return parser.parse_args()


def _emit_report(report_path, config, signals_log, summary, shadow_tracker=None, cb=None, symbols=None):
    """Write periodic or final report to disk."""
    report = {
        "config": config,
        "signals": signals_log,
        "summary": summary,
    }
    if shadow_tracker:
        cal = shadow_tracker.get_calibration()
        report["calibration"] = {
            "total_signals": cal.total_signals,
            "profitable": cal.profitable,
            "signal_quality_score": cal.signal_quality_score,
            "longest_losing_streak": cal.longest_losing_streak,
            "max_drawdown": cal.max_drawdown,
            "total_pnl": cal.total_pnl,
            "suggested_max_consecutive_losses": cal.suggested_max_consecutive_losses,
            "suggested_max_drawdown": cal.suggested_max_drawdown,
        }
        report["hypothetical_positions"] = shadow_tracker.get_closed_positions()
    if cb and symbols:
        report["circuit_breaker"] = {}
        for sym in symbols:
            state = cb.get_state(sym)
            report["circuit_breaker"][sym] = {
                "tripped": state.tripped,
                "trip_reason": state.trip_reason.value if state.trip_reason else None,
                "consecutive_losses": state.consecutive_losses,
                "session_pnl": state.session_pnl,
            }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Report saved to {report_path}")


def main():
    global _running
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()

    # Shadow mode implies dry-run and removes window cap
    if args.shadow_mode:
        args.dry_run = True
        args.window_secs = 0  # 0 = no limit
        args.max_signals = 0  # 0 = no limit

    if not args.dry_run:
        logger.error("This script is currently only for --dry-run or --shadow-mode.")
        return

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    mode = "shadow" if args.shadow_mode else "dry-run"
    logger.info(f"Starting continuous {mode} consumer.")
    logger.info(f"Config: symbols={args.symbols}, min_confidence={args.min_confidence}")

    store = DuckDBLifecycleStore()
    tracker = SignalLifecycleTracker(store=store)
    redis_client = get_redis_client()

    # Circuit breaker
    cb_config = CircuitBreakerConfig(
        max_consecutive_losses=args.cb_max_losses,
        max_session_drawdown=args.cb_max_drawdown,
        max_signals_per_hour=args.cb_max_per_hour,
        cooldown_secs=args.cb_cooldown,
    )

    def _on_trip(symbol, reason):
        logger.warning(f"CIRCUIT BREAKER TRIPPED: {symbol} — {reason.value}")
        try:
            redis_client.publish(f"liquidation:alerts:{symbol}",
                                 json.dumps({"type": "circuit_breaker_trip",
                                             "symbol": symbol,
                                             "reason": reason.value,
                                             "timestamp": datetime.now(timezone.utc).isoformat()}))
        except Exception as e:
            logger.error(f"Failed to publish CB alert: {e}")

    cb = CircuitBreaker(config=cb_config, on_trip=_on_trip)

    # Shadow tracker (only in shadow mode)
    shadow = ShadowTracker() if args.shadow_mode else None
    # Track last signal price per symbol for hypothetical exit
    last_prices: dict[str, float] = {}

    channels = [f"liquidation:signals:{sym}" for sym in args.symbols]

    start_time = time.time()
    last_report_time = start_time
    accepted_count = 0
    signals_seen = 0
    rejected_count = 0
    reject_reasons: dict[str, int] = {}
    signals_log: list[dict] = []

    try:
        with redis_client.pubsub() as pubsub:
            if pubsub is None:
                logger.error("Failed to connect to Redis. Exiting.")
                return

            pubsub.subscribe(*channels)
            logger.info(f"Listening for signals on {channels}...")

            while _running:
                # Window check (0 = no limit in shadow mode)
                if args.window_secs > 0 and (time.time() - start_time) > args.window_secs:
                    logger.info("Runtime window expired.")
                    break

                # Max signals check (0 = no limit in shadow mode)
                if args.max_signals > 0 and accepted_count >= args.max_signals:
                    logger.info("Max accepted signals reached.")
                    break

                # Periodic report in shadow mode
                if args.shadow_mode and (time.time() - last_report_time) >= args.report_interval_secs:
                    summary = _build_summary(signals_seen, accepted_count, rejected_count,
                                             reject_reasons, start_time)
                    _emit_report(args.report_path, vars(args), signals_log, summary,
                                 shadow, cb, args.symbols)
                    last_report_time = time.time()

                message = pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    signals_seen += 1
                    data = json.loads(message["data"])
                    signal_obj = LiquidationSignal(**data)
                    sig_id = signal_obj.signal_id or f"{mode}-{signals_seen}"

                    tracker.record_signal(sig_id)

                    # Close previous hypothetical position for this symbol
                    if shadow and signal_obj.symbol in last_prices:
                        # Find open position for this symbol and close it
                        for open_id, pos in list(shadow._open.items()):
                            if pos.symbol == signal_obj.symbol:
                                shadow.record_exit(open_id, float(signal_obj.price))
                                # Feed hypothetical PnL to circuit breaker
                                closed = shadow._closed[-1] if shadow._closed else None
                                if closed:
                                    cb.record_outcome(signal_obj.symbol, closed.pnl)

                    # Circuit breaker gate
                    cb_allowed, cb_reason = cb.check(signal_obj.symbol)
                    if not cb_allowed:
                        tracker.transition(sig_id, LifecycleState.REJECTED)
                        rejected_count += 1
                        reject_reasons[cb_reason] = reject_reasons.get(cb_reason, 0) + 1
                        logger.info(f"REJECTED {sig_id}: {cb_reason}")
                        signals_log.append({"id": sig_id, "state": "REJECTED", "reason": cb_reason})
                        continue

                    # Filter checks
                    reject_reason = None
                    if signal_obj.symbol not in args.symbols:
                        reject_reason = f"symbol_not_in_allowlist"
                    elif signal_obj.confidence < args.min_confidence:
                        reject_reason = f"confidence_below_threshold"

                    if reject_reason:
                        tracker.transition(sig_id, LifecycleState.REJECTED)
                        rejected_count += 1
                        reject_reasons[reject_reason] = reject_reasons.get(reject_reason, 0) + 1
                        logger.info(f"REJECTED {sig_id}: {reject_reason}")
                        signals_log.append({"id": sig_id, "state": "REJECTED", "reason": reject_reason})
                    else:
                        tracker.transition(sig_id, LifecycleState.ACCEPTED)
                        cb.record_acceptance(signal_obj.symbol)
                        accepted_count += 1
                        logger.info(f"ACCEPTED {sig_id} ({mode})")
                        signals_log.append({"id": sig_id, "state": "ACCEPTED"})

                        # Record hypothetical entry in shadow mode
                        if shadow:
                            shadow.record_entry(sig_id, signal_obj.symbol,
                                                float(signal_obj.price), signal_obj.side)

                    last_prices[signal_obj.symbol] = float(signal_obj.price)

    except Exception as e:
        logger.error(f"Consumer error: {e}")
    finally:
        # Write report BEFORE closing connections (report doesn't need them)
        summary = _build_summary(signals_seen, accepted_count, rejected_count,
                                 reject_reasons, start_time)
        _emit_report(args.report_path, vars(args), signals_log, summary,
                     shadow, cb, args.symbols)

        if shadow:
            cal = shadow.get_calibration()
            logger.info(f"Calibration: quality={cal.signal_quality_score:.2f}, "
                        f"streak={cal.longest_losing_streak}, "
                        f"suggested_max_losses={cal.suggested_max_consecutive_losses}, "
                        f"suggested_drawdown={cal.suggested_max_drawdown:.2f}")

        # Cleanup connections last
        redis_client.disconnect()
        store.close()


def _build_summary(signals_seen, accepted, rejected, reject_reasons, start_time):
    return {
        "signals_seen": signals_seen,
        "accepted": accepted,
        "rejected": rejected,
        "reject_reasons": reject_reasons,
        "accept_rate": accepted / signals_seen if signals_seen > 0 else 0.0,
        "runtime_secs": time.time() - start_time,
        "venue_orders_submitted": 0,
    }


if __name__ == "__main__":
    main()
