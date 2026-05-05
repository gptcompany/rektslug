#!/usr/bin/env python3
"""Runner for Nautilus fault injection tests (Phase 4).

Wraps the guarded testnet smoke and injects failures into the lifecycle
to verify recovery and flat account states.
"""

import argparse
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault", required=True, help="Fault point name (e.g. PRE_SUBMIT)")
    parser.add_argument("--nautilus-path", default="/media/sam/1TB/nautilus_dev")
    parser.add_argument("--redis-host", default="172.20.0.4")
    parser.add_argument("--skip-recovery", action="store_true", help="Don't run the recovery pass")
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()

    smoke_script = os.path.join(args.nautilus_path, "scripts/hyperliquid/liquidation_bridge_smoke.py")

    logger.info(f"=== FAULT INJECTION TEST: {args.fault} ===")

    # 1. Run the script with the FAULT injected via environment variable
    # We will monkeypatch nautilus_dev via a custom launcher that imports it
    # and overrides the strategy methods based on the FAULT_INJECTION_POINT env var.

    wrapper_code = f"""
import os
import sys
from decimal import Decimal
import time

sys.path.insert(0, "{args.nautilus_path}")

from scripts.hyperliquid.liquidation_bridge_smoke import main as smoke_main, parse_args
from strategies.hyperliquid.liquidation_bridge.strategy import LiquidationRedisSignalStrategy

fault_point = os.environ.get("FAULT_INJECTION_POINT")

if fault_point == "PRE_SUBMIT":
    original_submit = LiquidationRedisSignalStrategy.submit_order
    def mocked_submit(self, order):
        print("INJECTED FAULT: PRE_SUBMIT")
        raise Exception("Fault PRE_SUBMIT triggered")
    LiquidationRedisSignalStrategy.submit_order = mocked_submit

elif fault_point == "POST_SUBMIT_PRE_FILL":
    original_submit = LiquidationRedisSignalStrategy.submit_order
    def mocked_submit(self, order):
        original_submit(self, order)
        print("INJECTED FAULT: POST_SUBMIT_PRE_FILL")
        os._exit(1)
    LiquidationRedisSignalStrategy.submit_order = mocked_submit

elif fault_point == "OPEN_POSITION_PRE_CLOSE":
    original_close = LiquidationRedisSignalStrategy.close_all_positions
    def mocked_close(self, instrument_id):
        print("INJECTED FAULT: OPEN_POSITION_PRE_CLOSE")
        os._exit(1)
    LiquidationRedisSignalStrategy.close_all_positions = mocked_close

elif fault_point == "POST_CLOSE_PRE_FEEDBACK":
    original_publish = LiquidationRedisSignalStrategy.publish_feedback
    def mocked_publish(self, feedback):
        print("INJECTED FAULT: POST_CLOSE_PRE_FEEDBACK")
        os._exit(1)
    LiquidationRedisSignalStrategy.publish_feedback = mocked_publish

elif fault_point == "REDIS_UNAVAILABLE":
    # Handled via bad REDIS_HOST
    pass

elif fault_point == "DUCKDB_UNAVAILABLE":
    # Handled via bad DB path dir
    pass

print(f"Running with fault injection: {{fault_point}}")
try:
    smoke_main()
except SystemExit as e:
    sys.exit(e.code)
"""

    wrapper_path = "/tmp/fault_wrapper.py"
    with open(wrapper_path, "w") as f:
        f.write(wrapper_code)

    env = os.environ.copy()
    env["FAULT_INJECTION_POINT"] = args.fault

    # Load PK
    pk_cmd = f"dotenvx get HYPERLIQUID_TESTNET_PK -f {args.nautilus_path}/.env"
    try:
        pk = subprocess.check_output(pk_cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        env["HYPERLIQUID_TESTNET_PK"] = pk
    except subprocess.CalledProcessError:
        logger.error("Failed to load HYPERLIQUID_TESTNET_PK")
        return

    cmd = [
        os.path.join(args.nautilus_path, ".venv/bin/python"),
        wrapper_path,
        "--confirm-testnet-order",
        "--rektslug-path", os.getcwd(),
        "--timeout-secs", "30",
        "--redis-host", args.redis_host if args.fault != "REDIS_UNAVAILABLE" else "255.255.255.255",
        "--db-path", "/invalid/path/db.duckdb" if args.fault == "DUCKDB_UNAVAILABLE" else "/tmp/fault_test.duckdb"
    ]

    logger.info("-> Injecting fault...")
    try:
        result = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
        logger.info(f"Fault run exit code: {result.returncode}")
        stdout = result.stdout
    except subprocess.TimeoutExpired as e:
        logger.info("Fault run timed out (expected if node hangs).")
        stdout = e.stdout.decode() if e.stdout else ""

    if "INJECTED FAULT" in stdout or args.fault in ["REDIS_UNAVAILABLE", "DUCKDB_UNAVAILABLE"]:
        logger.info("Fault was successfully injected.")
    else:
        logger.warning(f"Fault signature not found in stdout! Stdout:\\n{stdout}")

    if args.skip_recovery:
        return

    # 2. Run the recovery pass (normal smoke)
    logger.info("-> Running recovery pass...")
    recovery_cmd = [
        os.path.join(args.nautilus_path, ".venv/bin/python"),
        smoke_script,
        "--confirm-testnet-order",
        "--rektslug-path", os.getcwd(),
        "--redis-host", args.redis_host,
        "--timeout-secs", "60",
        "--db-path", "/tmp/fault_test.duckdb"
    ]

    try:
        recovery_result = subprocess.run(recovery_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=80)
        recovery_code = recovery_result.returncode
        recovery_stdout = recovery_result.stdout
    except subprocess.TimeoutExpired as e:
        logger.error("Recovery run timed out!")
        recovery_code = -1
        recovery_stdout = e.stdout.decode() if e.stdout else ""

    logger.info(f"Recovery run exit code: {recovery_code}")

    if "NODE_SMOKE_OK" in recovery_stdout:
        logger.info("Recovery run PASSED (NODE_SMOKE_OK). Account is flat.")
    else:
        logger.error("Recovery run FAILED.")
        logger.error(f"Stdout:\\n{recovery_stdout}")

    # Output simple marker for the test script
    print(f"FAULT_TEST_RESULT: {args.fault} -> RECOVERY_CODE={recovery_code}")


if __name__ == "__main__":
    main()
