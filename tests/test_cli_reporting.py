import subprocess

import numpy as np
from audience_simulator.reporting import compare_predictions, csv_export


def test_export_neutralizes_spreadsheet_formulas_without_changing_numbers():
    raw = csv_export([{"date": "2026-11-16", "ad_id": "=HYPERLINK(1)", "ctr_pred": -0.2, "ages": []}]).decode(
        "utf-8-sig"
    )
    assert "'=HYPERLINK(1)" in raw
    assert "-0.2" in raw


def test_equal_predictions_are_practical_tie():
    rows = [
        {"ad_id": ad, "expected_impressions": 1000, "expected_clicks": 10, "expected_spend": 10}
        for ad in ["A", "B"]
    ]
    result = compare_predictions(rows, {"p": np.full((30, 2), 0.01), "impressions": np.full((30, 2), 1000)})
    assert result["pairwise"][0]["status"] == "practical_tie"
    assert result["pairwise"][0]["winner"] is None


def test_cli_audit_works_without_network():
    result = subprocess.run(
        [".venv/bin/python", "-m", "audience_simulator.cli", "audit"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert '"storico_giornaliero.csv": 1879' in result.stdout
