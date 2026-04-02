"""Contract tests for the Hyperliquid public liq-map endpoint."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.liquidationheatmap.api.main import app
from src.liquidationheatmap.api.routers import liquidations


def _fresh_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _base_cache_payload() -> dict:
    return {
        "source": "hyperliquid-sidecar",
        "symbol": "BTCUSDT",
        "timeframe": "1w",
        "current_price": 68500.0,
        "mark_price": 68500.0,
        "account_count": 123,
        "generated_at": _fresh_timestamp(),
        "grid": {
            "step": 500.0,
            "anchor_price": 68500.0,
            "min_price": 50000.0,
            "max_price": 90000.0,
        },
        "leverage_ladder": ["cross"],
        "long_buckets": [
            {"price_level": 64000.0, "leverage": "cross", "volume": 1000.0},
        ],
        "short_buckets": [
            {"price_level": 72000.0, "leverage": "cross", "volume": 1500.0},
        ],
        "cumulative_long": [
            {"price_level": 64000.0, "value": 1000.0},
        ],
        "cumulative_short": [
            {"price_level": 72000.0, "value": 1500.0},
        ],
        "out_of_range_volume": {
            "long": 0.0,
            "short": 0.0,
        },
        "source_anchor": "data/cache/hl_sidecar_btcusdt.json",
        "bin_size": 500.0,
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    cache_file = tmp_path / "hl_sidecar_btcusdt.json"
    cache_file.write_text(json.dumps(_base_cache_payload()), encoding="utf-8")
    v3_cache_file = tmp_path / "hl_sidecar_v3_btcusdt.json"
    v3_cache_file.write_text(
        json.dumps(
            {
                **_base_cache_payload(),
                "source": "hyperliquid-sidecar-top-positions",
                "account_count": 17,
                "projection": {
                    "mode": "top_positions_local",
                    "selected_users": 20,
                    "included_users": 17,
                    "target_count": 20,
                    "live_override_users": 12,
                    "users_removed_by_live_override": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(liquidations, "_HL_CACHE_DIR", tmp_path)
    return TestClient(app)


def test_hl_public_map_default_variant_returns_sidecar_cache(client: TestClient) -> None:
    response = client.get("/liquidations/hl-public-map?symbol=BTCUSDT&timeframe=1w")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "hyperliquid-sidecar"
    assert data["symbol"] == "BTCUSDT"
    assert data["grid"]["step"] == 500.0


def test_hl_public_map_coinglass_variant_uses_experimental_builder(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    def fake_builder(symbol: str, timeframe: str, base_cache: dict) -> dict:
        called["symbol"] = symbol
        called["timeframe"] = timeframe
        called["base_cache_source"] = base_cache["source"]
        return {
            **base_cache,
            "source": "coinglass-top-position-local",
            "current_price": 70123.0,
            "mark_price": 70123.0,
            "account_count": 17,
            "source_anchor": "data/validation/raw_provider_api/mock-capture",
        }

    monkeypatch.setattr(liquidations, "_build_coinglass_top_position_response", fake_builder)

    response = client.get(
        "/liquidations/hl-public-map"
        "?symbol=BTCUSDT&timeframe=1w&variant=coinglass-top-position"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "coinglass-top-position-local"
    assert data["current_price"] == 70123.0
    assert data["source_anchor"] == "data/validation/raw_provider_api/mock-capture"
    assert called == {
        "symbol": "BTCUSDT",
        "timeframe": "1w",
        "base_cache_source": "hyperliquid-sidecar",
    }


def test_hl_public_map_internal_top_positions_variant_returns_v3_cache(
    client: TestClient,
) -> None:
    response = client.get(
        "/liquidations/hl-public-map"
        "?symbol=BTCUSDT&timeframe=1w&variant=internal-top-positions"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "hyperliquid-sidecar-top-positions"
    assert data["account_count"] == 17


def test_coinglass_builder_falls_back_to_last_decodable_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target_url = "https://capi.coinglass.com/api/hyperliquid/topPosition/liqMap?symbol=BTC"
    latest_capture_dir = tmp_path / "20260402T082851Z"
    older_capture_dir = tmp_path / "20260401T160752Z"

    for capture_dir in (latest_capture_dir, older_capture_dir):
        capture_dir.mkdir(parents=True)
        (capture_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "providers": [
                        {
                            "captures": [
                                {
                                    "source_url": target_url,
                                    "saved_file": "coinglass/12_liqmap.json",
                                }
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    calls: list[str] = []

    def fake_decode(capture_dir: Path, symbol: str) -> dict:
        calls.append(capture_dir.name)
        if capture_dir == latest_capture_dir:
            raise HTTPException(status_code=503, detail="CoinGlass decode failed: empty result")
        assert symbol == "BTC"
        return {
            "price": 70123.0,
            "list": [
                {
                    "liquidationPrice": 69000.0,
                    "positionUsd": 250000.0,
                    "size": 1.0,
                    "userId": "abc",
                }
            ],
        }

    monkeypatch.setattr(liquidations, "_CG_CAPTURE_ROOT", tmp_path)
    monkeypatch.setattr(liquidations, "_decode_coinglass_top_position_capture", fake_decode)

    response = liquidations._build_coinglass_top_position_response(
        symbol="BTCUSDT",
        timeframe="1w",
        base_cache=_base_cache_payload(),
    )

    assert calls == ["20260402T082851Z", "20260401T160752Z"]
    assert response["source_anchor"] == str(older_capture_dir)
    assert response["current_price"] == 70123.0
    assert response["account_count"] == 1
    assert response["long_buckets"] == [
        {"price_level": 69000.0, "leverage": "cross", "volume": 250000.0}
    ]


def test_hl_public_map_rejects_unknown_variant(client: TestClient) -> None:
    response = client.get("/liquidations/hl-public-map?symbol=BTCUSDT&variant=unknown")

    assert response.status_code == 400
    assert "Unsupported Hyperliquid liq-map variant" in response.json()["detail"]
