import json
from pathlib import Path

import httpx
import pytest
from audience_simulator.creative_quality import (
    audit_creative,
    audit_shifts,
    creative_checks,
    decision_problem,
    enforce_consistency,
    heuristic_problems,
    panel_flags,
    shift_for,
)
from audience_simulator.reactions import validate_decision
from audience_simulator.schemas import CampaignBrief
from test_native_engine import PAYLOAD, FakeAgent, clicks, result_of, run_native, service  # noqa: F401
from test_reactions import decision


def validated(**changes):
    return validate_decision(json.dumps(decision(**changes)))[0]


def test_a_person_who_calls_the_ad_nonsense_cannot_click_it():
    result = validated(
        ad_problem="nonsense",
        skip_per_100=70,
        stop_per_100=20,
        engage_per_100=5,
        click_per_100=5,
        frictions=["senza_senso"],
    )
    assert result["click_per_100"] == 0 and result["engage_per_100"] == 2
    assert result["skip_per_100"] == 78 and result["stop_per_100"] == 20
    assert sum(result[f"{n}_per_100"] for n in ("skip", "stop", "engage", "click")) == 100
    assert result["gates"] == {"notice": 0.22, "engage": 0.02, "click": 0.0}
    assert result["consistency_enforced"] is True and result["ad_problem_source"] == "model"


def test_the_words_of_the_frictions_back_up_a_model_that_forgot_the_field():
    result = validated(ad_problem="none", frictions=["messaggio_offensivo"], click_per_100=10)
    assert result["ad_problem"] == "offensive" and result["ad_problem_source"] == "friction_text"
    assert result["click_per_100"] == 0
    # An ordinary objection is not a broken ad.
    fine = validated(frictions=["prezzo_non_chiaro"], click_per_100=10)
    assert fine["click_per_100"] == 10 and fine["consistency_enforced"] is False
    # "senso di fastidio" is not "senza senso".
    assert decision_problem({"frictions": ["senso_di_fastidio"]}) == ("none", "model")


def test_confusing_and_fine_ads_keep_the_numbers_the_model_gave():
    for problem in ("none", "confusing"):
        result = validated(ad_problem=problem, click_per_100=10)
        assert result["click_per_100"] == 10 and result["consistency_enforced"] is False
    assert enforce_consistency([70, 20, 5, 5], "confusing") == ([70, 20, 5, 5], False)
    assert enforce_consistency([70, 20, 5, 5], "off_topic") == ([78, 20, 2, 0], True)


def flagged(creative, problems):
    return [{"creative_id": creative, "decision": {"ad_problem": p, "frictions": []}} for p in problems]


def test_panel_flags_need_a_majority_to_call_a_creative_problematic():
    records = (
        flagged("B", ["nonsense"] * 6 + ["none"] * 2)
        + flagged("A", ["none"] * 7 + ["confusing"])
        + flagged("C", ["offensive"] * 2 + ["none"] * 6)
        + flagged("D", ["nonsense"] * 3)
    )
    status = {f["creative_id"]: f["status"] for f in panel_flags(records)}
    assert status == {"A": "ok", "B": "problematic", "C": "watch", "D": "insufficient_data"}
    b = next(f for f in panel_flags(records) if f["creative_id"] == "B")
    assert b["broken_share"] == 0.75 and b["problems"] == {"nonsense": 6}


def test_rules_catch_placeholders_shouting_and_repetition_without_a_model():
    ok = {
        "id": "A",
        "headline": "Pelle luminosa in 4 settimane",
        "primary_text": "Il kit routine con recensioni.",
    }
    assert heuristic_problems(ok) == ([], 5)
    lorem = {"id": "B", "headline": "Lorem ipsum offerta", "primary_text": "dolor sit amet"}
    assert heuristic_problems(lorem) == (["nonsense"], 1)
    shout = {"id": "C", "headline": "CLICCA QUI!!! VINCI SUBITO", "primary_text": "Offerta"}
    assert heuristic_problems(shout) == (["spam"], 3)
    repeat = {"id": "D", "headline": "Offerta", "primary_text": "click click click"}
    assert heuristic_problems(repeat) == (["spam"], 2)
    assert heuristic_problems({"id": "E", "headline": "Ciao", "primary_text": ""})[1] == 1


def test_audit_penalty_is_zero_for_a_sound_creative_and_grows_with_the_worst_flaw():
    shifts = [shift_for(w) for w in (5, 4, 3, 2, 1)]
    assert shifts[0] == 0 and shifts == sorted(shifts, reverse=True) and shifts[-1] == pytest.approx(-2.0)
    assert shifts[1] > -0.2  # a merely modest creative is barely touched


class AuditClient:
    model = "audit-fake"

    def __init__(self, scores, problems=(), raw=None):
        self.scores, self.problems, self.raw, self.calls = scores, list(problems), raw, 0

    def generate(self, system, user, schema, **options):
        self.calls += 1
        assert options["temperature"] == 0 and "hostility" in schema["properties"]
        assert "Odio i cani" in user  # the creative reaches the reviewer as data
        raw = self.raw or json.dumps(
            {
                "comprehensible": self.scores[0],
                "on_product": self.scores[1],
                "internally_consistent": self.scores[2],
                "hostility": self.scores[3],
                "problems": self.problems,
                "summary": "Dichiara di odiare ciò che vende.",
            }
        )
        return {"raw": raw}


BRIEF = CampaignBrief.model_validate(
    {
        **PAYLOAD,
        "creatives": [
            {
                "id": "B",
                "headline": "Cane Morto",
                "primary_text": "Odio i cani",
                "visual_description": "Una routine",
            },
            PAYLOAD["creatives"][0],
        ],
    }
)


