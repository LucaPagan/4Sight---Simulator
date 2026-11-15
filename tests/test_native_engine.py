import json
from pathlib import Path

import pytest
from audience_simulator.api import create_app
from audience_simulator.cloud import CloudQuotaError
from audience_simulator.config import Settings
from audience_simulator.native_engine import DEFAULT_SLOT_MIX, slot_mix
from audience_simulator.schemas import FrequencyCap, TargetingSpec
from audience_simulator.service import SimulationService
from audience_simulator.stimulus_view import FREQUENCY
from fastapi.testclient import TestClient
from test_persona_cards import FakeWriter
from test_reactions import decision


def slot_of(user):
    return next(slot for slot, text in FREQUENCY.items() if text in user)


class FakeAgent:
    """Writes cards like the persona writer and answers reactions with a function of the person and the slot."""

    provider, model, interval = "fake", "fake-agent", 0.0

    def __init__(self, reaction=None, quota_at=None):
        self.writer, self.reaction, self.quota_at = FakeWriter(), reaction, quota_at
        self.reactions = 0

    def status(self):
        return {"ready": True, "digest": "fake-digest", "error": None}

    def generate(self, system, user, schema, **options):
        if "cards" in schema["properties"]:
            return self.writer.generate(system, user, schema, **options)
        self.reactions += 1
        if self.quota_at and self.reactions == self.quota_at:
            raise CloudQuotaError()
        values = self.reaction(user) if self.reaction else {}
        return {
            "raw": values if isinstance(values, str) else json.dumps(decision(**values)),
            "seconds": 0.01,
            "tokens": 50,
            "provider": "fake",
            "model": "fake-agent",
        }


def clicks(skip, stop, engage, click):
    return {"skip_per_100": skip, "stop_per_100": stop, "engage_per_100": engage, "click_per_100": click}


PAYLOAD = {
    "name": "Cani",
    "brand": "NDL",
    "vertical": "pet_ecommerce",
    "product_description": "Cibo per cani",
    "date_from": "2026-11-16",
    "date_to": "2026-11-17",
    "population_size": 30,
    "creatives": [
        {
            "id": "A",
            "headline": "Crocchette",
            "primary_text": "Il tuo cane merita il meglio",
            "visual_description": "Labrador",
        },
        {
            "id": "B",
            "headline": "Snack",
            "primary_text": "Premi per ogni giorno",
            "visual_description": "Biscotti",
        },
    ],
    "targeting": {"audience_intent": "ha un cane", "detailed": [{"id": "interest:dogs"}]},
}


@pytest.fixture
def service(tmp_path):
    return SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db.sqlite",
            artifact_dir=tmp_path / "artifacts",
            data_dir=Path("data"),
            queue_mode="manual",
            monte_carlo_draws=60,
        )
    )


def run_native(service, agent, payload=PAYLOAD, key="n", slots=("first", "repeat", "saturated")):
    scenario = service.create_scenario(payload)
    run = service.repo.create_run(
        scenario["id"],
        key,
        {"provider": "fake", "model": "fake-agent", "mode": "agent_native", "slots": list(slots)},
    )
    service.execute_run(run["id"], client=agent)
    return scenario, service.repo.get("simulation_runs", run["id"])


def result_of(service, run):
    assert run["completion_status"] == "complete", run
    return service.result(run["id"])


def test_slot_mix_comes_from_the_frequency_cap_or_a_declared_default():
    mix, info = slot_mix(None, {"first", "repeat", "saturated"})
    assert mix == pytest.approx(DEFAULT_SLOT_MIX) and info["source"] == "assumed_default"
    once, _ = slot_mix(
        TargetingSpec(frequency_cap=FrequencyCap(max_impressions=1)), {"first", "repeat", "saturated"}
    )
    assert once == {"first": 1.0}
    six, info = slot_mix(
        TargetingSpec(frequency_cap=FrequencyCap(max_impressions=6)), {"first", "repeat", "saturated"}
    )
    assert (
        six == pytest.approx({"first": 1 / 6, "repeat": 2 / 6, "saturated": 3 / 6})
        and info["source"] == "frequency_cap"
    )
    partial, info = slot_mix(None, {"first"})
    assert partial == {"first": 1.0} and info["renormalized"]
    with pytest.raises(ValueError):
        slot_mix(TargetingSpec(frequency_cap=FrequencyCap(max_impressions=1)), {"saturated"})


