import subprocess
import sys


def test_producer_accepts_snapshot_ts_and_run_kind():
    # Attempt to run producer.py with the required flags
    # We use --help or just mock the call to not actually run it fully,
    # or pass valid arguments.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.liquidationheatmap.hyperliquid.producer",
            "--snapshot-ts",
            "2026-04-03T12:00:00Z",
            "--run-kind",
            "baseline",
        ],
        capture_output=True,
        text=True,
    )

    # It should succeed without argparse errors
    assert result.returncode == 0
    # Also verify it rejects invalid run kinds
    result_invalid = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.liquidationheatmap.hyperliquid.producer",
            "--snapshot-ts",
            "2026-04-03T12:00:00Z",
            "--run-kind",
            "invalid_kind",
        ],
        capture_output=True,
        text=True,
    )
    assert result_invalid.returncode != 0
