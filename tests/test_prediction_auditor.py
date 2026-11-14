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


def test_report_separates_missing_price_from_panel_discoveries():
    from audience_simulator.reporting import build_report
    from test_agents_behavior import make_brief

    brief = make_brief()
    behavior = {
        "policy_findings": [
            dict(
                ad_id="A",
                age_band="18-24",
                policy_count=20,
                frictions={"price_unknown": 20, "unclear_benefit": 3},
                scores={},
                evidence=["creative.primary_text"],
            )
        ]
    }
    report = build_report(brief, [], behavior, {}, {"completed": 240, "required": 240})
    diagnosis = report["diagnoses"][0]
    assert "price_unknown" not in diagnosis["evidence"]["frictions"]
    assert diagnosis["evidence"]["frictions"] == {"unclear_benefit": 3}
    assert all("price_unknown" not in f["frictions"] for f in diagnosis["evidence"]["by_age"])
    assert report["input_gaps"] == [
        {
            "field": "price_eur",
            "source": "input_validation",
            "message": "Prezzo non indicato: informazione mancante nel brief.",
        }
    ]
    status = report["measurement_status"]
    assert status["aggregate_kpi_source"] == "historical_baseline"
    assert status["agents_change_aggregate_kpis"] is False
    assert status["certified"] is False
    assert status["human_observations"] == 0
