# ruff: noqa: F811
import json
import re

import pytest
from audience_simulator.cloud import CloudQuotaError
from audience_simulator.counterfactual import TESTS, build_pairs, run_counterfactuals
from audience_simulator.decision_quality import (
    THRESHOLDS,
    assess_decisions,
    eta_squared,
    export_rubric,
    inconsistencies,
    invented_numbers,
    marketer_speak,
    references_ad,
    score_rubric,
)
from audience_simulator.prompt_eval import (
    VARIANTS,
    build_without_examples,
    compare_variants,
    compare_with_v7,
    guard_split,
    paired_difference,
)
from audience_simulator.reactions import build_prompt, reaction_plan
from test_agents_behavior import policy
from test_native_engine import PAYLOAD, FakeAgent, clicks, run_native, service  # noqa: F401
from test_reactions import decision, loaded, population  # noqa: F401


def sensitive(user):
    """Reacts to the person's facts and to the ad, never to name or city."""
    skip = 70
    if "Ha un cane" in user or "Ha un gatto" in user:
        skip -= 25
    if "polizza auto" in user.lower():
        skip += 6
    if "più di quattro" in user:
        skip += 8
    if "Il suo reddito è alto" in user:
        return clicks(skip, 100 - skip - 8, 0, 8)
    return clicks(skip, 100 - skip - 1, 0, 1)


def records_for(population, reaction, slots=("first",)):
    service, scenario_id, brief, pop = loaded(population)
    plan = reaction_plan(brief, pop["profiles"], pop["cards"], "fake-digest", slots=slots)
    agent = FakeAgent(reaction)
    out = []
    for item in plan:
        raw = agent.generate("", build_prompt(item["input"])[1], {"properties": {}})["raw"]
        out.append(
            {
                **{k: item[k] for k in ("key", "agent_id", "creative_id", "slot")},
                "input": item["input"],
                "decision": json.loads(raw),
            }
        )
    return out, {p["agent_id"]: p for p in pop["profiles"]}, brief, pop, plan


def with_gates(record):
    d = record["decision"]
    d["gates"] = {"notice": (100 - d["skip_per_100"]) / 100, "engage": 0, "click": d["click_per_100"] / 100}
    return record


# --- decision quality -------------------------------------------------------------------------------------------


def record(**changes):
    payload = {
        "persona": {"fatti": ["Ha 30 anni."], "nome": "Anna"},
        "ad": {
            "al_primo_sguardo": {"visual": "Un labrador felice", "testo": "Crocchette per cani adulti"},
            "se_ti_fermi_e_leggi": {"offerta": "Spedizione gratis"},
            "dopo_il_click": {},
        },
        "situation": {"momento": "la sera"},
    }
    return {
        "key": "k",
        "agent_id": "a",
        "creative_id": "A",
        "slot": "first",
        "input": payload,
        "decision": decision(**changes),
    }


def test_grounding_marketer_language_and_invented_numbers():
    assert references_ad(
        record(first_impression="Il labrador mi ha fatto sorridere", detail_cited="labrador")
    )
    assert not references_ad(
        record(first_impression="Boh, vado avanti", detail_cited="", reaction_after_stopping="")
    )
    assert marketer_speak(record(first_impression="Il target è chiaro ma la call to action è debole"))
    assert not marketer_speak(record(first_impression="Mi piace il cane, ma non mi serve"))
    assert invented_numbers(record(reaction_after_stopping="Costa 49 euro, troppo")) == ["49"]
    assert invented_numbers(record(reaction_after_stopping="Ho 30 anni e ci penso")) == []


def test_inconsistent_decisions_are_named():
    assert "read_without_stopping" in inconsistencies(record(read_beyond_glance=True, **clicks(99, 1, 0, 0)))
    assert "reaction_after_without_stopping" in inconsistencies(record(**clicks(100, 0, 0, 0)))
    assert "clicks_but_hides" in inconsistencies(record(action_if_engaged="hide", **clicks(80, 5, 5, 10)))
    seen_later = record(read_beyond_glance=False, detail_cited="spedizione gratis")
    assert "cites_text_not_seen_at_a_glance" in inconsistencies(seen_later)
    assert inconsistencies(record()) == []


def test_eta_squared_measures_how_much_an_attribute_explains():
    assert eta_squared([1, 1, 5, 5], ["a", "a", "b", "b"]) == pytest.approx(1.0)
    assert eta_squared([1, 5, 1, 5], ["a", "a", "b", "b"]) == pytest.approx(0.0)
    assert eta_squared([3, 3, 3], ["a", "b", "c"]) == 0.0


