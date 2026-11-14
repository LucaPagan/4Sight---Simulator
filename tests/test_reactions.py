import json
from pathlib import Path

import pytest
from audience_simulator.cloud import CloudQuotaError
from audience_simulator.config import Settings
from audience_simulator.persona_cards import describe_profile
from audience_simulator.reactions import (
    EVIDENCE,
    EXAMPLES,
    REACTION_PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_prompt,
    decide,
    decision_schema,
    normalize_per_100,
    reaction_plan,
    reaction_view,
    validate_decision,
)
from audience_simulator.service import SimulationService
from audience_simulator.stimulus_view import FREQUENCY, SLOTS, exposure_placement, situation, stimulus
from test_persona_cards import FakeWriter

CREATIVE = {
    "id": "A",
    "headline": "Crocchette senza cereali",
    "primary_text": "Il tuo cane merita il meglio: ingredienti semplici, carne fresca e nessun conservante. "
    * 3,
    "visual_description": "Un labrador che mangia da una ciotola",
    "cta": "Acquista ora",
    "offer": "Spedizione gratis",
    "price_text": "29,90 €",
    "landing_page_summary": "Scheda prodotto con ingredienti e recensioni",
}


def decision(**changes):
    base = {
        "first_impression": "Ho un cane, mi sono fermato a guardare la ciotola.",
        "detail_cited": "labrador",
        "read_beyond_glance": True,
        "reaction_after_stopping": "Gli ingredienti sembrano semplici, ma non so quanto costino.",
        "skip_per_100": 60,
        "stop_per_100": 25,
        "engage_per_100": 5,
        "click_per_100": 10,
        "action_if_engaged": "save",
        "post_click_intent": "browse",
        "frictions": ["prezzo_non_chiaro"],
        "evidence": ["ad.visual", "persona.facts"],
        "unknowns": ["prezzo"],
    }
    return {**base, **changes}


class FakeReactor:
    provider, model = "fake", "fake-reactor"

    def __init__(self, handler=None):
        self.calls, self.handler = [], handler

    def status(self):
        return {"ready": True, "digest": "fake-digest", "error": None}

    def generate(self, system, user, schema, **options):
        self.calls.append({"system": system, "user": user, "schema": schema, "options": options})
        value = self.handler(len(self.calls), user) if self.handler else decision()
        return {
            "raw": value if isinstance(value, str) else json.dumps(value),
            "seconds": 0.01,
            "tokens": 50,
            "provider": "fake",
            "model": "fake-reactor",
        }


def test_stimulus_shows_only_the_visible_part_of_the_caption_at_a_glance():
    seen = stimulus(CREATIVE, "instagram_feed", "mobile", "NDL")
    glance = seen["al_primo_sguardo"]
    assert glance["testo"].endswith("… altro") and len(glance["testo"]) <= 135
    assert "Sponsorizzato · NDL" == glance["inserzionista"] and glance["pulsante"] == "Acquista ora"
    assert seen["se_ti_fermi_e_leggi"]["testo_completo"] == " ".join(CREATIVE["primary_text"].split())
    assert (
        seen["se_ti_fermi_e_leggi"]["offerta"] == "Spedizione gratis"
        and "prezzo" in seen["se_ti_fermi_e_leggi"]
    )
    assert seen["dopo_il_click"] == {"pagina_di_destinazione": CREATIVE["landing_page_summary"]}
    assert "titolo" not in glance and seen["se_ti_fermi_e_leggi"]["titolo"] == CREATIVE["headline"]


def test_each_placement_shows_its_own_glance():
    stories = stimulus(CREATIVE, "instagram_stories", "mobile", "NDL")["al_primo_sguardo"]
    assert "testo" not in stories and stories["testo_sul_fotogramma"] == CREATIVE["headline"]
    facebook = stimulus(CREATIVE, "facebook_feed", "mobile", "NDL")["al_primo_sguardo"]
    assert facebook["titolo"] == CREATIVE["headline"] and "testo" in facebook
    reels = stimulus(CREATIVE, "instagram_reels", "mobile", "NDL")["al_primo_sguardo"]
    assert reels["formato"] == "video" and len(reels["testo"]) < len(facebook["testo"])
    column = stimulus(CREATIVE, "facebook_right_column", "desktop", "NDL")
    assert column["al_primo_sguardo"]["prezzo"] == "29,90 €" and "pulsante" not in column["al_primo_sguardo"]
    assert "computer" in column["dove"]
    explore = stimulus(CREATIVE, "instagram_explore", "mobile", "NDL")["al_primo_sguardo"]
    assert "testo" not in explore and "pulsante" not in explore


def test_missing_visual_and_landing_are_declared_not_invented():
    bare = {"id": "B", "headline": "Titolo", "primary_text": "Testo breve", "cta": "Scopri"}
    seen = stimulus(bare, "instagram_feed", "mobile", "NDL")
    assert "non inventarla" in seen["al_primo_sguardo"]["visual"]
    assert seen["dopo_il_click"] == {} and seen["al_primo_sguardo"]["testo"] == "Testo breve"


