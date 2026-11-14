from audience_simulator.agents import PROMPT_VERSION, evaluation_plan, evaluation_schema
from audience_simulator.audience import generate_population
from audience_simulator.reporting import input_gaps
from audience_simulator.schemas import CampaignBrief, Creative


def brief(**creative):
    base = {"id": "A", "headline": "Crema", "primary_text": "Idratazione 24 ore"}
    return CampaignBrief(
        name="T",
        brand="Marca",
        product_description="Crema viso",
        vertical="beauty_skincare",
        date_from="2026-11-16",
        date_to="2026-11-16",
        creatives=[Creative(**{**base, **creative})],
    )


def plan(b):
    return evaluation_plan(b, generate_population(b)[:1], "digest")


def test_complete_stimulus_reaches_the_agent_payload():
    b = brief(
        offer="-20% fino a domenica",
        price_text="19,90 € invece di 24,90 €",
        landing_page_summary="Scheda prodotto con recensioni e spedizione gratuita sopra 29 €",
        visual_description="Flacone su fondo bianco",
    )
    payload = plan(b)[0]["input"]
    assert payload["creative"]["offer"] == "-20% fino a domenica"
    assert payload["creative"]["price_text"].startswith("19,90")
    assert "recensioni" in payload["creative"]["landing_page_summary"]
    assert payload["creative"]["cta"] == "Scopri di più"
    assert payload["campaign"]["device"] == "mobile"


def test_new_stimulus_fields_are_allowed_evidence_references():
    payload = plan(brief(offer="-20%"))[0]["input"]
    allowed = evaluation_schema(payload)["properties"]["evidence"]["items"]["enum"]
    assert {"creative.offer", "creative.price_text", "creative.landing_page_summary"} <= set(allowed)


def test_stimulus_changes_change_the_cache_key_and_prompt_version_is_bumped():
    base, changed = plan(brief())[0]["key"], plan(brief(offer="-20%"))[0]["key"]
    assert base != changed
    assert PROMPT_VERSION != "consumer-policy-v6"


def test_missing_stimulus_parts_are_reported_as_gaps_not_discoveries():
    gaps = {g["field"] for g in input_gaps(brief())}
    assert {"price_eur", "creative.A.visual_description", "creative.A.landing_page_summary"} <= gaps
    complete = brief(
        visual_description="Flacone",
        landing_page_summary="Scheda prodotto",
        offer="-20%",
        price_text="19,90 €",
    ).model_copy(update={"price_eur": 19.9})
    assert input_gaps(complete) == []


def test_traffic_objective_does_not_require_a_landing_page_summary():
    b = brief(visual_description="Flacone").model_copy(update={"objective": "traffico", "price_eur": 10})
    assert "creative.A.landing_page_summary" not in {g["field"] for g in input_gaps(b)}
