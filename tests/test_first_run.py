"""Il percorso «clona e avvia»: niente kit, niente modello, modelli deboli. Deve sempre arrivare a un risultato."""

import json

import httpx
import pytest
from audience_simulator.agents import OllamaClient
from audience_simulator.api import create_app
from audience_simulator.config import Settings
from audience_simulator.datasets import audit_dataset
from audience_simulator.demo_kit import write_demo_kit
from audience_simulator.service import SimulationService
from fastapi.testclient import TestClient
from test_native_engine import PAYLOAD, FakeAgent
from test_simulation_api import brief, fake_ollama


def make_service(tmp_path, **extra):
    return SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db.sqlite",
            artifact_dir=tmp_path / "artifacts",
            data_dir=tmp_path / "no-kit",
            queue_mode="manual",
            monte_carlo_draws=20,
            **extra,
        )
    )


def test_demo_kit_passes_the_same_audit_as_the_real_kit(tmp_path):
    audit = audit_dataset(write_demo_kit(tmp_path / "kit"))
    assert audit["errors"] == []
    assert audit["counts"]["storico_giornaliero.csv"] > 1000 and audit["cold_start_assets"]


def test_missing_kit_falls_back_to_demo_data_and_a_run_still_produces_numbers(tmp_path):
    service = make_service(tmp_path)
    assert service.demo_data and service.cfg.data_dir == tmp_path / "artifacts" / "demo-data"
    assert TestClient(create_app(service)).get("/api/v1/health").json()["demo_data"] is True
    scenario = service.create_scenario(brief())
    run = service.repo.create_run(scenario["id"], "demo")
    unreachable = OllamaClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    service.execute_run(run["id"], unreachable)
    state = service.repo.get("simulation_runs", run["id"])
    assert state["status"] == "waiting_for_runtime" and state["completion_status"] == "preliminary"
    assert len(service.result(run["id"])["predictions"]) == 2


def test_real_kit_is_preferred_over_demo_data(tmp_path):
    write_demo_kit(tmp_path / "kit")
    service = SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db.sqlite",
            artifact_dir=tmp_path / "artifacts",
            data_dir=tmp_path / "kit",
            queue_mode="manual",
        )
    )
    assert not service.demo_data and service.cfg.data_dir == tmp_path / "kit"


def test_local_model_falls_back_to_one_that_is_installed(tmp_path, monkeypatch):
    service = make_service(tmp_path, ollama_model="missing:1b")
    monkeypatch.setattr(service, "local_models", lambda: ["nomic-embed-text", "qwen3.5:9b", "llama2:7b"])
    assert service.local_model() == "qwen3.5:9b"
    monkeypatch.setattr(service, "local_models", lambda: ["nomic-embed-text", "something:1b"])
    assert service.local_model() == "something:1b"
    monkeypatch.setattr(service, "local_models", lambda: [])
    assert service.local_model() == "missing:1b"  # Ollama spento: resta il nome configurato
    monkeypatch.setattr(service, "local_models", lambda: ["missing:1b", "qwen3.5:9b"])
    assert service.local_model() == "missing:1b"


def test_model_download_reports_ollama_not_running(tmp_path):
    service = make_service(tmp_path, ollama_url="http://127.0.0.1:9")
    client = TestClient(create_app(service))
    assert client.get("/api/v1/runtime/pull").json() == {"status": "idle"}
    assert client.post("/api/v1/runtime/pull", json={"model": "bad name!"}).status_code == 422
    assert client.post("/api/v1/runtime/pull", json={}).status_code == 202
    for _ in range(100):
        state = client.get("/api/v1/runtime/pull").json()
        if state["status"] != "downloading":
            break
    assert state["status"] == "error" and "Ollama" in state["message"]
    assert client.get("/api/v1/runtime/status").json()["recommended_model"]


def test_a_second_local_run_is_not_left_waiting_for_the_first(tmp_path):
    service = make_service(tmp_path)
    scenario = service.create_scenario(brief())
    first = service.repo.create_run(scenario["id"], "one")
    service.repo.update_run(first["id"], status="running")
    second = service.repo.create_run(scenario["id"], "two")
    queued = []
    service.cfg.queue_mode = "local"
    service.executor = type("Pool", (), {"submit": lambda self, fn, *a: queued.append(a)})()
    service.dispatch(second["id"])
    assert queued and service.repo.get("simulation_runs", second["id"])["status"] == "queued"


def test_weak_model_that_never_answers_validly_does_not_block_the_run(tmp_path):
    service = make_service(tmp_path)

    def broken(request):
        if request.url.path == "/api/tags":
            return fake_ollama(request)
        return httpx.Response(200, json={"response": "non è json", "done": True})

    scenario = service.create_scenario(brief())
    run = service.repo.create_run(scenario["id"], "weak")
    service.execute_run(run["id"], OllamaClient(transport=httpx.MockTransport(broken)))
    state = service.repo.get("simulation_runs", run["id"])
    assert state["completion_status"] == "complete", state
    result = service.result(run["id"])
    assert "neutre" in result["report"]["limitations"][0]
    # Le risposte inventate per riempire il vuoto non entrano nella cache condivisa.
    assert service.repo.list("agent_evaluations") == []


def test_native_run_completes_when_reactions_are_invalid(tmp_path):
    service = make_service(tmp_path)
    agent = FakeAgent(reaction=lambda user: "non è json")
    payload = {**PAYLOAD, "population_size": 30}
    scenario = service.create_scenario(payload)
    run = service.repo.create_run(
        scenario["id"], "n", {"provider": "fake", "model": "fake-agent", "mode": "agent_native", "slots": ["first"]}
    )
    service.execute_run(run["id"], client=agent)
    state = service.repo.get("simulation_runs", run["id"])
    assert state["completion_status"] == "complete", state
    assert "neutre" in json.dumps(service.result(run["id"])["report"]["limitations"])
    assert service.repo.list("agent_decisions") == []


@pytest.mark.parametrize("vertical", ["beauty_skincare", "pet_ecommerce", "abbigliamento"])
@pytest.mark.parametrize("dates", [("2026-11-16", "2026-11-18"), ("2027-03-01", "2027-03-10"), ("2026-01-05", "2026-01-09")])
def test_any_vertical_and_period_gets_a_statistical_estimate(tmp_path, vertical, dates):
    service = make_service(tmp_path)
    scenario = service.create_scenario({**brief(), "vertical": vertical, "date_from": dates[0], "date_to": dates[1]})
    run = service.repo.create_run(scenario["id"], f"{vertical}{dates}")
    unreachable = OllamaClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    service.execute_run(run["id"], unreachable)
    predictions = service.result(run["id"])["predictions"]
    assert predictions and all(p["expected_clicks"] >= 0 and p["ctr_pred"] > 0 for p in predictions)