@pytest.fixture
def population(tmp_path):
    service = SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db.sqlite",
            artifact_dir=tmp_path / "artifacts",
            data_dir=Path("data"),
            queue_mode="manual",
            monte_carlo_draws=30,
        )
    )
    payload = {
        "name": "Cani",
        "brand": "NDL",
        "vertical": "pet_ecommerce",
        "product_description": "Cibo per cani",
        "date_from": "2026-11-16",
        "date_to": "2026-11-16",
        "population_size": 30,
        "creatives": [
            {
                "id": "A",
                "headline": "Crocchette",
                "primary_text": "Il tuo cane merita il meglio",
                "visual_description": "Labrador",
            },
            {"id": "B", "headline": "Snack", "primary_text": "Premi per ogni giorno"},
        ],
        "targeting": {"audience_intent": "ha un cane", "detailed": [{"id": "interest:dogs"}]},
    }
    scenario = service.create_scenario(payload)
    service.write_personas(scenario["id"], client=FakeWriter())
    return service, scenario["id"]


def loaded(population):
    service, scenario_id = population
    from audience_simulator.schemas import CampaignBrief

    scenario = service.repo.get("scenarios", scenario_id)
    pop = service.repo.get("populations", scenario["population_id"])
    return service, scenario_id, CampaignBrief.model_validate(scenario["brief"]), pop


def test_situation_is_stable_per_person_and_changes_with_the_frequency_slot(population):
    _, _, brief, pop = loaded(population)
    profile = pop["profiles"][0]
    first = situation(profile, brief, "first", "ordinary")
    assert first == situation(profile, brief, "first", "ordinary")
    assert first["frequenza"] == FREQUENCY["first"]
    assert situation(profile, brief, "saturated", "ordinary")["frequenza"] == FREQUENCY["saturated"]
    assert len({situation(p, brief, "first", "ordinary")["momento"] for p in pop["profiles"]}) >= 3
    assert "Black Friday" in situation(profile, brief, "first", "black_friday")["periodo"]


def test_exposure_placement_only_uses_platforms_the_person_uses(population):
    _, _, brief, pop = loaded(population)
    placements = {exposure_placement(p, brief) for p in pop["profiles"]}
    assert len(placements) >= 2
    for p in pop["profiles"]:
        placement = exposure_placement(p, brief)
        assert placement == exposure_placement(p, brief)
        if placement.startswith("instagram"):
            assert p["uses_instagram"]
        if placement.startswith("facebook") or placement.startswith("messenger"):
            assert p["uses_facebook"]


def test_plan_covers_creatives_slots_and_persons_with_unique_keys(population):
    _, _, brief, pop = loaded(population)
    plan = reaction_plan(brief, pop["profiles"], pop["cards"], "d")
    assert len(plan) == 2 * 1 * len(SLOTS) * 30 and len({i["key"] for i in plan}) == len(plan) - duplicates(
        plan
    )
    assert {i["slot"] for i in plan} == set(SLOTS)
    by_person = {}
    for item in plan:
        by_person.setdefault((item["agent_id"], item["slot"]), set()).add(
            json.dumps(item["input"]["situation"], sort_keys=True)
        )
    assert all(len(v) == 1 for v in by_person.values())  # same moment for both creatives
    with pytest.raises(ValueError, match="schede"):
        reaction_plan(brief, pop["profiles"], {}, "d")


def duplicates(plan):
    return len(plan) - len({i["key"] for i in plan})


def test_prompt_is_first_person_role_play_without_bookkeeping_or_numeric_traits(population):
    _, _, brief, pop = loaded(population)
    item = reaction_plan(brief, pop["profiles"][:1], pop["cards"], "d", slots=("repeat",))[0]
    system, user = build_prompt(item["input"])
    card = pop["cards"][item["agent_id"]]
    assert card["name"] in user and card["facts"][0] in user and "non negoziabili" in user
    assert "AL PRIMO SGUARDO".lower() in user.lower() and "Hai già visto questo annuncio" in user
    for hidden in (
        "model_digest",
        "prompt_version",
        "agent_id",
        "moment_code",
        "category_affinity",
        "population_weight",
    ):
        assert hidden not in user and hidden not in system
    assert "dopo_il_click" not in user and "Dopo il click" in user or "Se cliccassi" in user
    assert "CTR" not in system and "100" in system
    assert "model_digest" in item["input"] and "model_digest" not in reaction_view(item["input"])


def test_few_shot_examples_come_from_other_sectors_in_a_per_person_order(population):
    _, _, brief, pop = loaded(population)
    plan = reaction_plan(brief, pop["profiles"], pop["cards"], "d", slots=("first",))
    prompts = {build_prompt(i["input"])[1] for i in plan if i["creative_id"] == "A"}
    orders = set()
    for text in prompts:
        order = tuple(text.index(e["settore"]) for e in EXAMPLES)
        orders.add(tuple(sorted(range(len(order)), key=order.__getitem__)))
    assert len(orders) >= 2
    assert all("cani" not in e["settore"] and "animali" not in e["settore"] for e in EXAMPLES)
    shares = [e["risposta"]["skip_per_100"] for e in EXAMPLES]
    assert min(shares) < 60 < max(shares)  # negative, irritated and interested examples


