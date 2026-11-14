import json
import stat

import httpx
import pytest
from audience_simulator.cloud import CloudQuotaError, GeminiClient, read_credentials, save_credentials
from test_agents_behavior import policy


def gemini_response(evaluation=None, status="completed"):
    return {
        "status": status,
        "model": "gemini-3.5-flash-lite",
        "steps": [
            {"type": "thought", "signature": "opaque"},
            {
                "type": "model_output",
                "content": [{"type": "text", "text": json.dumps(evaluation or policy())}],
            },
        ],
        "usage": {"total_input_tokens": 400, "total_output_tokens": 130, "total_thought_tokens": 20},
    }


def test_gemini_uses_fixed_host_private_header_stateless_schema():
    def handler(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.path == "/v1beta/interactions"
        assert request.headers["x-goog-api-key"] == "test-secret-key"
        assert "test-secret-key" not in str(request.url)
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["response_format"]["schema"]["additionalProperties"] is False
        assert body["generation_config"]["thinking_level"] == "minimal"
        assert "tools" not in body and "previous_interaction_id" not in body
        return httpx.Response(200, json=gemini_response())

    client = GeminiClient("test-secret-key", free_tier_confirmed=True, transport=httpx.MockTransport(handler))
    result = client.evaluate({"creative": {"headline": "Kit"}})
    assert result["evaluation"]["interest"] == 2
    assert result["tokens"] == 130
    assert result["thinking_used"]
    assert "test-secret-key" not in json.dumps(result)


def test_cloud_missing_key_or_free_tier_confirmation_blocks_requests():
    def handler(request):
        pytest.fail("Unconfigured cloud must not send a request")

    client = GeminiClient("", free_tier_confirmed=True, transport=httpx.MockTransport(handler))
    assert not client.status()["ready"]
    with pytest.raises(ValueError):
        client.evaluate({})
    client = GeminiClient(
        "test-secret-key", free_tier_confirmed=False, transport=httpx.MockTransport(handler)
    )
    assert not client.status()["ready"]
    with pytest.raises(ValueError):
        client.evaluate({})


def test_cloud_quota_is_resumable_without_paid_fallback():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            429, headers={"retry-after": "45"}, json={"error": {"message": "Quota exceeded"}}
        )

    client = GeminiClient("test-secret-key", free_tier_confirmed=True, transport=httpx.MockTransport(handler))
    with pytest.raises(CloudQuotaError) as exc:
        client.evaluate({})
    assert exc.value.retry_after_seconds == 45
    assert len(calls) == 1


def test_cloud_incomplete_or_fabricated_evidence_is_rejected():
    client = GeminiClient(
        "test-secret-key",
        free_tier_confirmed=True,
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=gemini_response(status="failed"))),
    )
    with pytest.raises(ValueError):
        client.evaluate({"creative": {"headline": "Kit"}})
    client = GeminiClient(
        "test-secret-key",
        free_tier_confirmed=True,
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, json=gemini_response({**policy(), "evidence": ["profile.invented"]})
            )
        ),
    )
    with pytest.raises(ValueError):
        client.evaluate({"creative": {"headline": "Kit"}})


def test_credentials_are_private_and_never_mirrored(tmp_path):
    save_credentials(tmp_path, "test-secret-key", True)
    assert read_credentials(tmp_path)["api_key"] == "test-secret-key"
    assert stat.S_IMODE((tmp_path / "runtime-credentials.json").stat().st_mode) == 0o600


def test_runtime_settings_never_return_credentials_and_run_selection_is_pinned(tmp_path):
    from audience_simulator.api import create_app
    from audience_simulator.config import Settings
    from audience_simulator.service import SimulationService
    from fastapi.testclient import TestClient
    from test_simulation_api import brief

    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art", queue_mode="manual")
    )
    http = TestClient(create_app(service))
    secret = "a-synthetic-key-for-a-test-1234"
    result = http.post(
        "/api/v1/runtime/config",
        json={"api_key": secret, "free_tier_confirmed": True, "requests_per_minute": 10},
    )
    assert result.status_code == 200
    assert secret not in result.text
    assert result.json()["gemini_configured"]
    assert secret not in http.get("/api/v1/runtime/config").text
    invalid = http.post(
        "/api/v1/runtime/config", json={"api_key": "private bad key", "free_tier_confirmed": True}
    )
    assert invalid.status_code == 422
    assert "private bad key" not in invalid.text
    scenario = service.create_scenario(brief())
    request = {
        "scenario_id": scenario["id"],
        "idempotency_key": "cloud",
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
    }
    run = http.post("/api/v1/simulations", json=request).json()
    assert run["provider"] == "gemini"
    assert run["requested_model"] == "gemini-3.5-flash-lite"
    assert (
        http.post(
            "/api/v1/simulations", json={**request, "provider": "ollama", "model": "qwen3.5:9b"}
        ).status_code
        == 409
    )
    assert secret not in json.dumps(service.repo.get("simulation_runs", run["id"]))


