import numpy as np
import pytest
from audience_simulator.agents import OllamaClient, evaluation_plan, policy_key
from audience_simulator.audience import generate_population
from audience_simulator.behavior import reconcile_gates, simulate_panel
from audience_simulator.schemas import AgentEvaluation, CampaignBrief, Creative


def make_brief():
    return CampaignBrief(
        name="Test",
        brand="NDL",
        product_description="Routine skincare autunno",
        vertical="beauty_skincare",
        date_from="2026-11-16",
        date_to="2026-11-16",
        creatives=[
            Creative(id="A", headline="Routine", primary_text="Scopri il kit"),
            Creative(id="B", headline="Offerta", primary_text="Un altro kit", lever="urgency"),
        ],
    )


def policy(interest=2):
    return AgentEvaluation(
        clarity=3,
        interest=interest,
        credibility=2,
        friction=2,
        conditional_action="consider_click",
        evidence=["creative.headline"],
        conditional_reaction="Potrebbe interessarmi se ne avessi bisogno.",
    ).model_dump()


def test_plan_covers_each_agent_and_creative_with_stable_keys():
    brief = make_brief()
    profiles = generate_population(brief)
    work = evaluation_plan(brief, profiles, "test-digest")
    assert len(work) == 240
    assert len({p["key"] for p in work}) == 240
    assert work == evaluation_plan(brief, profiles, "test-digest")
    changed = brief.model_copy(update={"placement": "facebook_feed"})
    assert work[0]["key"] != evaluation_plan(changed, profiles, "test-digest")[0]["key"]
    assert policy_key({"b": 2, "a": 1}) == policy_key({"a": 1, "b": 2})


def test_llm_extra_kpi_and_invalid_ordinals_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AgentEvaluation(**{**policy(), "ctr": 2})
    with pytest.raises(ValidationError):
        AgentEvaluation(**{**policy(), "interest": 20})


def test_client_validates_real_http_boundary():
    import httpx

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"message": {"content": __import__("json").dumps(policy())}, "done": True, "eval_count": 30},
        )
    )
    client = OllamaClient(transport=transport)
    result = client.evaluate({"profile": {}, "creative": {"headline": "Kit skincare"}, "regime": "ordinary"})
    assert result["evaluation"]["interest"] == 2
    assert result["tokens"] == 30


def test_novel_friction_is_hypothesis_but_fabricated_evidence_is_rejected():
    import json

    import httpx

    response = {**policy(), "frictions": ["scarcity_misinterpretation"]}
    client = OllamaClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"message": {"content": json.dumps(response)}, "done": True})
        )
    )
    assert client.evaluate({"creative": {"headline": "Kit"}})["evaluation"]["frictions"] == [
        "scarcity_misinterpretation",
        "price_unknown",
    ]
    with pytest.raises(ValueError, match="evidence"):
        client.evaluate({"creative": {}})


def test_gate_reconciliation_and_contextual_state():
    gates = np.tile([-0.8, 0.2, -1.0], (20, 1))
    for target in [0, 0.01, 0.5, 1]:
        calibrated = reconcile_gates(gates, np.ones(20) / 20, target)
        assert np.mean(np.prod(calibrated, axis=1)) == pytest.approx(target, abs=1e-10)


def test_behavior_replay_ignores_and_memory_arms_are_separate():
    brief = make_brief()
    profiles = generate_population(brief)
    records = evaluation_plan(brief, profiles, "digest")
    policies = {p["key"]: policy() for p in records}
    predictions = [
        {
            "date": "2026-11-16",
            "ad_id": c.id,
            "ctr_pred": 1.0,
            "ages": [
                {"age_band": band, "ctr_estimate": 1.0}
                for band in ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
            ],
        }
        for c in brief.creatives
    ]
    first = simulate_panel(brief, profiles, policies, records, predictions)
    second = simulate_panel(brief, profiles, policies, records, predictions)
    assert first == second
    assert len(first["events"]) == 240
    assert any(not e["noticed"] for e in first["events"])
    assert all(e["explanation"] is None for e in first["events"] if not e["noticed"])
    assert all(s["exposure_count"] == 1 for s in first["states"])
    assert all(e["exposure_context"]["placement_source"] == "scenario_assumption" for e in first["events"])
    reversed_brief = brief.model_copy(update={"creatives": list(reversed(brief.creatives))})
    other = simulate_panel(reversed_brief, profiles, policies, records, predictions)
    assert sorted(first["events"], key=lambda e: e["exposure_id"]) == sorted(
        other["events"], key=lambda e: e["exposure_id"]
    )