def test_schema_is_flat_strict_and_limits_evidence_to_known_fields():
    schema = decision_schema()
    assert schema["additionalProperties"] is False and "$defs" not in json.dumps(schema)
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["evidence"]["items"]["enum"] == EVIDENCE


def test_decision_validation_normalizes_and_derives_gates():
    result, normalized = validate_decision(json.dumps(decision()))
    assert normalized == 0 and result["gates"] == {"notice": 0.4, "engage": 0.15, "click": 0.1}
    result, normalized = validate_decision(json.dumps(decision(skip_per_100=63, click_per_100=12)))
    assert normalized == 1
    assert sum(result[f"{n}_per_100"] for n in ("skip", "stop", "engage", "click")) == 100
    assert normalize_per_100([50, 30, 10, 5]) == [53, 32, 10, 5]
    for bad in (
        decision(skip_per_100=10, stop_per_100=10),
        decision(evidence=["ad.inventato"]),
        decision(action_if_engaged="compra"),
        decision(skip_per_100=0, stop_per_100=0, engage_per_100=0, click_per_100=0),
        decision(evidence=[]),
    ):
        with pytest.raises(ValueError):
            validate_decision(json.dumps(bad))


def test_decide_uses_a_seeded_warm_temperature_and_the_strict_schema(population):
    _, _, brief, pop = loaded(population)
    item = reaction_plan(brief, pop["profiles"][:1], pop["cards"], "d")[0]
    client = FakeReactor()
    out = decide(client, item["input"])
    call = client.calls[0]
    assert call["options"]["temperature"] == 0.7 and isinstance(call["options"]["seed"], int)
    assert call["schema"] == decision_schema() and out["prompt_version"] == REACTION_PROMPT_VERSION
    decide(client, item["input"])
    assert client.calls[1]["options"]["seed"] == call["options"]["seed"]
    assert out["decision"]["gates"]["click"] == 0.1 and SYSTEM_PROMPT == call["system"]


def test_service_runs_caches_and_summarizes_reactions(population):
    service, scenario_id = population
    client = FakeReactor()
    result = service.run_reactions(scenario_id, client=client, slots=("first",))
    assert (
        result["required"] == result["evaluated"] == 60 and result["failed"] == 0 and len(client.calls) == 60
    )
    assert result["validated"] is False and result["evidence"] == "hypothesis"
    assert {s["creative_id"] for s in result["summary"]} == {"A", "B"}
    assert result["summary"][0]["skip"] == 60 and result["summary"][0]["personas"] == 30
    again = FakeReactor()
    cached = service.run_reactions(scenario_id, client=again, slots=("first",), limit=10)
    assert again.calls == [] and cached["from_cache"] == 10 and cached["evaluated"] == 10


def test_invalid_answers_are_retried_once_then_counted_never_invented(population):
    service, scenario_id = population

    def handler(call, user):
        return "non è json" if call <= 2 else decision()

    client = FakeReactor(handler)
    result = service.run_reactions(scenario_id, client=client, slots=("first",), limit=3)
    assert result["failed"] == 1 and len(result["decisions"]) == 2 and len(client.calls) == 4


def test_quota_error_stops_the_run_and_keeps_finished_reactions(population):
    service, scenario_id = population

    class Quota(FakeReactor):
        def generate(self, *args, **kwargs):
            if len(self.calls) == 5:
                raise CloudQuotaError()
            return super().generate(*args, **kwargs)

    with pytest.raises(CloudQuotaError):
        service.run_reactions(scenario_id, client=Quota(), slots=("first",))
    resumed = FakeReactor()
    result = service.run_reactions(scenario_id, client=resumed, slots=("first",))
    assert result["from_cache"] == 5 and len(resumed.calls) == 55


def test_reactions_require_persona_cards(population):
    service, _ = population
    scenario = service.create_scenario(
        {
            "name": "x",
            "brand": "B",
            "vertical": "pet_ecommerce",
            "product_description": "Cibo",
            "population_size": 30,
            "creatives": [{"id": "A", "headline": "x", "primary_text": "y"}],
            "targeting": {"audience_intent": "ha un cane"},
        }
    )
    with pytest.raises(ValueError, match="schede"):
        service.run_reactions(scenario["id"], client=FakeReactor())


def test_facts_in_the_prompt_match_the_skeleton(population):
    _, _, brief, pop = loaded(population)
    profile = pop["profiles"][4]
    item = next(
        i
        for i in reaction_plan(brief, pop["profiles"], pop["cards"], "d")
        if i["agent_id"] == profile["agent_id"]
    )
    assert all(f in build_prompt(item["input"])[1] for f in describe_profile(profile))
