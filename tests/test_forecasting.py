from pathlib import Path

import numpy as np
import pytest
from audience_simulator.datasets import load_dataset
from audience_simulator.forecasting import (
    ForecastModels,
    build_features,
    forecast,
    train_model_registry,
    validate_models,
)


@pytest.fixture(scope="module")
def kit():
    return load_dataset(Path("data"))


@pytest.fixture(scope="module")
def models(kit):
    return ForecastModels.fit(kit)


def test_features_do_not_change_when_validation_labels_change(kit):
    before = build_features(kit, kit["future"], "2026-11-01")
    changed = {**kit, "history": kit["history"].copy()}
    changed["history"].loc[
        changed["history"].data > "2026-11-01", ["click", "impression", "spesa", "ctr", "cpm"]
    ] = 999999
    after = build_features(changed, kit["future"], "2026-11-01")
    assert before.equals(after)
    assert not {"click", "ctr", "cpm", "spesa", "impression", "frequenza", "copertura"}.intersection(
        before.columns
    )


def test_forecast_preserves_699_rows_and_shared_budget(kit, models):
    rows, draws = forecast(kit, models, kit["future"], seed=42, n_draws=50)
    assert len(rows) == 699
    assert [r["ad_id"] for r in rows] == kit["future"].ad_id.tolist()
    assert [r["date"] for r in rows] == kit["future"].data.tolist()
    assert models.cutoff == "2026-11-01"
    for r in rows:
        assert r["expected_clicks"] == pytest.approx(r["expected_impressions"] * r["ctr_pred"] / 100)
        assert 0 <= r["ctr_pred"] <= 100
        assert r["cpm_pred"] > 0
        assert r["cpm_pred"] == pytest.approx(1000 * r["expected_spend"] / r["expected_impressions"])
    for _, indices in kit["future"].groupby(["data", "adset_id"], sort=False).groups.items():
        budget = kit["future"].loc[indices[0], "budget_giornaliero_adset"]
        assert np.all(draws["spend"][:, list(indices)].sum(axis=1) <= budget + 1e-9)
    assert all(r["confidence_status"] == "extrapolation" for r in rows if r["cold_start"])


def test_repeat_seed_and_zero_budget(kit, models):
    subset = kit["future"].iloc[:5].copy()
    subset["budget_giornaliero_adset"] = 0
    first, _ = forecast(kit, models, subset, seed=3, n_draws=20)
    second, _ = forecast(kit, models, subset, seed=3, n_draws=20)
    assert first == second
    assert all(r["expected_spend"] == r["expected_impressions"] == r["expected_clicks"] == 0 for r in first)


def test_validation_reports_only_known_period(kit, models):
    report = validate_models(kit, models, n_draws=30)
    assert report["training_rows"] == 1435
    assert report["validation_rows"] == 444
    assert report["future_test_score"] is None
    assert report["age_accuracy"] is None
    assert report["ctr_weighted_mae_pp"] >= 0
    assert 0 <= report["ctr_coverage_90"] <= 1


def test_registry_selects_candidate_and_calibrates_only_inside_training(kit):
    selected = train_model_registry(kit)
    assert selected.recipe["calibration_cutoff"] == "2026-11-01"
    assert all(f["validation_end"] <= "2026-11-01" for f in selected.recipe["inner_folds"])
    assert selected.ctr_model in {"glm_binomial", "hierarchical_smoothing"}
    choice = selected.recipe["selection"]
    assert choice["selected_log_loss"] <= choice["other_log_loss"]


def test_residual_decomposition_keeps_within_day_uncertainty():
    import pandas as pd
    from audience_simulator.forecasting import residual_components

    daily, noise = residual_components(
        pd.Series(["day1", "day1", "day2", "day2"]),
        np.array([[-1.0, -0.5, 0], [1.0, 0.5, 0], [-1.0, -0.5, 0], [1.0, 0.5, 0]]),
    )
    np.testing.assert_allclose(daily, 0)
    np.testing.assert_allclose(noise, [1.0, 0.5])
