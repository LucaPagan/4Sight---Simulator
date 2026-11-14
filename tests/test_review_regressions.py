import shutil
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pytest
from audience_simulator.agents import OllamaClient, calendar_regime
from audience_simulator.api import create_app
from audience_simulator.audience import age_predictions, generate_population
from audience_simulator.behavior import simulate_panel
from audience_simulator.config import Settings
from audience_simulator.service import SimulationService
from fastapi.testclient import TestClient
from test_agents_behavior import make_brief, policy
from test_simulation_api import brief, fake_ollama


def test_diagnoses_change_with_real_panel_frictions():
    from audience_simulator.reporting import build_report

    b = make_brief()
    coverage = {"required": 240, "completed": 240}
    a = {
        "policy_findings": [
            {
                "ad_id": "A",
                "frictions": {"price": 20},
                "scores": {"credibility": 1.0, "interest": 3.0},
                "evidence": ["creative.headline"],
                "age_band": "55-64",
            }
        ]
    }
    z = {
        "policy_findings": [
            {
                "ad_id": "A",
                "frictions": {"trust": 20},
                "scores": {"credibility": 1.0, "interest": 3.0},
                "evidence": ["creative.primary_text"],
                "age_band": "18-24",
            }
        ]
    }
    first = build_report(b, [], a, {}, coverage)["diagnoses"][0]
    second = build_report(b, [], z, {}, coverage)["diagnoses"][0]
    assert first["hypothesis"] != second["hypothesis"]
    assert "price" in first["evidence"]["frictions"]
    assert "trust" in second["evidence"]["frictions"]


def test_cpm_calibration_matches_ridge_when_ctr_smoothing_wins():
    from audience_simulator.datasets import load_dataset
    from audience_simulator.forecasting import ForecastModels, train_model_registry

    kit = load_dataset(Path("data"))
    selected = train_model_registry(kit)
    fold = ForecastModels.fit(kit, cutoff="2026-09-20")
    rows = kit["history"].loc[kit["history"].data == "2026-09-21"]
    _, predicted = fold.predict(kit, rows)
    expected = float(np.log(rows.cpm.to_numpy() / predicted).mean())
    assert selected.calibration_residuals[0, 1] == pytest.approx(expected, abs=1e-12)


def test_completed_resume_is_idempotent_without_runtime(tmp_path):
    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art", queue_mode="manual")
    )
    scenario = service.create_scenario(brief())
    run = service.repo.create_run(scenario["id"], "finished")
    service.repo.update_run(run["id"], status="succeeded", completion_status="complete", progress=100)
    response = TestClient(create_app(service)).post(f"/api/v1/simulations/{run['id']}/resume")
    assert response.status_code == 202
    assert response.json()["status"] == "succeeded"


def test_calendar_regimes_follow_black_friday_in_each_year():
    assert calendar_regime(date(2027, 11, 26)) == "black_friday"
    assert calendar_regime(date(2027, 11, 27)) == "post_black_friday"
    assert calendar_regime(date(2027, 11, 29)) == "cyber_monday"
    assert calendar_regime(date(2018, 11, 23)) == "black_friday"


def test_exposure_weights_reconcile_to_delivered_age_shares():
    from audience_simulator.agents import evaluation_plan

    b = make_brief()
    b.age_shares = [0.5, 0.1, 0.1, 0.1, 0.1, 0.1]
    profiles = generate_population(b)
    plan = evaluation_plan(b, profiles, "test")
    policies = {p["key"]: policy() for p in plan}
    d = {
        "p": np.full((20, 1), 0.02),
        "impressions": np.full((20, 1), 10000.0),
        "spend": np.full((20, 1), 100.0),
    }
    ages = age_predictions(d, shares=b.age_shares, effects=[-2, -1, 0, 1, 2, 3])[0]
    rows = [
        {"date": "2026-11-16", "ad_id": c.id, "ctr_pred": 2.0, "expected_impressions": 10000.0, "ages": ages}
        for c in b.creatives
    ]
    result = simulate_panel(b, profiles, policies, plan, rows)
    for creative in b.creatives:
        events = [e for e in result["events"] if e["ad_id"] == creative.id]
        assert sum(e["weight"] * e["click_probability"] for e in events) == pytest.approx(0.02, abs=1e-10)


def test_imported_dataset_applies_to_new_scenarios_but_old_snapshot_stays(tmp_path):
    shutil.copytree("data", tmp_path / "original")
    shutil.copytree("data", tmp_path / "replacement")
    file = tmp_path / "replacement/asset_creativi/asset_beauty_skincare.csv"
    file.write_text(file.read_text().replace("kit routine autunno", "kit routine aggiornato"))
    service = SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db",
            artifact_dir=tmp_path / "art",
            data_dir=tmp_path / "original",
            queue_mode="manual",
        )
    )
    first = service.create_scenario(brief())
    service.import_dataset(tmp_path / "replacement", activate=True)
    second = service.create_scenario(brief())
    assert first["dataset_path"] == str((tmp_path / "original").resolve())
    assert second["dataset_path"] == str((tmp_path / "replacement").resolve())
    assert first["dataset_id"] != second["dataset_id"]
    assert any("aggiornato" in h for h in service.ensure_kit()["assets"].headline)


def test_cancel_during_behavior_cannot_be_overwritten_by_publication(tmp_path, monkeypatch):
    import audience_simulator.service as module

    service = SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db",
            artifact_dir=tmp_path / "art",
            queue_mode="manual",
            monte_carlo_draws=20,
        )
    )
    scenario = service.create_scenario(brief())
    run = service.repo.create_run(scenario["id"], "cancel")
    actual = module.simulate_panel

    def cancel_after_behavior(*args, **kwargs):
        result = actual(*args, **kwargs)
        service.repo.update_run(run["id"], status="canceled")
        return result

    monkeypatch.setattr(module, "simulate_panel", cancel_after_behavior)
    service.execute_run(run["id"], OllamaClient(transport=httpx.MockTransport(fake_ollama)))
    state = service.repo.get("simulation_runs", run["id"])
    assert state["status"] == "canceled"
    assert state["completion_status"] != "complete"