def test_agent_decisions_are_the_ctr_and_the_forecast_is_only_a_reference(service):
    agent = FakeAgent(lambda user: clicks(80, 10, 2, 8))
    _, run = run_native(service, agent)
    result = result_of(service, run)
    assert result["mode"] == "agent_native" and result["quantitative_source"] == "agent_native_decisions"
    assert result["validated"] is False and result["model"]["prompt_version"] == "agent-reaction-v8.1"
    for row in result["predictions"]:
        assert row["ctr_pred"] == pytest.approx(8.0)  # every reached persona says 8 clicks per 100
        assert row["expected_clicks"] == pytest.approx(row["expected_impressions"] * 0.08)
        assert row["reference_forecast"]["ctr_pred"] != pytest.approx(8.0)
        assert row["ctr_interval"][0] - 1e-9 <= row["ctr_pred"] <= row["ctr_interval"][1] + 1e-9
        assert sum(a["clicks_estimate"] for a in row["ages"]) == pytest.approx(row["expected_clicks"])
        assert (
            "agent_native_decisions_as_ctr" in row["assumptions"]
            and row["confidence_status"] == "unvalidated"
        )
    status = result["report"]["measurement_status"]
    assert status["agent_decisions_are_the_estimate"] and status["human_validated"] is False
    assert status["stated_action_used_in_gates"] is True and status["domain"] == "unverified"
    assert result["comparison"]["domain_assessment"]["verified"] is False
    assert any("non validata" in limit for limit in result["report"]["limitations"])
    divergence = result["report"]["native"]["divergence"]
    assert {d["ad_id"] for d in divergence} == {"A", "B"} and all(d["diverges"] for d in divergence)


def test_each_persona_decision_moves_the_result_and_segments_show_why(service):
    def reaction(user):
        return clicks(60, 20, 0, 20) if "Ha un cane" in user else clicks(97, 2, 0, 1)

    result = result_of(service, run_native(service, FakeAgent(reaction))[1])
    segments = {s["ad_id"]: s["segments"] for s in result["report"]["native"]["breakdowns"]}["A"]
    pets = {s["key"]: s for s in segments["pet_species"]}
    assert pets["dog"]["ctr_pct"] == pytest.approx(20.0) and pets["none"]["ctr_pct"] == pytest.approx(1.0)
    ideal = {s["key"]: s for s in segments["in_ideal_target"]}
    assert ideal["true"]["ctr_pct"] > ideal["false"]["ctr_pct"] if "false" in ideal else True
    overall = result["predictions"][0]["ctr_pred"]
    assert 1.0 < overall < 20.0
    assert all(s["low_sample"] == (s["personas"] < 8) for dim in segments.values() for s in dim)
    assert {s["key"] for s in segments["age_band"]} <= {"18-24", "25-34", "35-44", "45-54", "55-64", "65+"}


def test_frequency_slots_are_mixed_by_the_assumed_impression_shares(service):
    by_slot = {
        "first": clicks(70, 10, 0, 20),
        "repeat": clicks(85, 5, 0, 10),
        "saturated": clicks(97, 2, 0, 1),
    }
    result = result_of(service, run_native(service, FakeAgent(lambda user: by_slot[slot_of(user)]))[1])
    expected = 0.45 * 20 + 0.35 * 10 + 0.20 * 1
    assert result["predictions"][0]["ctr_pred"] == pytest.approx(expected)
    capped = {
        **PAYLOAD,
        "targeting": {**PAYLOAD["targeting"], "frequency_cap": {"max_impressions": 1, "days": 7}},
    }
    again = result_of(
        service, run_native(service, FakeAgent(lambda user: by_slot[slot_of(user)]), capped, "m")[1]
    )
    assert again["predictions"][0]["ctr_pred"] == pytest.approx(20.0)
    assert again["report"]["native"]["slot_mix"]["info"]["source"] == "frequency_cap"