def test_panel_that_ignores_profiles_or_repeats_itself_is_flagged(population):
    constant, profiles, *_ = records_for(population, lambda user: clicks(90, 5, 2, 3))
    result = assess_decisions(constant, profiles)
    assert {"insensitive_to_profile", "uniform_decisions"} <= set(result["flags"])
    assert result["human_validated"] is False and result["thresholds"] == THRESHOLDS
    varied, profiles, *_ = records_for(population, sensitive)
    result = assess_decisions(varied, profiles)
    assert (
        "insensitive_to_profile" not in result["flags"]
        and result["profile_dependence"]["pet_species"]["notice"] > 0.05
    )
    assert set(result["by_creative"]) == {"A", "B"} and result["decisions"] == 60


def test_positivity_bias_and_implausible_rates_are_flagged(population):
    eager, profiles, *_ = records_for(population, lambda user: clicks(30, 30, 20, 20))
    result = assess_decisions(eager, profiles)
    assert "positivity_bias" in result["flags"]
    assert {"mean_notice_outside_plausible_range", "mean_click_outside_plausible_range"} <= set(
        result["warnings"]
    )
    with pytest.raises(ValueError):
        assess_decisions([])


def test_rubric_is_blind_and_scoring_compares_raters_with_the_automated_flags(population):
    records, *_ = records_for(population, sensitive)
    sheet = export_rubric(records, n=20, seed=1)
    header = sheet["csv"].splitlines()[0]
    assert header == "blind_id,ad_seen,persona,reaction,realism,profile_consistency,groundedness"
    assert "creative" not in header and len(sheet["key"]) == 20 and sheet["csv"].count("\n") == 21
    assert (
        export_rubric(records, n=20, seed=1)["key"] == sheet["key"]
        and export_rubric(records, n=20, seed=2)["key"] != sheet["key"]
    )
    import csv
    import io

    rows = list(csv.DictReader(io.StringIO(sheet["csv"])))
    rater = [{**r, "realism": "2", "profile_consistency": "1", "groundedness": "1"} for r in rows]
    other = [
        {
            **r,
            "realism": "1" if i % 2 else "2",
            "profile_consistency": "1",
            "groundedness": "2" if i % 3 else "0",
        }
        for i, r in enumerate(rows)
    ]
    scored = score_rubric({"r1": rater, "r2": other}, sheet["key"], records)
    assert scored["raters"] == 2 and scored["items"] == 20 and scored["mean"]["realism"] > 1
    assert scored["agreement"]["realism"]["items"] == 20


# --- counterfactual ---------------------------------------------------------------------------------------------


def suite(population, reaction, repo=True, **options):
    service, scenario_id, brief, pop = loaded(population)
    agent = options.pop("agent", None) or FakeAgent(reaction)
    result = run_counterfactuals(
        agent,
        brief,
        pop["profiles"],
        pop["cards"],
        "fake-digest",
        service.repo if repo else None,
        n_pairs=options.pop("n_pairs", 12),
    )
    return result, agent, (service, brief, pop)


def by_name(result):
    return {t["test"]: t for t in result["tests"]}


def test_pairs_differ_only_in_the_one_thing_being_tested(population):
    _, _, brief, pop = loaded(population)
    pairs = build_pairs(brief, pop["profiles"], pop["cards"], "d", n_pairs=6)
    assert {p["test"] for p in pairs} == set(TESTS)
    for pair in pairs:
        a, b = pair["a"], pair["b"]
        if pair["test"] == "placebo":
            assert (
                a["ad"] == b["ad"]
                and a["situation"] == b["situation"]
                and a["persona"]["fatti"] == b["persona"]["fatti"]
            )
            assert (a["persona"]["nome"], a["persona"]["citta"]) != (
                b["persona"]["nome"],
                b["persona"]["citta"],
            )
        if pair["test"] == "relevant_person_vs_not":
            assert (
                any("cane" in f or "gatto" in f for f in a["persona"]["fatti"])
                and "Non ha animali domestici." in b["persona"]["fatti"]
            )
            assert a["ad"] == b["ad"]
        if pair["test"] == "on_topic_vs_off_topic_ad":
            assert a["persona"] == b["persona"] and "assicurazione" in json.dumps(b["ad"]).lower()
        if pair["test"] == "first_vs_saturated":
            assert a["situation"]["frequenza"] != b["situation"]["frequenza"] and a["ad"] == b["ad"]
        if pair["test"] == "price_sensitive_vs_not":
            assert a["ad"] == b["ad"] and "129,90" in json.dumps(a["ad"], ensure_ascii=False)
            assert "reddito è alto" in " ".join(a["persona"]["fatti"]) and "reddito è basso" in " ".join(
                b["persona"]["fatti"]
            )


