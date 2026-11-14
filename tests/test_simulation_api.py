import json
from pathlib import Path

import httpx
import pytest
from audience_simulator.agents import OllamaClient
from audience_simulator.api import create_app
from audience_simulator.config import Settings
from audience_simulator.service import SimulationService
from fastapi.testclient import TestClient


def brief():
    return {
        "name": "Test NDL",
        "brand": "NDL",
        "vertical": "beauty_skincare",
        "product_description": "Kit skincare autunno",
        "date_from": "2026-11-16",
        "date_to": "2026-11-16",
        "creatives": [
            {"id": "A", "headline": "Kit", "primary_text": "Scopri il kit"},
            {"id": "B", "headline": "Routine", "primary_text": "Una routine semplice"},
        ],
    }


def fake_ollama(request):
    if request.url.path == "/api/tags":
        return httpx.Response(
            200, json={"models": [{"name": "qwen3.5:9b", "digest": "test-digest", "size": 10}]}
        )
    return httpx.Response(
        200,
        json={
            "message": {
                "content": json.dumps(
                    {
                        "clarity": 3,
                        "interest": 2,
                        "credibility": 2,
                        "friction": 2,
                        "conditional_action": "consider_click",
                        "frictions": ["price_unknown"],
                        "evidence": ["creative.headline"],
                        "unknowns": ["Prezzo"],
                        "conditional_reaction": "Potrei guardare il kit se ne avessi bisogno.",
                    }
                )
            },
            "done": True,
            "eval_count": 40,
        },
    )


@pytest.fixture
def service(tmp_path):
    cfg = Settings(
        database_url=f"sqlite:///{tmp_path}/db.sqlite",
        artifact_dir=tmp_path / "artifacts",
        data_dir=Path("data"),
        queue_mode="manual",
        monte_carlo_draws=30,
    )
    return SimulationService(cfg)


def test_brief_validation_and_no_false_completion_when_runtime_missing(service):
    app = create_app(service=service)
    client = TestClient(app)
    assert (
        client.post("/api/v1/scenarios", json={**brief(), "age_shares": [1, 1, 1, 1, 1, 1]}).status_code
        == 422
    )
    scenario = client.post("/api/v1/scenarios", json=brief()).json()
    run = client.post(
        "/api/v1/simulations", json={"scenario_id": scenario["id"], "idempotency_key": "a"}
    ).json()
    duplicate = client.post(
        "/api/v1/simulations", json={"scenario_id": scenario["id"], "idempotency_key": "a"}
    ).json()
    assert duplicate["id"] == run["id"]
    assert client.post("/api/v1/exports", json={"run_id": run["id"]}).status_code == 409
    assert client.get("/api/v1/simulations/missing/status").status_code == 404


@pytest.mark.parametrize("vertical", ["beauty_skincare", "pet_ecommerce", "abbigliamento"])
def test_full_120_agent_simulation_and_resume_uses_snapshot(service, vertical):
    payload = {**brief(), "vertical": vertical}
    scenario = service.create_scenario(payload)
    run = service.repo.create_run(scenario["id"], "complete")
    client = OllamaClient(transport=httpx.MockTransport(fake_ollama))
    service.execute_run(run["id"], client=client)
    status = service.repo.get("simulation_runs", run["id"])
    assert status["completion_status"] == "complete", status
    assert status["completed_policies"] == status["required_policies"] == 240
    result = service.result(run["id"])
    assert len(result["profiles"]) == 120
    assert result["model"]["prompt_version"] == result["policy_snapshot"][0]["input"]["prompt_version"]
    assert all(p["input"]["campaign"]["vertical"] == vertical for p in result["policy_snapshot"])
    assert len(result["predictions"]) == 2
    assert len(result["predictions"][0]["ages"]) == 6
    assert result["quantitative_source"] == "historical_baseline_with_age_reconciliation"
    assert len(result["behavior"]["events"]) == 240
    assert result["report"]["age_accuracy"] is None
    first = service.store.path(f"runs/{run['id']}.json").read_bytes()
    service.execute_run(run["id"], client=client)
    assert service.store.path(f"runs/{run['id']}.json").read_bytes() == first
    app = TestClient(create_app(service=service))
    export = app.post("/api/v1/exports", json={"run_id": run["id"]}).json()
    downloaded = app.get(export["download_url"])
    assert downloaded.status_code == 200
    assert len(downloaded.text.strip().splitlines()) == 3


def test_origin_boundary_prevents_cross_site_write(service):
    client = TestClient(create_app(service=service))
    assert (
        client.post("/api/v1/scenarios", json=brief(), headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
