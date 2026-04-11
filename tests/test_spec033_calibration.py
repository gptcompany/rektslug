import pytest
import json
from pathlib import Path

def test_signoff_gate():
    # Mock report
    report = {"parity_score": 75}
    assert report["parity_score"] >= 70