def test_a_persona_that_uses_its_facts_passes_and_the_placebo_is_stable(population):
    result, _, _ = suite(population, sensitive)
    tests = by_name(result)
    for name in (
        "relevant_person_vs_not",
        "on_topic_vs_off_topic_ad",
        "price_sensitive_vs_not",
        "first_vs_saturated",
    ):
        assert tests[name]["verdict"] == "sensitive", (name, tests[name])
        assert tests[name]["share_as_expected"] >= 0.7 and tests[name]["p_value"] < 0.05
    assert tests["placebo"]["stable"] is True and tests["placebo"]["mean_abs_delta"] == pytest.approx(0)
    assert (
        result["summary"]["sensitive"] == 4
        and result["validated"] is False
        and result["evidence"] == "hypothesis"
    )


def test_a_persona_that_ignores_or_reverses_its_facts_fails(population):
    flat, _, _ = suite(population, lambda user: clicks(90, 6, 2, 2), repo=False)
    assert {t["verdict"] for t in flat["tests"] if t["test"] != "placebo"} == {"insensitive"}
    reversed_, _, _ = suite(
        population,
        lambda user: (
            clicks(60, 30, 0, 10)
            if "Non ha animali" in user or "polizza auto" in user
            else clicks(95, 4, 0, 1)
        ),
        repo=False,
    )
    tests = by_name(reversed_)
    assert (
        tests["relevant_person_vs_not"]["verdict"] == "insensitive"
        and tests["relevant_person_vs_not"]["moved_against"] > 0
    )


def test_model_noise_raises_the_bar_and_fails_the_tests(population):
    def noisy(user):
        value = int(__import__("hashlib").sha256(user.encode()).hexdigest(), 16) % 60
        return clicks(30 + value, 69 - value, 0, 1)

    result, _, _ = suite(population, noisy)
    tests = by_name(result)
    assert tests["placebo"]["stable"] is False
    assert all(t["verdict"] != "sensitive" for t in result["tests"] if t["test"] != "placebo")


def test_counterfactual_answers_are_cached_and_failures_are_dropped_not_invented(population):
    first, agent, (service, brief, pop) = suite(population, sensitive)
    calls = agent.reactions
    assert calls > 0 and first["summary"]["failed_pairs"] == 0
    again = FakeAgent(sensitive)
    run_counterfactuals(again, brief, pop["profiles"], pop["cards"], "fake-digest", service.repo, 12)
    assert again.reactions == 0
    broken, _, _ = suite(population, lambda user: "non json", repo=False)
    assert broken["summary"]["failed_pairs"] == broken["summary"]["pairs_asked"] > 0
    assert all(t["pairs"] == 0 for t in broken["tests"])


def test_quota_error_stops_the_suite(population):
    with pytest.raises(CloudQuotaError):
        suite(population, sensitive, repo=False, agent=FakeAgent(sensitive, quota_at=3))


def test_service_and_api_expose_the_suite_and_the_rubric(population, monkeypatch):
    from audience_simulator.api import create_app
    from fastapi.testclient import TestClient

    service, scenario_id = population
    monkeypatch.setattr(service, "client", lambda provider="ollama", model=None: FakeAgent(sensitive))
    client = TestClient(create_app(service=service))
    answer = client.post(f"/api/v1/scenarios/{scenario_id}/quality/counterfactual", json={"n_pairs": 8})
    assert answer.status_code == 200 and answer.json()["summary"]["sensitive"] >= 1
    assert (
        client.post(
            f"/api/v1/scenarios/{scenario_id}/quality/counterfactual", json={"n_pairs": 1}
        ).status_code
        == 422
    )
    reactions = service.run_reactions(scenario_id, client=FakeAgent(sensitive), slots=("first",))
    assert reactions["quality"]["human_validated"] is False and reactions["quality"]["decisions"] == 60


def test_agent_native_run_reports_real_reaction_quality_and_exports_a_rubric(service):  # noqa: F811
    scenario, run = run_native(service, FakeAgent(sensitive))
    result = service.result(run["id"])
    quality = result["behavior"]["reaction_quality"]
    assert quality["human_validated"] is False and quality["decisions"] == 2 * 3 * 30 and "flags" in quality
    assert result["report"]["reaction_quality"] == quality
    sheet = service.rubric(run["id"], n=10, seed=3)
    assert len(sheet["key"]) == 10 and "blind_id" in sheet["csv"]
    from audience_simulator.api import create_app
    from fastapi.testclient import TestClient

    client = TestClient(create_app(service=service))
    assert client.get(f"/api/v1/simulations/{run['id']}/rubric?n=5").json()["csv"].count("\n") == 6
    assert client.get(f"/api/v1/simulations/{run['id']}/rubric?n=0").status_code == 422


