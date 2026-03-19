import json
import logging
import runpy
import sys
import builtins
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

import src.api.examples as api_examples
import src.validation.pipeline as pipeline_exports
from src.liquidationheatmap.utils import logging_config
from src.liquidationheatmap.validation import coinglass_scraper
from src.validation.pipeline import ci_runner
from src.validation.pipeline.models import GateDecision, PipelineStatus


@dataclass
class _FakePipelineResult:
    status: PipelineStatus
    gate_2_decision: GateDecision
    overall_score: float | None = None
    overall_grade: str | None = None
    gate_2_reason: str | None = None
    error_message: str | None = None

    def to_dict(self):
        return {
            "status": self.status.value,
            "gate_2_decision": self.gate_2_decision.value,
            "overall_score": self.overall_score,
        }


def test_api_examples_expose_expected_documentation_payloads():
    assert api_examples.CALCULATE_EXAMPLES["basic"]["value"]["symbol"] == "BTCUSDT"
    assert api_examples.CALCULATE_RESPONSE_EXAMPLES["tier_3"]["value"]["tier"] == 3
    assert len(api_examples.BATCH_EXAMPLES["multiple_tiers"]["value"]["calculations"]) == 3


def test_validation_pipeline_exports_surface_expected_symbols():
    exported = set(pipeline_exports.__all__)

    assert "PipelineOrchestrator" in exported
    assert "get_dashboard_metrics" in exported
    assert pipeline_exports.PipelineOrchestrator is not None
    assert callable(pipeline_exports.get_dashboard_metrics)


def test_validation_pipeline_module_tolerates_missing_optional_imports(monkeypatch):
    original_import = builtins.__import__
    blocked = {
        "src.validation.pipeline.metrics_aggregator",
        "src.validation.pipeline.models",
        "src.validation.pipeline.orchestrator",
    }

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in blocked:
            raise ImportError(name)
        return original_import(name, globals, locals, fromlist, level)

    for name in blocked:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(builtins, "__import__", _fake_import)

    namespace = runpy.run_path(
        str((Path(pipeline_exports.__file__)).resolve()),
        run_name="pipeline_import_failure_case",
    )

    assert namespace["__all__"][-2:] == ["MetricsAggregator", "get_dashboard_metrics"]
    with pytest.raises(ImportError, match="failed to import"):
        namespace["__getattr__"]("MetricsAggregator")


def test_setup_logging_configures_handlers_and_named_loggers(monkeypatch, tmp_path):
    basic_config_calls = {}

    monkeypatch.setattr(
        logging_config.logging,
        "basicConfig",
        lambda **kwargs: basic_config_calls.update(kwargs),
    )

    log_file = tmp_path / "logs" / "app.log"
    logging_config.setup_logging(level="debug", log_file=str(log_file))

    assert log_file.parent.exists()
    assert basic_config_calls["level"] == logging.DEBUG
    assert len(basic_config_calls["handlers"]) == 2
    assert isinstance(basic_config_calls["handlers"][0], logging.FileHandler)
    assert isinstance(basic_config_calls["handlers"][1], logging.StreamHandler)
    assert logging.getLogger("uvicorn").level == logging.WARNING
    assert logging.getLogger("fastapi").level == logging.INFO


@pytest.mark.parametrize(
    ("result", "fail_on_gate_fail", "expected_exit"),
    [
        (_FakePipelineResult(PipelineStatus.FAILED, GateDecision.FAIL, error_message="boom"), True, 1),
        (_FakePipelineResult(PipelineStatus.COMPLETED, GateDecision.PASS, overall_score=91.2, overall_grade="A"), True, 0),
        (_FakePipelineResult(PipelineStatus.COMPLETED, GateDecision.ACCEPTABLE, overall_score=61.5, overall_grade="B", gate_2_reason="low recall"), True, 0),
        (_FakePipelineResult(PipelineStatus.COMPLETED, GateDecision.FAIL, overall_score=32.0, overall_grade="F", gate_2_reason="bad"), False, 0),
    ],
)
def test_run_ci_validation_returns_expected_exit_codes(monkeypatch, tmp_path, capsys, result, fail_on_gate_fail, expected_exit):
    monkeypatch.setattr(ci_runner, "run_pipeline", lambda **kwargs: result)

    output_path = tmp_path / "ci" / "result.json"
    exit_code = ci_runner.run_ci_validation(
        symbol="ETHUSDT",
        validation_types=["backtest", "realtime"],
        tolerance_pct=1.5,
        output_path=str(output_path),
        fail_on_gate_fail=fail_on_gate_fail,
    )

    assert exit_code == expected_exit
    if result.status != PipelineStatus.FAILED:
        assert output_path.exists()
        assert json.loads(output_path.read_text())["gate_2_decision"] == result.gate_2_decision.value

    output = capsys.readouterr().out
    assert "CI Validation Runner" in output
    assert "ETHUSDT" in output


