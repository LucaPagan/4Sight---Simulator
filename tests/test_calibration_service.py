import json
from pathlib import Path

import httpx
import pytest
from audience_simulator import domain as domain_module
from audience_simulator.agents import PROMPT_VERSION, OllamaClient
from audience_simulator.calibration import FEATURES
from audience_simulator.domain import Domain, DomainEntry, VerifiedConfig
from audience_simulator.schemas import CampaignBrief
from audience_simulator.service import CALIBRATION_KEY
from test_simulation_api import brief, service  # noqa: F401

pytestmark = pytest.mark.skipif(
    not Path("data/storico_giornaliero.csv").exists(), reason="Kit CSV non distribuito"
)


def creative_dependent_ollama(request):
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b", "digest": "d", "size": 1}]})
    interest = 4 if "Routine" in json.loads(request.content)["prompt"] else 1
    return httpx.Response(
        200,
        json={
            "response": json.dumps(
                {
                    "clarity": 2,
                    "interest": interest,
                    "credibility": 2,
                    "friction": 2,
                    "conditional_action": "defer",
                    "frictions": [],
                    "evidence": ["creative.headline"],
                    "unknowns": [],
                    "conditional_reaction": "Il titolo della crema mi dice qualcosa.",
                }
            ),
            "done": True,
            "eval_count": 10,
        },
    )


def artifact(passed=True):
    weights = dict.fromkeys(FEATURES, 0.0) | {"interest": 0.8}
    return {
        "version": "calibration-v1",
        "features": FEATURES,
        "weights": weights,
        "beta": 1.0 if passed else 0.0,
        "gate": {"passed": passed},
    }


def verify_domain(monkeypatch):
    entry = DomainEntry(
        domain=Domain.from_brief(CampaignBrief.model_validate(brief())),
        verified_for=[VerifiedConfig(prompt_version=PROMPT_VERSION, model="qwen3.5:9b", benchmark_id="t")],
    )
    monkeypatch.setattr(domain_module, "VERIFIED_DOMAINS", (entry,))


def run(service, key):  # noqa: F811
    scenario = service.create_scenario(brief())
    record = service.repo.create_run(scenario["id"], key)
    service.execute_run(
        record["id"], client=OllamaClient(transport=httpx.MockTransport(creative_dependent_ollama))
    )
    return service.result(record["id"])


def by_ad(result):
    return {p["ad_id"]: p for p in result["predictions"]}


def test_without_a_calibration_the_panel_does_not_move_kpis(service):  # noqa: F811
    result = run(service, "plain")
    assert result["panel_calibration"]["applied"] is False
    pair = result["report"]["comparison"]["pairwise"][0]
    assert pair["decision"] == "out_of_domain"
    assert result["report"]["comparison"]["domain_assessment"]["verified"] is False
    assert result["quantitative_source"] == "historical_baseline_with_age_reconciliation"
    assert result["report"]["measurement_status"]["agents_change_aggregate_kpis"] is False
    assert (
        result["report"]["measurement_status"]["delivery"]["mode"]
        == "history_allocation_independent_of_panel"
    )


def test_calibrated_shift_needs_a_passed_gate_and_a_verified_domain(service, monkeypatch):  # noqa: F811
    service.store.write_json(CALIBRATION_KEY, artifact(passed=True))
    unverified = run(service, "unverified")
    assert unverified["panel_calibration"]["applied"] is False
    assert unverified["panel_calibration"]["domain_status"] == "out_of_domain"
    verify_domain(monkeypatch)
    service.store.write_json(CALIBRATION_KEY, artifact(passed=False))
    failed = run(service, "failed-gate")
    assert failed["panel_calibration"]["applied"] is False
    assert "fuori campione" in failed["panel_calibration"]["reason"]


def test_verified_calibration_moves_ctr_relatively_and_leaves_delivery_alone(service, monkeypatch):  # noqa: F811
    baseline = by_ad(run(service, "baseline"))
    service.store.write_json(CALIBRATION_KEY, artifact(passed=True))
    verify_domain(monkeypatch)
    result = run(service, "calibrated")
    assert result["panel_calibration"]["applied"] is True
    assert result["report"]["comparison"]["pairwise"][0]["decision"] in {"winner", "unresolvable_difference"}
    assert result["quantitative_source"] == "historical_baseline_with_calibrated_panel_shift"
    assert result["report"]["measurement_status"]["agents_change_aggregate_kpis"] is True
    shifted = by_ad(result)
    assert shifted["B"]["ctr_pred"] > baseline["B"]["ctr_pred"]
    assert shifted["A"]["ctr_pred"] < baseline["A"]["ctr_pred"]
    for ad in ("A", "B"):
        assert shifted[ad]["expected_impressions"] == pytest.approx(baseline[ad]["expected_impressions"])
        assert shifted[ad]["expected_spend"] == pytest.approx(baseline[ad]["expected_spend"])
        assert "panel_ctr_shift_calibrated" in shifted[ad]["assumptions"]
        ages = shifted[ad]["ages"]
        assert sum(a["clicks_estimate"] for a in ages) == pytest.approx(shifted[ad]["expected_clicks"])