# --- prompt A/B harness -----------------------------------------------------------------------------------------


def test_harness_refuses_the_locked_test_split_and_unknown_splits():
    with pytest.raises(ValueError, match="test congelato"):
        guard_split("test")
    with pytest.raises(ValueError):
        guard_split("produzione")
    guard_split("dev")
    guard_split("synthetic")


def test_no_examples_variant_removes_only_the_examples(population):
    _, _, brief, pop = loaded(population)
    payload = reaction_plan(brief, pop["profiles"][:1], pop["cards"], "d")[0]["input"]
    full = build_prompt(payload)[1]
    short = build_without_examples(payload)[1]
    assert "ESEMPI DI FORMA" in full and "ESEMPI DI FORMA" not in short
    assert short.endswith("Rispondi come questa persona con il JSON dello schema.") and "L'ANNUNCIO" in short
    assert set(VARIANTS) >= {"v8", "v8_no_examples", "v8_temperature_0", "v8_temperature_1"}


class RecordingAgent(FakeAgent):
    def __init__(self, reaction):
        super().__init__(reaction)
        self.temperatures = []

    def generate(self, system, user, schema, **options):
        if "cards" not in schema["properties"]:
            self.temperatures.append(options["temperature"])
        return super().generate(system, user, schema, **options)


def test_variants_are_compared_on_identical_exposures_with_paired_statistics(population):
    _, _, brief, pop = loaded(population)
    plan = reaction_plan(brief, pop["profiles"], pop["cards"], "d")
    agent = RecordingAgent(
        lambda user: clicks(97, 2, 0, 1) if "ESEMPI DI FORMA" not in user else clicks(88, 8, 2, 2)
    )
    report = compare_variants(
        agent, ["v8", "v8_no_examples", "v8_temperature_0"], plan, pop["profiles"], "synthetic", n=24
    )
    assert report["exposures"] == 24 and report["baseline"] == "v8"
    assert set(agent.temperatures) == {0.7, 0.0}
    no_examples = report["variants"]["v8_no_examples"]["paired_vs_baseline"]
    assert (
        no_examples["notice"]["mean_difference"] == pytest.approx(-0.09)
        and no_examples["notice"]["interval"][1] < 0
    )
    assert no_examples["notice"]["n"] == 24
    same = report["variants"]["v8_temperature_0"]["paired_vs_baseline"]["notice"]
    assert same["mean_difference"] == pytest.approx(0) and same["interval"] == pytest.approx([0, 0])
    with pytest.raises(ValueError):
        compare_variants(agent, ["v8"], plan, pop["profiles"], "test")
    again = compare_variants(
        RecordingAgent(agent.reaction), ["v8", "v8_no_examples"], plan, pop["profiles"], "synthetic", n=24
    )
    assert (
        again["variants"]["v8_no_examples"]["paired_vs_baseline"]["notice"]
        == report["variants"]["v8_no_examples"]["paired_vs_baseline"]["notice"]
    )


def test_paired_difference_handles_empty_and_constant_inputs():
    assert paired_difference([], [])["n"] == 0
    assert paired_difference([1, 2, 3], [2, 3, 4])["mean_difference"] == pytest.approx(1)


class V7Agent(FakeAgent):
    def evaluate(self, payload):
        text = (
            "Il target è chiaro"
            if payload["profile"]["age_band"] == "18-24"
            else "Mi piace il labrador nell'immagine"
        )
        return {"evaluation": {**policy(), "conditional_reaction": text}}


def test_v7_and_v8_are_compared_on_the_same_persona_creative_and_day(population):
    service, scenario_id, brief, pop = loaded(population)
    plan = reaction_plan(brief, pop["profiles"], pop["cards"], "d")
    result = compare_with_v7(V7Agent(sensitive), brief, pop["profiles"], plan, "d", "dev", n=20)
    assert result["exposures"] == 20 and result["failed"] == {"v7": 0, "v8": 0}
    assert result["v7"]["marketer_language_share"] > 0 and result["v8"]["marketer_language_share"] == 0
    assert set(result["paired_v8_minus_v7"]) == {"grounded", "marketer"}
    assert result["paired_v8_minus_v7"]["marketer"]["mean_difference"] < 0
    assert "non è confrontabile" in result["note"]
    with pytest.raises(ValueError, match="test congelato"):
        compare_with_v7(V7Agent(sensitive), brief, pop["profiles"], plan, "d", "test")
    assert re.search("dev", result["split"])