def test_ci_runner_main_parses_arguments(monkeypatch):
    captured = {}

    def _fake_run_ci_validation(**kwargs):
        captured["kwargs"] = kwargs
        return 0

    monkeypatch.setattr(ci_runner, "run_ci_validation", _fake_run_ci_validation)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ci_runner.py",
            "--symbol",
            "ETHUSDT",
            "--validation-types",
            "backtest,realtime",
            "--tolerance-pct",
            "1.25",
            "--output",
            "reports/out.json",
            "--no-fail",
        ],
    )

    exit_code = ci_runner.main()

    assert exit_code == 0
    assert captured["kwargs"] == {
        "symbol": "ETHUSDT",
        "validation_types": ["backtest", "realtime"],
        "tolerance_pct": 1.25,
        "output_path": "reports/out.json",
        "fail_on_gate_fail": False,
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$0", Decimal("0")),
        ("$3.59M", Decimal("3590000")),
        ("$457.22K", Decimal("457220")),
        ("$1.2B", Decimal("1200000000")),
        ("garbage", Decimal("0")),
    ],
)
def test_parse_coinglass_value_handles_suffixes_and_bad_input(raw, expected):
    assert coinglass_scraper.parse_coinglass_value(raw) == expected


def test_extract_btc_data_from_snapshot_supports_success_and_failure_cases():
    parsed = coinglass_scraper.extract_btc_data_from_snapshot({"row": ['BTC', '$87790.8']})
    failed = coinglass_scraper.extract_btc_data_from_snapshot({"bad": object()})

    assert parsed is not None
    assert parsed.symbol == "BTC"
    assert parsed.price == Decimal("87790.8")
    assert failed is None


@pytest.mark.asyncio
async def test_fetch_our_heatmap_returns_payload_and_empty_on_failure(monkeypatch):
    class _Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: _Response({"meta": {"ok": True}}))
    assert await coinglass_scraper.fetch_our_heatmap("BTCUSDT") == {"meta": {"ok": True}}

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    assert await coinglass_scraper.fetch_our_heatmap("BTCUSDT") == {}


def test_calculate_validation_metrics_and_pipeline_history(tmp_path):
    cg_data = coinglass_scraper.CoinglassLiquidation(
        symbol="BTC",
        price=Decimal("70000"),
        long_1h=Decimal("100"),
        short_1h=Decimal("120"),
        long_24h=Decimal("500"),
        short_24h=Decimal("250"),
        timestamp=datetime.utcnow(),
    )
    our_data = {"meta": {"total_long_volume": 250, "total_short_volume": 125}}

    result = coinglass_scraper.calculate_validation_metrics(cg_data, our_data)
    assert result.long_ratio == 0.5
    assert result.short_ratio == 0.5
    assert result.price_match is True

    pipeline = coinglass_scraper.ValidationPipeline(results_dir=tmp_path)
    pipeline.log_result(result)
    history = pipeline.get_history(limit=10)
    rolling = pipeline.calculate_rolling_accuracy(window=24)

    assert len(history) == 1
    assert history[0]["symbol"] == "BTC"
    assert rolling["avg_long_ratio"] == 0.5
    assert rolling["avg_short_ratio"] == 0.5
    assert coinglass_scraper.ValidationPipeline._std([1, 2, 3]) > 0
    assert coinglass_scraper.ValidationPipeline._std([1]) == 0.0
    assert coinglass_scraper.ValidationPipeline(results_dir=tmp_path / "empty").calculate_rolling_accuracy() == {
        "error": "No history available"
    }


@pytest.mark.parametrize(
    "argv",
    [
        ["coinglass_scraper.py", "history"],
        ["coinglass_scraper.py", "accuracy"],
        ["coinglass_scraper.py"],
    ],
)
def test_coinglass_scraper_cli_paths(monkeypatch, capsys, argv, tmp_path):
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: None)

    runpy.run_path(str(Path(coinglass_scraper.__file__).resolve()), run_name="__main__")

    output = capsys.readouterr().out
    if len(argv) > 1 and argv[1] == "history":
        assert output.strip().startswith("[")
    elif len(argv) > 1 and argv[1] == "accuracy":
        assert output.strip().startswith("{")
    else:
        assert "Usage: python coinglass_scraper.py" in output
