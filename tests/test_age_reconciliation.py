import numpy as np
import pytest
from audience_simulator.audience import age_predictions, generate_population, reconcile_age_ctr
from audience_simulator.schemas import CampaignBrief


@pytest.mark.parametrize("base", [0, 1, 1e-9, 0.015, 0.99])
def test_reconciliation_extremes_and_zero_shares(base):
    q = np.array([0.5, 0, 0.1, 0.2, 0.1, 0.1])
    p = reconcile_age_ctr(base, q, np.array([-3, 4, 0.2, -0.5, 1, 0]))
    assert np.all((p >= 0) & (p <= 1))
    assert q @ p == pytest.approx(base, abs=1e-10)


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        reconcile_age_ctr(0.01, np.array([-1, 2]), np.zeros(2))


def test_age_scenarios_invert_without_changing_aggregate():
    q = np.full(6, 1 / 6)
    delta = np.array([-0.2, 0, 0, 0, 0.2, 0])
    p1 = reconcile_age_ctr(0.02, q, delta)
    p2 = reconcile_age_ctr(0.02, q, -delta)
    neutral = reconcile_age_ctr(0.02, q, np.zeros(6))
    assert p1[0] < p1[4] and p2[0] > p2[4]
    assert np.allclose(neutral, 0.02)


def test_population_weighted_and_heterogeneous():
    brief = CampaignBrief(
        name="Test", brand="NDL", product_description="Kit skincare", vertical="beauty_skincare"
    )
    first = generate_population(brief)
    assert first == generate_population(brief)
    assert len(first) == 120
    assert sum(p["population_weight"] for p in first) == pytest.approx(1)
    assert len({p["agent_id"] for p in first}) == 120
    assert np.std([p["category_affinity"] for p in first[:20]]) > 0.05


def test_age_totals_and_theoretical_evidence():
    draw = {
        "p": np.full((50, 1), 0.02),
        "impressions": np.full((50, 1), 10000.0),
        "spend": np.full((50, 1), 100.0),
    }
    rows = age_predictions(draw, seed=42)
    assert len(rows[0]) == 6
    assert sum(r["expected_impressions"] for r in rows[0]) == pytest.approx(10000)
    assert sum(r["clicks_estimate"] for r in rows[0]) == pytest.approx(200)
    assert all(r["evidence_level"] == "modeled_assumption" and r["cpm_pred"] is None for r in rows[0])
