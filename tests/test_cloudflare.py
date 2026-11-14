import json

import httpx
import pytest
from audience_simulator.cloud import CloudQuotaError
from audience_simulator.cloudflare import CloudflareClient
from test_agents_behavior import policy


def test_cloudflare_fixed_account_endpoint_and_strict_response():
    def handler(req):
        assert req.url.host == "api.cloudflare.com"
        assert req.url.path == "/client/v4/accounts/" + "a" * 32 + "/ai/v1/chat/completions"
        assert req.headers["authorization"] == "Bearer test-token"
        body = json.loads(req.content)
        assert body["model"] == "@cf/google/gemma-4-26b-a4b-it"
        assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        assert body["store"] is False
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(policy())}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
                "model": body["model"],
            },
        )

    c = CloudflareClient(
        "test-token", "a" * 32, free_tier_confirmed=True, transport=httpx.MockTransport(handler)
    )
    result = c.evaluate({"creative": {"headline": "Kit"}})
    assert result["evaluation"]["interest"] == 2
    assert result["estimated_neurons"] == pytest.approx(14.5456)
    assert result["provider"] == "cloudflare"
    assert "test-token" not in json.dumps(result)


def test_cloudflare_quota_and_paid_models_cannot_trigger_fallback():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(429)

    c = CloudflareClient(
        "test-token", "a" * 32, free_tier_confirmed=True, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(CloudQuotaError):
        c.evaluate({})
    assert len(calls) == 1
    with pytest.raises(ValueError):
        CloudflareClient("test-token", "a" * 32, model="@cf/zai-org/glm-5.3")
    with pytest.raises(ValueError):
        CloudflareClient("test-token", "../../other")


def test_cloudflare_truncated_and_extra_numeric_kpi_are_rejected():
    for finish, evaluation in [("length", policy()), ("stop", {**policy(), "ctr": 99})]:
        c = CloudflareClient(
            "test-token",
            "a" * 32,
            free_tier_confirmed=True,
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "choices": [{"finish_reason": finish, "message": {"content": json.dumps(evaluation)}}]
                    },
                )
            ),
        )
        with pytest.raises(ValueError):
            c.evaluate({"creative": {"headline": "Kit"}})


def test_cloudflare_credentials_are_separate_from_gemini(tmp_path):
    from audience_simulator.api import create_app
    from audience_simulator.cloud import read_credentials
    from audience_simulator.config import Settings
    from audience_simulator.service import SimulationService
    from fastapi.testclient import TestClient

    s = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art", queue_mode="manual")
    )
    http = TestClient(create_app(s))
    first = "a-gemini-test-secret-key-12345"
    second = "a-cloudflare-test-token-12345"
    assert (
        http.post("/api/v1/runtime/config", json={"api_key": first, "free_tier_confirmed": True}).status_code
        == 200
    )
    response = http.post(
        "/api/v1/runtime/config",
        json={
            "provider": "cloudflare",
            "api_key": second,
            "account_id": "a" * 32,
            "free_tier_confirmed": True,
            "requests_per_minute": 30,
        },
    )
    assert response.status_code == 200
    assert second not in response.text and first not in response.text
    assert response.json()["configured"]
    assert read_credentials(tmp_path / "art")["api_key"] == first
    assert read_credentials(tmp_path / "art", "cloudflare")["api_key"] == second
    runtime = http.get("/api/v1/runtime/status?provider=cloudflare").json()
    assert runtime["ready"]
    assert runtime["daily_free_neurons"] == 10000
    assert not runtime["digest_is_weights_hash"]
