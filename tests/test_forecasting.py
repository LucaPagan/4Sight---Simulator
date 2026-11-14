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


def test_new_campaign_backtest_excludes_whole_adset_and_keeps_future_outcomes_out(kit, monkeypatch):
    import pandas as pd
    from audience_simulator import forecasting as module
    from audience_simulator.forecasting import validate_new_campaigns

    original_forecast = module.forecast
    launch_ages = []

    def capture_features(fold_kit, model, rows, **kwargs):
        features = build_features(fold_kit, rows, model.cutoff)
        launch_ages.append(features.loc[rows.data.to_numpy() == rows.data.min(), "age_days"].tolist())
        return original_forecast(fold_kit, model, rows, **kwargs)

    monkeypatch.setattr(module, "forecast", capture_features)
    # Two adsets suffice to exercise exclusion without rerunning twelve fits in this unit test.
    ids = sorted(kit["history"].adset_id.unique())[:2]
    small = {**kit, "history": kit["history"].loc[kit["history"].adset_id.isin(ids)].copy()}
    # Imported catalogues may legitimately already use the validator's generated prefix.
    small["assets"] = pd.concat(
        [kit["assets"], kit["assets"].assign(asset_id="new-" + kit["assets"].asset_id)], ignore_index=True
    )
    report = validate_new_campaigns(small, n_draws=20)
    assert len(report["folds"]) == 2
    assert report["source_type"] == "simulated_kit"
    assert report["certified"] is False
    assert report["validation_rows"] == len(small["history"].loc[small["history"].data > "2026-11-01"])
    for fold in report["folds"]:
        assert fold["held_out_adset"] not in fold["training_adsets"]
        assert fold["training_cutoff"] == "2026-11-01"
        assert fold["all_rows_cold_start"]
        assert fold["ctr_weighted_mae_pp"] >= 0
    changed = {**small, "history": small["history"].copy()}
    changed["history"].loc[changed["history"].data > "2026-11-01", "click"] = 0
    other = validate_new_campaigns(changed, n_draws=20)
    assert [f["forecast_hash"] for f in report["folds"]] == [f["forecast_hash"] for f in other["folds"]]
    assert report["ctr_weighted_mae_pp"] != other["ctr_weighted_mae_pp"]
    assert launch_ages and all(age == 0 for group in launch_ages for age in group)


def test_new_brief_cannot_borrow_history_by_reusing_an_old_ad_id(kit, models, tmp_path):
    from audience_simulator.config import Settings
    from audience_simulator.schemas import CampaignBrief, Creative
    from audience_simulator.service import SimulationService

    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art", monte_carlo_draws=20)
    )
    service.kit, service.models = kit, models
    old_id = sorted(models.known_ads)[0]
    creative = Creative(id=old_id, headline="Nuovo prodotto", primary_text="Una creatività mai pubblicata")
    brief = CampaignBrief(
        name="Nuova campagna",
        brand="Nuovo brand",
        vertical="abbigliamento",
        product_description="Un nuovo abito",
        date_from="2026-11-16",
        date_to="2026-11-16",
        creatives=[creative],
    )
    first, _ = service.predict_brief(brief)
    renamed = brief.model_copy(update={"creatives": [creative.model_copy(update={"id": "a-fresh-id"})]})
    second, _ = service.predict_brief(renamed)
    assert first[0]["cold_start"] is True
    assert first[0]["ad_id"] == old_id
    for field in ["ctr_pred", "cpm_pred", "expected_clicks", "expected_spend"]:
        assert first[0][field] == pytest.approx(second[0][field], abs=1e-12)


def test_new_brief_does_not_borrow_a_colliding_historical_adset(kit, tmp_path):
    from audience_simulator.config import Settings
    from audience_simulator.schemas import CampaignBrief, Creative
    from audience_simulator.service import SimulationService

    changed = {**kit, "history": kit["history"].copy()}
    changed["history"].loc[changed["history"].adset_id == "CDF-AS1", "adset_id"] = "user-adset"
    models = ForecastModels.fit(changed)
    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art", monte_carlo_draws=20)
    )
    service.kit, service.models = changed, models
    brief = CampaignBrief(
        name="Nuovo",
        brand="Nuovo",
        vertical="pet_ecommerce",
        product_description="Cibo animali",
        date_from="2026-11-16",
        date_to="2026-11-16",
        creatives=[Creative(id="fresh", headline="Un nuovo prodotto", primary_text="Scopri il prodotto")],
    )
    actual, _ = service.predict_brief(brief)
    scenario_kit, rows = service.rows_for_brief(brief)
    rows["adset_id"] = "a-never-seen-adset"
    expected, _ = forecast(scenario_kit, models, rows, seed=brief.seed, n_draws=20)
    assert actual[0]["adset_id"] == "user-adset"
    for field in ["ctr_pred", "cpm_pred", "expected_clicks", "expected_spend"]:
        assert actual[0][field] == pytest.approx(expected[0][field], abs=1e-12)
