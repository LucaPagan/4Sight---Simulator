import httpx
import pandas as pd
import pytest
from audience_simulator.agents import OllamaClient
from audience_simulator.config import Settings
from audience_simulator.service import SimulationService


def source_rows():
    return pd.DataFrame(
        [
            {
                "Campaign name": "Giving Guide 2021 - Emotional",
                "Ad name": "Animal Welfare (Emotional)",
                "Text": text,
                "Impressions": n,
                "Link clicks": clicks,
                "Amount spent (USD)": spend,
                "Starts": "2021-11-30",
                "Ends": "2021-12-20",
            }
            for text, n, clicks, spend in [("Messaggio A", 1000, 10, 12), ("Messaggio B", 2000, 40, 30)]
        ]
    )


def test_public_inputs_do_not_change_when_observed_clicks_change():
    from audience_simulator.retrospective import build_case

    rows = source_rows()
    case, observations = build_case(rows)
    changed = rows.copy()
    changed["Link clicks"] = [200, 300]
    other, other_observations = build_case(changed)
    assert case == other
    assert observations != other_observations
    assert len(case["creatives"]) == 2
    assert case["context"]["vertical"] == "charitable_giving"
    assert not {"clicks", "impressions", "spend", "ctr"} & set(case["context"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("Impressions", 0),
        ("Impressions", 2.5),
        ("Link clicks", -1),
        ("Link clicks", 1001),
        ("Amount spent (USD)", float("inf")),
    ],
)
def test_invalid_real_metrics_are_rejected(field, value):
    from audience_simulator.retrospective import build_case

    rows = source_rows()
    rows[field] = rows[field].astype(float)
    rows.loc[0, field] = value
    with pytest.raises(ValueError):
        build_case(rows)


def test_missing_clicks_are_unknown_and_ambiguous_duplicate_cells_are_rejected():
    from audience_simulator.retrospective import build_case

    rows = source_rows()
    rows.loc[0, "Link clicks"] = float("nan")
    _, observed = build_case(rows)
    assert any(a["clicks"] is None for a in observed["arms"])
    with pytest.raises(ValueError, match="duplicat"):
        build_case(pd.concat([rows, rows.iloc[:1]], ignore_index=True))


def test_public_panel_resumes_and_scoring_rejects_tampered_snapshot(tmp_path, monkeypatch):
    import json

    from audience_simulator import retrospective as module
    from audience_simulator.schemas import AgentEvaluation

    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art")
    )
    raw = source_rows().to_csv(index=False).encode()
    monkeypatch.setattr(module, "SOURCE_SHA256", __import__("hashlib").sha256(raw).hexdigest())
    prepared = module.prepare_public_campaign(
        service, transport=httpx.MockTransport(lambda req: httpx.Response(200, content=raw))
    )
    case_id = prepared["case_id"]
    received = []

    def respond(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "test", "digest": "digest"}]})
        payload = json.loads(json.loads(request.content)["prompt"].split("Dati:\n")[1])
        received.append(payload)
        evaluation = AgentEvaluation(
            clarity=3,
            interest=2,
            credibility=2,
            friction=2,
            conditional_action="defer",
            evidence=["creative.primary_text"],
            conditional_reaction="Ci penserei.",
        )
        return httpx.Response(200, json={"done": True, "response": evaluation.model_dump_json()})

    client = OllamaClient(model="test", transport=httpx.MockTransport(respond))
    first = module.run_public_campaign(service, case_id, client, max_new=1)
    assert first["status"] == "partial"
    with pytest.raises(ValueError, match="incomplet"):
        module.score_public_campaign(service, first["evaluation_id"])
    result = module.run_public_campaign(service, case_id, client)
    assert result["status"] == "complete"
    assert result["required"] == result["completed"] == 240
    assert result["cached"] == 1
    assert len({json.dumps(p["profile"], sort_keys=True) for p in received}) == 120
    assert all("clicks" not in p["campaign"] and "impressions" not in p["campaign"] for p in received)
    assert "charitable" in received[0]["profile"]["category_context"]
    assert result["new_attempts"] == 239
    scored = module.score_public_campaign(service, result["evaluation_id"])
    assert sorted(a["ctr_observed_pct"] for a in scored["observed"]) == [1, 2]
    assert sorted(a["cpm_observed_usd"] for a in scored["observed"]) == [12, 15]
    assert scored["certified"] is False
    assert scored["aggregate_ctr_accuracy"] is None
    assert scored["panel_preference"] is None  # Equal votes cannot create a winner.
    assert scored["observed_difference_resolved"] is True
    assert scored["comparison_conclusion"] == "no_panel_preference"
    case_key = prepared["case_key"]
    case = service.store.read_json(case_key)
    case["context"]["clicks"] = 100
    service.store.write_json(case_key, case)
    with pytest.raises(ValueError):
        module.run_public_campaign(service, case_id, client)
    del case["context"]["clicks"]
    service.store.write_json(case_key, case)
    observation_key = case_key.replace("case.json", "observations.json")
    observed = service.store.read_json(observation_key)
    observed["arms"][0]["clicks"] = 0
    service.store.write_json(observation_key, observed)
    with pytest.raises(ValueError, match="(?i)integrit"):
        module.score_public_campaign(service, result["evaluation_id"])
    _, original_observed = module.build_case(source_rows())
    service.store.write_json(observation_key, original_observed)
    snapshot_key = result["snapshot_key"]
    snapshot = service.store.read_json(snapshot_key)
    snapshot["evaluations"][0]["response"]["interest"] = 4
    service.store.write_json(snapshot_key, snapshot)
    with pytest.raises(ValueError, match="(?i)integrit"):
        module.score_public_campaign(service, result["evaluation_id"])


def test_public_import_verifies_source_before_creating_cases(tmp_path):
    from audience_simulator.retrospective import prepare_public_campaign

    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art")
    )
    with pytest.raises(ValueError, match="checksum"):
        prepare_public_campaign(
            service, transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"bad"))
        )
    assert not list((tmp_path / "art").glob("validation/public-meta/cases/*/case.json"))


def test_public_cloud_failure_is_partial_and_reports_safe_provider_reason(tmp_path, monkeypatch):
    from audience_simulator import retrospective as module
    from audience_simulator.cloud import GeminiClient

    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art")
    )
    raw = source_rows().to_csv(index=False).encode()
    monkeypatch.setattr(module, "SOURCE_SHA256", __import__("hashlib").sha256(raw).hexdigest())
    prepared = module.prepare_public_campaign(
        service, transport=httpx.MockTransport(lambda req: httpx.Response(200, content=raw))
    )
    client = GeminiClient(
        "test-secret-key",
        free_tier_confirmed=True,
        transport=httpx.MockTransport(lambda req: httpx.Response(503)),
    )
    result = module.run_public_campaign(service, prepared["case_id"], client)
    assert result["status"] == "partial"
    assert result["completed"] == 0
    assert result["new_attempts"] == 1
    assert "503" in result["error_message"]
    assert "test-secret-key" not in str(result)
