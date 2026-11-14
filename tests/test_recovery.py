import httpx
from audience_simulator.agents import OllamaClient
from audience_simulator.config import Settings
from audience_simulator.service import SimulationService
from test_simulation_api import brief, fake_ollama


def test_atomic_job_claim_prevents_duplicate_execution(tmp_path):
    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art", queue_mode="manual")
    )
    scenario = service.create_scenario(brief())
    run = service.repo.create_run(scenario["id"], "claim")
    assert service.repo.claim_run(run["id"]) is True
    assert service.repo.claim_run(run["id"]) is False


def test_capacity_resume_only_evaluates_missing_policy(tmp_path):
    cfg = Settings(
        database_url=f"sqlite:///{tmp_path}/db",
        artifact_dir=tmp_path / "art",
        queue_mode="manual",
        max_evaluations=1,
        monte_carlo_draws=20,
    )
    service = SimulationService(cfg)
    scenario = service.create_scenario(brief())
    run = service.repo.create_run(scenario["id"], "capacity")
    client = OllamaClient(transport=httpx.MockTransport(fake_ollama))
    service.execute_run(run["id"], client)
    first = service.repo.get("simulation_runs", run["id"])
    assert first["status"] == "waiting_for_capacity"
    assert first["completed_policies"] == 1
    saved = service.repo.list("agent_evaluations")[0]
    cfg.max_evaluations = 1000
    service.execute_run(run["id"], client)
    assert service.repo.get("simulation_runs", run["id"])["completion_status"] == "complete"
    assert service.repo.get_policy(saved["id"])["created_at"] == saved["created_at"]