def test_audit_scores_the_worst_dimension_and_is_cached(service):  # noqa: F811
    client = AuditClient((4, 1, 3, 5), ["offensive", "off_topic"])
    first = audit_creative(client, BRIEF, BRIEF.creatives[0], service.repo, "digest")
    again = audit_creative(client, BRIEF, BRIEF.creatives[0], service.repo, "digest")
    assert client.calls == 1 and again == first
    assert first["worst_score"] == 1 and first["status"] == "problematic"
    assert first["shift_logit"] == pytest.approx(-2.0) and first["problems"] == ["off_topic", "offensive"]
    assert first["source"] == "llm+rules"


def test_an_unusable_audit_answer_falls_back_to_the_rules_and_says_so():
    result = audit_creative(AuditClient(None, raw="non è json"), BRIEF, BRIEF.creatives[0])
    assert result["source"] == "rules_only" and result["shift_logit"] == 0
    assert "non valida" in result["unavailable_reason"]
    assert audit_creative(None, BRIEF, BRIEF.creatives[0], use_model=False)["unavailable_reason"] is None


def test_checks_join_audit_and_panel_and_keep_the_worse_status():
    audit = {
        "creative_id": "B",
        "status": "watch",
        "problems": ["offensive"],
        "shift_logit": -0.5,
    }
    panel = panel_flags(flagged("B", ["offensive"] * 6) + flagged("A", ["none"] * 6))
    checks = {c["creative_id"]: c for c in creative_checks(BRIEF, [audit], panel)}
    assert checks["B"]["status"] == "problematic" and "problematica" in checks["B"]["message"]
    assert checks["A"]["status"] == "ok" and checks["A"]["message"] is None
    assert audit_shifts([audit]) == {"B": -0.5}


@pytest.mark.skipif(not Path("data/storico_giornaliero.csv").exists(), reason="Kit CSV non distribuito")
def test_native_run_flags_a_creative_the_panel_calls_nonsense_and_zeroes_its_clicks(service):  # noqa: F811
    def reaction(user):
        # Same persona, same moment: only the creative differs.
        if "Snack" in user:
            return {**clicks(98, 1, 1, 0), "ad_problem": "nonsense", "frictions": ["senza_senso"]}
        return clicks(80, 10, 2, 8)

    result = result_of(service, run_native(service, FakeAgent(reaction), slots=("first",))[1])
    ctr = {p["ad_id"]: p["ctr_pred"] for p in result["predictions"]}
    assert ctr["B"] == 0 and ctr["A"] > 0
    checks = {c["creative_id"]: c for c in result["report"]["creative_checks"]}
    assert checks["B"]["status"] == "problematic" and checks["A"]["status"] == "ok"
    assert result["report"]["limitations"][0] == checks["B"]["message"]
    quality = {c["ad_id"]: c.get("quality_status") for c in result["comparison"]["creatives"]}
    assert quality == {"A": "ok", "B": "problematic"}
    assert "quality_warning" in result["comparison"]["pairwise"][0]


def ollama_with_audit(request):
    """Local runtime double: reviews «Snack» as broken, answers every evaluation like a neutral consumer."""
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b", "digest": "d", "size": 1}]})
    body = json.loads(request.content)
    if "hostility" in json.dumps(body.get("format", {})):
        broken = "Snack" in body["prompt"]
        answer = {
            "comprehensible": 1 if broken else 5,
            "on_product": 2 if broken else 5,
            "internally_consistent": 5,
            "hostility": 4 if broken else 1,
            "problems": ["nonsense", "offensive"] if broken else [],
            "summary": "Non ha senso e offende." if broken else "Regge.",
        }
    else:
        answer = {
            "clarity": 3,
            "interest": 3,
            "credibility": 3,
            "friction": 2,
            "conditional_action": "defer",
            "frictions": [],
            "evidence": ["creative.headline"],
            "unknowns": [],
            "conditional_reaction": "Il titolo mi dice qualcosa.",
        }
    return httpx.Response(200, json={"response": json.dumps(answer), "done": True, "eval_count": 10})


@pytest.mark.skipif(not Path("data/storico_giornaliero.csv").exists(), reason="Kit CSV non distribuito")
def test_historical_mode_cannot_read_the_text_but_the_audit_lowers_a_broken_creative(service):  # noqa: F811
    from audience_simulator.agents import OllamaClient

    scenario = service.create_scenario(PAYLOAD)
    record = service.repo.create_run(scenario["id"], "audit")
    service.execute_run(record["id"], client=OllamaClient(transport=httpx.MockTransport(ollama_with_audit)))
    result = service.result(record["id"])
    ctr = {p["ad_id"]: p["ctr_pred"] for p in result["predictions"]}
    # Without the audit the two creatives share the vertical's historical CTR; the penalty is the only difference.
    assert ctr["B"] < 0.3 * ctr["A"]
    assert result["quantitative_source"].endswith("_and_creative_audit")
    assert (
        "creative_audit_ctr_shift"
        in next(p for p in result["predictions"] if p["ad_id"] == "B")["assumptions"]
    )
    assert (
        "creative_audit_ctr_shift"
        not in next(p for p in result["predictions"] if p["ad_id"] == "A")["assumptions"]
    )
    checks = {c["creative_id"]: c for c in result["report"]["creative_checks"]}
    assert checks["B"]["status"] == "problematic" and checks["A"]["status"] == "ok"
    assert result["report"]["comparison"]["creatives"][0]["ad_id"] == "A"
