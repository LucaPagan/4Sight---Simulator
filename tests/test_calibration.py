import numpy as np
import pytest
from audience_simulator.calibration import (
    FEATURES,
    apply_ctr_shifts,
    creative_features,
    fit_calibration,
    shifts_for,
)
from audience_simulator.corpus import ComparableCampaign, CorpusDomain, Observation, Stimulus

DOMAIN = CorpusDomain(
    kind="news_headline", platform="p", country="US", language="en", objective="c", placement="x"
)


def evaluation(interest=2, clarity=2, credibility=2, friction=2, action="defer"):
    return {
        "interest": interest,
        "clarity": clarity,
        "credibility": credibility,
        "friction": friction,
        "conditional_action": action,
    }


def records(*items):
    return [{"input": {"profile": {"population_weight": w}}, "evaluation": e} for w, e in items]


def synthetic(n_campaigns=60, signal=1.0, seed=0, arms=3, impressions=200000):
    rng = np.random.default_rng(seed)
    campaigns, features = [], {}
    for c in range(n_campaigns):
        stimuli, observations, feats = [], {}, {}
        base = rng.normal(-4.5, 0.3)
        for a in range(arms):
            arm = f"c{c}a{a}"
            f = {name: float(rng.normal()) for name in FEATURES}
            logit = base + signal * 0.4 * f["interest"]
            ctr = 1 / (1 + np.exp(-logit))
            clicks = int(rng.binomial(impressions, ctr))
            stimuli.append(Stimulus(id=arm, headline=f"h {arm}"))
            observations[arm] = Observation(impressions=impressions, clicks=clicks)
            feats[arm] = f
        campaigns.append(
            ComparableCampaign(
                campaign_id=f"c{c}", source="s", domain=DOMAIN, stimuli=stimuli, observations=observations
            )
        )
        features[f"c{c}"] = feats
    return campaigns, features


def test_creative_features_are_weighted_means_of_scaled_scores_and_action_shares():
    feats = creative_features(
        records(
            (3, evaluation(interest=4, action="consider_click")),
            (1, evaluation(interest=0, action="not_interested")),
        )
    )
    assert feats["interest"] == pytest.approx((3 * 1.0 + 1 * -1.0) / 4)
    assert feats["consider_click_share"] == pytest.approx(0.75)
    assert feats["not_interested_share"] == pytest.approx(0.25)
    assert feats["clarity"] == 0


def test_creative_features_without_weights_use_equal_weights():
    plain = [
        {"input": {"profile": {}}, "evaluation": evaluation(interest=4)},
        {"input": {"profile": {}}, "evaluation": evaluation(interest=2)},
    ]
    assert creative_features(plain)["interest"] == pytest.approx(0.5)


def test_real_signal_passes_the_gate_and_gets_a_positive_scale():
    campaigns, features = synthetic(signal=1.0)
    artifact, oof = fit_calibration(campaigns, features, n_boot=300)
    assert artifact["gate"]["passed"] is True
    assert 0.5 < artifact["beta"] <= 1.0
    assert artifact["weights"]["interest"] > 0
    assert set(oof) == {c.campaign_id for c in campaigns}


def test_no_signal_fails_the_gate_and_the_panel_does_not_move_kpis():
    campaigns, features = synthetic(signal=0.0, seed=1)
    artifact, _ = fit_calibration(campaigns, features, n_boot=300)
    assert artifact["gate"]["passed"] is False
    assert artifact["beta"] == 0.0
    assert shifts_for(artifact, features["c0"]) == {k: 0.0 for k in features["c0"]}


def test_shifts_are_relative_across_the_brief_and_never_move_the_mean():
    campaigns, features = synthetic(signal=1.0)
    artifact, _ = fit_calibration(campaigns, features, n_boot=200)
    shifts = shifts_for(artifact, features["c0"])
    assert sum(shifts.values()) == pytest.approx(0, abs=1e-9)
    best = max(features["c0"], key=lambda a: features["c0"][a]["interest"])
    assert shifts[best] == max(shifts.values())


def test_single_creative_has_no_relative_information():
    campaigns, features = synthetic(signal=1.0)
    artifact, _ = fit_calibration(campaigns, features, n_boot=200)
    only = {"a": features["c0"]["c0a0"]}
    assert shifts_for(artifact, only) == {"a": 0.0}


def test_too_few_pairs_refuse_to_calibrate():
    campaigns, features = synthetic(n_campaigns=3)
    with pytest.raises(ValueError, match="coppie"):
        fit_calibration(campaigns, features)


def draws_and_predictions():
    n = 4
    impressions = np.full((200, n), 1000.0)
    p = np.full((200, n), 0.02)
    predictions = [{"ad_id": "A" if i < 2 else "B", "ctr_pred": 2.0, "assumptions": []} for i in range(n)]
    return predictions, {
        "p": p,
        "impressions": impressions,
        "clicks": impressions * p,
        "cpm": np.full((200, n), 10.0),
    }


def test_ctr_shift_changes_clicks_but_never_impressions_or_spend():
    predictions, draws = draws_and_predictions()
    spend_before = draws["impressions"] * draws["cpm"] / 1000
    apply_ctr_shifts(predictions, draws, {"A": 0.3, "B": -0.3})
    assert draws["p"][:, 0].mean() > 0.02 > draws["p"][:, 3].mean()
    assert np.allclose(draws["impressions"], 1000)
    assert np.allclose(draws["impressions"] * draws["cpm"] / 1000, spend_before)
    assert np.allclose(draws["clicks"], draws["impressions"] * draws["p"])
    assert predictions[0]["ctr_pred"] > 2.0 > predictions[3]["ctr_pred"]
    assert predictions[0]["expected_clicks"] == pytest.approx(draws["clicks"][:, 0].mean())
    assert "panel_ctr_shift_calibrated" in predictions[0]["assumptions"]


def test_zero_shift_leaves_predictions_untouched():
    predictions, draws = draws_and_predictions()
    before = draws["p"].copy()
    apply_ctr_shifts(predictions, draws, {"A": 0.0, "B": 0.0})
    assert np.array_equal(draws["p"], before)
    assert "panel_ctr_shift_calibrated" not in predictions[0]["assumptions"]
