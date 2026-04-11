import pytest
import sys
from pathlib import Path
import argparse

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

def test_public_route_baseline_uses_public_surface():
    from scripts.capture_provider_api import build_targets
    
    args = argparse.Namespace(
        provider="rektslug",
        coin="BTC",
        timeframe="1d",
        exchange="binance",
        coinank_url=None,
        coinglass_url=None,
        bitcoincounterflow_url=None,
        coinglass_timeframe=None,
        surface="public"
    )
    targets = build_targets(args)
    assert targets[0].requested_surface == "public"
    assert targets[0].effective_surface == "public"
    assert "/liquidations/coinank-public-map" in targets[0].url

