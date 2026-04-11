import pytest
import json
from pathlib import Path
from scripts.generate_public_parity_report import generate_parity_report

def test_generate_report_creates_artifact(tmp_path):
    report_data = {"metrics": {"parity_score": 85}}
    output_path = tmp_path / "report.json"
    generate_parity_report(report_data, output_path)
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert data["metrics"]["parity_score"] == 85
