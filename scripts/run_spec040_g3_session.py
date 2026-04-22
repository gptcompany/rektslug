#!/usr/bin/env python3
"""Run a bounded real G3 continuous session for spec-040."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from src.liquidationheatmap.signals.publisher import SignalPublisher


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a real spec-040 G3 session.")
    parser.add_argument(
        "--nautilus-path",
        default="/media/sam/1TB/nautilus_dev",
        help="Path to nautilus_dev checkout.",
    )
    parser.add_argument(
        "--output-dir",
        default="specs/040-nautilus-continuous-paper-testnet/g3_session",
        help="Directory where runtime logs and evidence are retained.",
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--instrument", default="BTC-USD-PERP.HYPERLIQUID")
    parser.add_argument("--signal-side", choices=["long", "short"], default="long")
    parser.add_argument("--signal-price", type=Decimal, default=Decimal("95000.50"))
    parser.add_argument("--signal-confidence", type=float, default=0.91)
    parser.add_argument("--window-secs", type=int, default=180)
    parser.add_argument("--signal-delay-secs", type=float, default=8.0)
    parser.add_argument("--flatten-timeout-secs", type=float, default=90.0)
    parser.add_argument("--redis-host", default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--redis-db", type=int, default=0)
    parser.add_argument(
        "--db-path",
        default="/media/sam/2TB-NVMe/liquidationheatmap_db/signal_feedback.duckdb",
    )
    parser.add_argument(
        "--start-feedback-consumer",
        action="store_true",
        help="Start rektslug-feedback-consumer via docker compose if it is not already running.",
    )
    parser.add_argument(
        "--cleanup-on-fail",
        action="store_true",
        help="Attempt Hyperliquid testnet cleanup if the session fails with residual state.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_testnet_key(nautilus_path: Path) -> str:
    cmd = ["dotenvx", "get", "HYPERLIQUID_TESTNET_PK", "-f", str(nautilus_path / ".env")]
    key = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    if not key:
        raise RuntimeError("HYPERLIQUID_TESTNET_PK not found via dotenvx")
    return key


def _docker_container_names(repo_root: Path) -> set[str]:
    ps = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo_root,
    )
    return {line.strip() for line in ps.stdout.splitlines() if line.strip()}


def _ensure_feedback_consumer(repo_root: Path, *, start_if_missing: bool) -> bool:
    names = _docker_container_names(repo_root)
    if "rektslug-feedback-consumer" in names:
        return False
    if not start_if_missing:
        raise RuntimeError("rektslug-feedback-consumer is not running")
    subprocess.run(
        ["docker", "compose", "up", "-d", "rektslug-feedback-consumer"],
        cwd=repo_root,
        check=True,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        if "rektslug-feedback-consumer" in _docker_container_names(repo_root):
            return True
        time.sleep(2)
    raise RuntimeError("rektslug-feedback-consumer did not start in time")


def _compose_feedback_consumer(repo_root: Path, action: str) -> None:
    if action == "up":
        cmd = ["docker", "compose", "up", "-d", "rektslug-feedback-consumer"]
    else:
        cmd = ["docker", "compose", action, "rektslug-feedback-consumer"]
    subprocess.run(
        cmd,
        cwd=repo_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_control_state(path: Path, *, sequence: int) -> None:
    payload = {
        "generated_at": _utc_now(),
        "status": "FLATTENING",
        "reduce_only": True,
        "sequence": sequence,
        "flatten_scope": "flatten_all",
        "flatten_target": "liquidation_bridge",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _wait_for_snapshot(
    path: Path,
    *,
    timeout_secs: float,
    predicate,
) -> dict[str, Any]:
    deadline = time.time() + timeout_secs
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        if path.exists():
            payload = _read_json(path)
            last_payload = payload
            if predicate(payload):
                return payload
        time.sleep(1)
    if last_payload is None:
        raise RuntimeError(f"timeout waiting for runtime snapshot: {path}")
    raise RuntimeError(f"timeout waiting for expected runtime state: {last_payload}")


def _fetch_feedback_rows(db_path: Path, signal_id: str) -> list[tuple[Any, ...]]:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        return conn.execute(
            """
            SELECT symbol, signal_id, entry_price, exit_price, pnl, source, created_at
            FROM signal_feedback
            WHERE signal_id = ?
            ORDER BY created_at DESC
            """,
            [signal_id],
        ).fetchall()
    finally:
        conn.close()


def _wait_for_feedback_row(db_path: Path, signal_id: str, *, timeout_secs: float) -> list[tuple[Any, ...]]:
    deadline = time.time() + timeout_secs
    rows: list[tuple[Any, ...]] = []
    while time.time() < deadline:
        rows = _fetch_feedback_rows(db_path, signal_id)
        if rows:
            return rows
        time.sleep(1)
    raise RuntimeError(f"timeout waiting for feedback row for {signal_id}")


def _cleanup_testnet_account(nautilus_path: Path, env: dict[str, str], symbol: str) -> None:
    coin = symbol[:-4] if symbol.endswith("USDT") else symbol
    subprocess.run(
        [
            str(nautilus_path / ".venv/bin/python"),
            str(nautilus_path / "scripts/hyperliquid/cleanup_testnet_account.py"),
            "--coin",
            coin,
        ],
        env=env,
        cwd=nautilus_path,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_session(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    nautilus_path = Path(args.nautilus_path).resolve()
    output_root = Path(args.output_dir).resolve()
    session_dir = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_dir.mkdir(parents=True, exist_ok=True)

    runtime_snapshot_path = session_dir / "continuous_runtime_report.json"
    runtime_ledger_path = session_dir / "runtime_ledger.jsonl"
    connectivity_status_path = session_dir / "connectivity_status.json"
    risk_status_path = session_dir / "risk_status.json"
    error_registry_path = session_dir / "error_registry.jsonl"
    control_state_path = session_dir / "operator_control_state.json"
    continuous_log_path = session_dir / "continuous_stdout.log"
    session_result_path = session_dir / "session_result.json"

    started_feedback_consumer = _ensure_feedback_consumer(
        repo_root,
        start_if_missing=args.start_feedback_consumer,
    )
    private_key = _load_testnet_key(nautilus_path)

    env = os.environ.copy()
    env["HYPERLIQUID_TESTNET_PK"] = private_key
    env["PYTHONPATH"] = str(nautilus_path)
    env["REDIS_HOST"] = args.redis_host
    env["REDIS_PORT"] = str(args.redis_port)
    env["REDIS_DB"] = str(args.redis_db)

    cmd = [
        str(nautilus_path / ".venv/bin/python"),
        str(nautilus_path / "scripts/hyperliquid/run_continuous.py"),
        "--mode",
        "testnet",
        "--symbol",
        args.symbol,
        "--instrument",
        args.instrument,
        "--max-size",
        "0.001",
        "--max-exposure",
        "0.01",
        "--window-secs",
        str(args.window_secs),
        "--redis-host",
        args.redis_host,
        "--redis-port",
        str(args.redis_port),
        "--redis-db",
        str(args.redis_db),
        "--log-level",
        args.log_level,
        "--control-state-path",
        str(control_state_path),
        "--runtime-snapshot-path",
        str(runtime_snapshot_path),
        "--runtime-ledger-path",
        str(runtime_ledger_path),
        "--connectivity-status-path",
        str(connectivity_status_path),
        "--risk-status-path",
        str(risk_status_path),
        "--error-registry-path",
        str(error_registry_path),
    ]

    with continuous_log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=nautilus_path,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    signal_id = f"spec040-g3-{int(time.time())}"
    result: dict[str, Any] = {
        "started_at": _utc_now(),
        "session_dir": str(session_dir),
        "signal_id": signal_id,
        "command": cmd,
        "runtime_snapshot_path": str(runtime_snapshot_path),
        "runtime_ledger_path": str(runtime_ledger_path),
        "control_state_path": str(control_state_path),
        "continuous_log_path": str(continuous_log_path),
        "feedback_db_path": args.db_path,
        "status": "running",
    }
    feedback_consumer_stopped = False

    try:
        _wait_for_snapshot(
            runtime_snapshot_path,
            timeout_secs=60,
            predicate=lambda payload: payload.get("node_status") in {"RUNNING", "DEGRADED"},
        )
        time.sleep(args.signal_delay_secs)

        os.environ["REDIS_HOST"] = args.redis_host
        os.environ["REDIS_PORT"] = str(args.redis_port)
        os.environ["REDIS_DB"] = str(args.redis_db)
        os.environ["SIGNALS_ENABLED"] = "true"
        publisher = SignalPublisher()
        if not publisher.publish_signal(
            args.symbol,
            float(args.signal_price),
            args.signal_side,
            args.signal_confidence,
            signal_id=signal_id,
        ):
            raise RuntimeError("failed to publish spec-040 G3 signal")

        opened_payload = _wait_for_snapshot(
            runtime_snapshot_path,
            timeout_secs=args.flatten_timeout_secs,
            predicate=lambda payload: int(payload.get("positions_opened", 0)) >= 1,
        )
        result["opened_snapshot"] = opened_payload

        _write_control_state(control_state_path, sequence=1)

        closed_payload = _wait_for_snapshot(
            runtime_snapshot_path,
            timeout_secs=args.flatten_timeout_secs,
            predicate=lambda payload: int(payload.get("positions_closed", 0)) >= 1,
        )

        process.send_signal(signal.SIGINT)
        process.wait(timeout=30)

        final_payload = _read_json(runtime_snapshot_path)
        time.sleep(3)
        _compose_feedback_consumer(repo_root, "stop")
        feedback_consumer_stopped = True
        rows = _wait_for_feedback_row(Path(args.db_path), signal_id, timeout_secs=10)
        builder_cmd = [
            "uv",
            "run",
            "python",
            "scripts/build_spec040_evidence.py",
            "--runtime-snapshot-path",
            str(runtime_snapshot_path),
            "--db-path",
            args.db_path,
            "--output-dir",
            str(session_dir / "evidence"),
        ]
        subprocess.run(builder_cmd, cwd=repo_root, check=True)

        result.update(
            {
                "status": "ok",
                "closed_snapshot": closed_payload,
                "final_snapshot": final_payload,
                "feedback_rows": [
                    {
                        "symbol": row[0],
                        "signal_id": row[1],
                        "entry_price": str(row[2]),
                        "exit_price": str(row[3]),
                        "pnl": str(row[4]),
                        "source": row[5],
                        "created_at": str(row[6]),
                    }
                    for row in rows
                ],
                "evidence_dir": str(session_dir / "evidence"),
                "ended_at": _utc_now(),
            }
        )
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        result["ended_at"] = _utc_now()
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
        if args.cleanup_on_fail:
            _cleanup_testnet_account(nautilus_path, env, args.symbol)
        if feedback_consumer_stopped and started_feedback_consumer:
            _compose_feedback_consumer(repo_root, "up")
        elif feedback_consumer_stopped and not started_feedback_consumer:
            _compose_feedback_consumer(repo_root, "start")
        session_result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return 1

    if feedback_consumer_stopped and started_feedback_consumer:
        _compose_feedback_consumer(repo_root, "up")
    elif feedback_consumer_stopped and not started_feedback_consumer:
        _compose_feedback_consumer(repo_root, "start")
    session_result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(session_result_path)
    return 0


def main() -> int:
    return run_session(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