@pytest.mark.skipif(
    not __import__("pathlib").Path("data/storico_giornaliero.csv").exists(), reason="Kit locale richiesto"
)
def test_cloud_quota_and_resume_finish_same_provider_without_reusing_local_cache(tmp_path, monkeypatch):
    import audience_simulator.cloud as module
    from audience_simulator.agents import evaluation_plan
    from audience_simulator.audience import generate_population
    from audience_simulator.config import Settings
    from audience_simulator.schemas import CampaignBrief
    from audience_simulator.service import SimulationService
    from test_simulation_api import brief

    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    service = SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db",
            artifact_dir=tmp_path / "art",
            queue_mode="manual",
            monte_carlo_draws=20,
        )
    )
    payload = brief()
    payload["creatives"] = payload["creatives"][:1]
    scenario = service.create_scenario(payload)
    run = service.repo.create_run(
        scenario["id"], "gemini", {"provider": "gemini", "model": "gemini-3.5-flash-lite"}
    )
    calls = []

    def handler(req):
        calls.append(req)
        if len(calls) == 2:
            return httpx.Response(429, headers={"retry-after": "60"})
        return httpx.Response(200, json=gemini_response())

    client = GeminiClient("test-secret-key", free_tier_confirmed=True, transport=httpx.MockTransport(handler))
    service.execute_run(run["id"], client=client)
    state = service.repo.get("simulation_runs", run["id"])
    assert state["status"] == "waiting_for_capacity"
    assert state["completed_policies"] == 1
    assert state["completion_status"] != "complete"
    service.execute_run(run["id"], client=client)
    state = service.repo.get("simulation_runs", run["id"])
    assert state["completion_status"] == "complete", state
    assert state["completed_policies"] == 120
    assert len(calls) == 121
    result = service.result(run["id"])
    assert result["model"]["provider"] == "gemini"
    assert not result["model"]["digest_is_weights_hash"]
    assert result["model"]["prompt_version"] == result["policy_snapshot"][0]["input"]["prompt_version"]
    b = CampaignBrief.model_validate(payload)
    local = evaluation_plan(b, generate_population(b), "local-model-digest")
    assert service.repo.get_policy(local[0]["key"]) is None


def test_second_local_run_waits_while_cloud_selection_is_independent(tmp_path):
    from audience_simulator.config import Settings
    from audience_simulator.service import SimulationService

    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art", queue_mode="local")
    )
    campaign = service.repo.create("campaigns", {"name": "Busy"})
    scenario = service.repo.create("scenarios", {"campaign_id": campaign["id"]})
    active = service.repo.create_run(scenario["id"], "first")
    service.repo.update_run(active["id"], status="running")
    waiting = service.repo.create_run(scenario["id"], "second")
    service.dispatch(waiting["id"])
    assert service.repo.get("simulation_runs", waiting["id"])["status"] == "waiting_for_capacity"
    assert service.repo.get("simulation_runs", active["id"])["status"] == "running"


def test_provider_rate_limit_is_shared_by_probe_and_panel_clients(tmp_path, monkeypatch):
    import audience_simulator.cloud as module

    now = [1000.0]
    delays = []
    monkeypatch.setattr(module.time, "time", lambda: now[0])

    def wait(seconds):
        delays.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(module.time, "sleep", wait)
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=gemini_response()))
    kwargs = dict(
        api_key="test-secret-key",
        free_tier_confirmed=True,
        requests_per_minute=10,
        transport=transport,
        rate_limit_path=tmp_path / "rate",
    )
    panel = GeminiClient(**kwargs)
    probe = GeminiClient(**kwargs)
    payload = {"creative": {"headline": "Kit"}}
    panel.evaluate(payload)
    probe.evaluate(payload)
    panel.evaluate(payload)
    assert delays == [6.0, 6.0]