def test_trace_events_share_uniforms_across_creatives_and_carry_the_decision(service):
    result = result_of(service, run_native(service, FakeAgent(lambda user: clicks(70, 10, 5, 15)))[1])
    events = result["behavior"]["events"]
    assert len(events) == 30 * 2 * 2 and all(e["stated_action_used_in_gates"] for e in events)
    paired = {}
    for e in events:
        paired.setdefault((e["agent_id"], e["date"]), []).append(e)
    assert all(
        len({x["slot"] for x in v}) == 1 and len({x["outcome"] for x in v}) == 1 for v in paired.values()
    )
    clicked = [e for e in events if e["clicked"]]
    assert clicked and all(e["outcome"] == "clicked" and e["explanation"] for e in clicked)
    assert all((e["explanation"] is None) == (e["outcome"] == "skipped") for e in events)


def test_untargeted_reach_and_legacy_modes_are_unchanged(service):
    legacy = {k: v for k, v in PAYLOAD.items() if k != "targeting"}
    scenario = service.create_scenario(legacy)
    run = service.repo.create_run(scenario["id"], "l", {"provider": "fake", "model": "m"})
    assert run["mode"] == "history_forecast" and run["slots"] is None


def test_resume_after_quota_reuses_cards_and_finished_reactions(service):
    agent = FakeAgent(quota_at=40)
    scenario, run = run_native(service, agent)
    assert run["status"] == "waiting_for_capacity" and run["completion_status"] == "partial"
    assert run["completed_policies"] == 39 and run["required_policies"] == 2 * 1 * 3 * 30 // 1 * 1
    population = service.repo.get("populations", scenario["population_id"])
    assert len(population["cards"]) == 30
    resumed = FakeAgent()
    service.execute_run(run["id"], client=resumed)
    final = service.repo.get("simulation_runs", run["id"])
    assert final["completion_status"] == "complete" and resumed.writer.calls == []
    assert resumed.reactions == 2 * 3 * 30 - 39


def test_api_requires_targeting_and_preflight_counts_cards_and_reactions(service, monkeypatch):
    client = TestClient(create_app(service=service))
    monkeypatch.setattr(service, "client", lambda provider="ollama", model=None: FakeAgent())
    plain = service.create_scenario({k: v for k, v in PAYLOAD.items() if k != "targeting"})
    denied = client.post(
        "/api/v1/simulations",
        json={"scenario_id": plain["id"], "idempotency_key": "x", "mode": "agent_native"},
    )
    assert denied.status_code == 422 and "targeting" in denied.json()["detail"]
    scenario = service.create_scenario(PAYLOAD)
    pre = client.post(
        "/api/v1/simulations/preflight",
        json={"scenario_id": scenario["id"], "mode": "agent_native", "slots": ["first", "repeat"]},
    ).json()
    assert pre["mode"] == "agent_native" and pre["required_policies"] == 2 * 2 * 30
    assert (
        pre["persona_cards_to_write"] == 30 and pre["persona_card_calls"] == 4 and pre["cached_policies"] == 0
    )
    accepted = client.post(
        "/api/v1/simulations",
        json={"scenario_id": scenario["id"], "idempotency_key": "ok", "mode": "agent_native"},
    )
    assert accepted.status_code == 202 and accepted.json()["mode"] == "agent_native"
    assert accepted.json()["slots"] == ["first", "repeat", "saturated"]
    other_mode = client.post(
        "/api/v1/simulations", json={"scenario_id": scenario["id"], "idempotency_key": "ok"}
    )
    assert other_mode.status_code == 409
