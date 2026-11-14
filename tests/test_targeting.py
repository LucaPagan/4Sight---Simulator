import pytest
from audience_simulator.schemas import (
    AudienceConstraint,
    CampaignBrief,
    Creative,
    DetailedTerm,
    TargetingAnalyzeRequest,
    TargetingSpec,
)
from audience_simulator.targeting import analyze_targeting, read_intent
from pydantic import ValidationError


def analyze(**targeting):
    return analyze_targeting(TargetingAnalyzeRequest(targeting=TargetingSpec(**targeting)))


def codes(report):
    return {n.code for n in report.notes}


def test_intent_dog_owner_living_alone_becomes_constraints():
    constraints, age, gender, leftover = read_intent("Chi ha un cane e vive da solo")
    assert {(c.attribute, tuple(c.values)) for c in constraints} == {
        ("pet_species", ("dog",)),
        ("household", ("alone",)),
    }
    assert (age, gender, leftover) == (None, None, "")


def test_intent_reports_what_it_did_not_understand_instead_of_guessing():
    report = analyze(audience_intent="Chi ha un cane e ama il giardinaggio biologico")
    assert report.unrecognized_intent == "ama giardinaggio biologico"
    assert "intent_not_understood" in codes(report)


def test_age_and_gender_in_text_are_flagged_not_silently_applied():
    constraints, age, gender, _ = read_intent("donne tra 25-34 anni")
    assert (age, gender, constraints) == ((25, 34), "women", [])
    assert "age_from_intent" in codes(analyze(audience_intent="25-34 anni"))


def test_lives_alone_is_not_targetable_on_meta_and_dog_proxy_leaks():
    report = analyze(
        audience_intent="ha un cane e vive da solo",
        detailed=[DetailedTerm(id="interest:dogs")],
    )
    by_attr = {p.attribute: p for p in report.proxies}
    assert by_attr["household"].meta_direct is False and by_attr["household"].selected_terms == []
    assert by_attr["household"].suggested_terms == ["demographic:single"]
    assert by_attr["pet_species"].selected_terms == ["interest:dogs"]
    assert by_attr["pet_species"].expected_precision == pytest.approx(0.55)
    assert by_attr["pet_species"].precision_evidence == "assumption"
    assert {"not_targetable", "no_proxy_selected", "low_precision"} <= codes(report)
    assert report.applied_to_population is False and "not_applied" in codes(report)


def test_precision_uses_best_selected_term():
    report = analyze(
        constraints=[AudienceConstraint(attribute="pet_species", values=["dog"])],
        detailed=[DetailedTerm(id="interest:pets"), DetailedTerm(id="interest:dogs", mode="narrow")],
    )
    assert report.proxies[0].expected_precision == pytest.approx(0.55)


def test_explicit_and_text_constraints_are_merged_without_duplicates():
    report = analyze(
        audience_intent="ha un cane",
        constraints=[AudienceConstraint(attribute="pet_species", values=["dog"])],
    )
    assert len(report.constraints) == 1


def test_placement_device_and_manual_placement_notes():
    request = TargetingAnalyzeRequest(
        device="desktop",
        targeting=TargetingSpec(advantage_placements=False, placements=["instagram_stories"]),
    )
    assert "placement_device" in codes(analyze_targeting(request))
    assert "no_placement" in codes(analyze(advantage_placements=False))
    assert "advantage_audience" in codes(analyze(advantage_audience=True))


@pytest.mark.parametrize(
    "bad",
    [
        {"age_min": 40, "age_max": 30},
        {"placements": ["instagram_feed", "instagram_feed"]},
        {"bid_strategy": "cost_cap"},
        {"constraints": [{"attribute": "reddito_segreto", "values": ["x"]}]},
        {"constraints": [{"attribute": "pet_species", "values": ["drago"]}]},
        {"detailed": [{"id": "interest:inesistente"}]},
        {"hours": [24]},
        {"unknown_field": 1},
    ],
)
def test_invalid_targeting_is_rejected(bad):
    with pytest.raises(ValidationError):
        TargetingSpec(**bad)


def test_brief_targeting_is_optional_and_backward_compatible():
    base = {
        "name": "t",
        "brand": "b",
        "product_description": "cibo per cani",
        "vertical": "pet_ecommerce",
        "creatives": [Creative(id="a", headline="x", primary_text="y")],
    }
    assert CampaignBrief(**base).targeting is None
    brief = CampaignBrief(**base, targeting=TargetingSpec(audience_intent="ha un cane"))
    assert (
        CampaignBrief.model_validate(brief.model_dump(mode="json")).targeting.audience_intent == "ha un cane"
    )


def test_endpoint_and_scenario_store_the_targeting_report(tmp_path):
    from pathlib import Path

    from audience_simulator.api import create_app
    from audience_simulator.config import Settings
    from audience_simulator.service import SimulationService
    from fastapi.testclient import TestClient

    service = SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db.sqlite",
            artifact_dir=tmp_path / "artifacts",
            data_dir=Path("data"),
            queue_mode="manual",
            monte_carlo_draws=30,
        )
    )
    client = TestClient(create_app(service=service))
    spec = {"audience_intent": "ha un cane e vive da solo", "detailed": [{"id": "interest:dogs"}]}
    analyzed = client.post("/api/v1/targeting/analyze", json={"targeting": spec}).json()
    assert {c["attribute"] for c in analyzed["constraints"]} == {"pet_species", "household"}
    assert (
        client.post(
            "/api/v1/targeting/analyze", json={"targeting": {"age_min": 50, "age_max": 20}}
        ).status_code
        == 422
    )
    brief = {
        "name": "Cani",
        "brand": "B",
        "vertical": "pet_ecommerce",
        "product_description": "Cibo per cani",
        "creatives": [{"id": "a", "headline": "x", "primary_text": "y"}],
        "targeting": spec,
    }
    scenario = client.post("/api/v1/scenarios", json=brief).json()
    assert scenario["targeting_report"]["applied_to_population"] is True
    assert scenario["brief"]["targeting"]["audience_intent"] == "ha un cane e vive da solo"
    plain = client.post("/api/v1/scenarios", json={k: v for k, v in brief.items() if k != "targeting"}).json()
    assert "targeting_report" not in plain


def test_catalog_endpoint_lists_what_the_form_can_offer(tmp_path):
    from pathlib import Path

    from audience_simulator.api import create_app
    from audience_simulator.config import Settings
    from audience_simulator.service import SimulationService
    from fastapi.testclient import TestClient

    service = SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db.sqlite",
            artifact_dir=tmp_path / "artifacts",
            data_dir=Path("data"),
            queue_mode="manual",
        )
    )
    catalog = TestClient(create_app(service=service)).get("/api/v1/targeting/catalog").json()
    assert len(catalog["placements"]) == 12 and {"id", "label", "surface"} <= set(catalog["placements"][0])
    terms = {t["id"]: t for t in catalog["terms"]}
    assert terms["interest:dogs"]["modelled"] is True and terms["interest:travel"]["modelled"] is False
    assert {a["id"] for a in catalog["attributes"]} >= {"household", "pet_species"}
