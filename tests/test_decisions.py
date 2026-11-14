import numpy as np
import pytest
from audience_simulator.calibration import FEATURES, fit_calibration
from audience_simulator.domain import DomainAssessment
from audience_simulator.reporting import compare_predictions
from audience_simulator.validation import interval_coverage
from test_calibration import synthetic

VERIFIED = DomainAssessment(status="verified", reason="ok", benchmark_id="b1")
OUT = DomainAssessment(
    status="out_of_domain", reason="Nessun benchmark indipendente ha ancora verificato un dominio."
)
UNVERIFIED = DomainAssessment(status="unverified_configuration", reason="prompt o modello non coincidono")


def rows_and_draws(gap):
    rng = np.random.default_rng(0)
    base = rng.normal(0.02, 0.0005, (400, 1))
    p = np.hstack([base + gap, base])
    impressions = np.full((400, 2), 10000.0)
    rows = [
        {
            "ad_id": ad,
            "expected_impressions": 10000.0,
            "expected_clicks": 10000.0 * p[:, i].mean(),
            "expected_spend": 100.0,
        }
        for i, ad in enumerate(["A", "B"])
    ]
    return rows, {"p": p, "impressions": impressions}


def test_decision_is_winner_in_a_verified_domain_when_the_difference_is_clear():
    rows, draws = rows_and_draws(0.01)
    pair = compare_predictions(rows, draws, VERIFIED)["pairwise"][0]
    assert pair["decision"] == "winner" and pair["winner"] == "A"


def test_decision_is_unresolvable_when_the_difference_is_inside_the_uncertainty():
    rows, draws = rows_and_draws(0.0002)
    pair = compare_predictions(rows, draws, VERIFIED)["pairwise"][0]
    assert pair["decision"] == "unresolvable_difference"


@pytest.mark.parametrize("assessment", [OUT, UNVERIFIED])
def test_unverified_domain_never_yields_a_verified_winner(assessment):
    rows, draws = rows_and_draws(0.01)
    result = compare_predictions(rows, draws, assessment)
    pair = result["pairwise"][0]
    assert pair["decision"] == "out_of_domain"
    assert pair["model_leader"] == "A"
    assert result["domain_assessment"]["status"] == assessment.status
    assert result["domain_assessment"]["reason"] == assessment.reason


def test_without_an_assessment_the_statistical_decision_is_kept_for_direct_callers():
    rows, draws = rows_and_draws(0.01)
    assert compare_predictions(rows, draws)["pairwise"][0]["decision"] == "winner"


def test_conformal_interval_is_stored_and_covers_new_pairs_at_about_its_level():
    train, train_features = synthetic(n_campaigns=80, signal=1.0, seed=10)
    artifact, _ = fit_calibration(train, train_features, n_boot=200)
    conformal = artifact["conformal"]
    assert conformal["level"] == 0.9 and conformal["quantile"] > 0
    test, test_features = synthetic(n_campaigns=80, signal=1.0, seed=11)
    weights = np.array([artifact["weights"][n] for n in FEATURES])
    scores = {}
    for campaign in test:
        raw = {
            a: float(weights @ np.array([f[n] for n in FEATURES]))
            for a, f in test_features[campaign.campaign_id].items()
        }
        mean = np.mean(list(raw.values()))
        scores[campaign.campaign_id] = {a: v - mean for a, v in raw.items()}
    report = interval_coverage(test, scores, artifact["gate"]["out_of_fold_scale"], conformal["quantile"])
    assert 0.8 <= report["coverage"] <= 0.97
    assert report["pairs"] == 80 * 3
