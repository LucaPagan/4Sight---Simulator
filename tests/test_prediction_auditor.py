import pytest
from audience_simulator.reporting import audit_predictions


def test_auditor_blocks_wrong_age_totals_and_budget():
    row = {
        "date": "2026-11-16",
        "ad_id": "A",
        "ctr_pred": 2.0,
        "cpm_pred": 10.0,
        "expected_impressions": 1000.0,
        "expected_clicks": 20.0,
        "expected_spend": 10.0,
        "ages": [
            {
                "age_band": band,
                "expected_impressions": 1000 / 6,
                "clicks_estimate": 20 / 6,
                "expected_spend": 10 / 6,
            }
            for band in ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
        ],
    }
    audit_predictions([row], 10)
    with pytest.raises(ValueError, match="budget"):
        audit_predictions([row], 9)
    row["ages"][0]["clicks_estimate"] = 0
    with pytest.raises(ValueError, match="età"):
        audit_predictions([row], 10)
