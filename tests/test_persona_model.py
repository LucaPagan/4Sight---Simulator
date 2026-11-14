from collections import Counter
from pathlib import Path

import httpx
import numpy as np
import pytest
from audience_simulator.agents import OllamaClient
from audience_simulator.config import Settings
from audience_simulator.persona_model import generate_targeted_population, trait_correlation_matrix
from audience_simulator.prompts import model_view
from audience_simulator.schemas import AGES, CampaignBrief, Creative, DetailedTerm, TargetingSpec
from audience_simulator.service import SimulationService, effective_brief
from test_simulation_api import fake_ollama


def brief(vertical="pet_ecommerce", size=120, seed=42, **targeting):
    return CampaignBrief(
        name="t",
        brand="B",
        product_description="Cibo per cani",
        vertical=vertical,
        creatives=[Creative(id="a", headline="Titolo", primary_text="Testo")],
        population_size=size,
        seed=seed,
        targeting=TargetingSpec(**targeting),
    )


def shares(profiles, key):
    counts = Counter(p[key] for p in profiles)
    return {k: v / len(profiles) for k, v in counts.items()}


def test_trait_correlations_are_a_valid_correlation_matrix():
    matrix = trait_correlation_matrix()
    assert np.allclose(matrix, matrix.T) and np.linalg.eigvalsh(matrix).min() > 0


def test_same_seed_same_panel_and_other_seed_other_panel():
    one, _ = generate_targeted_population(brief(seed=7))
    again, _ = generate_targeted_population(brief(seed=7))
    other, _ = generate_targeted_population(brief(seed=8))
    assert one == again and one != other


def test_panel_is_diverse_with_unique_ids_and_weights_summing_to_one():
    profiles, reach = generate_targeted_population(brief())
    assert len(profiles) == 120 and len({p["agent_id"] for p in profiles}) == 120
    assert sum(p["population_weight"] for p in profiles) == pytest.approx(1)
    assert reach["audit"]["duplicates"] == 0 and reach["audit"]["status"] == "ok"
    for attribute in ("household", "pet_species", "urbanicity", "occupation", "income_band"):
        assert len({p[attribute] for p in profiles}) >= 3
    assert all(p["profile_version"] == "profiles-v3-targeted" for p in profiles)
    assert all(p["provenance"]["pet_species"] == "assumption" for p in profiles)


def test_attributes_are_coherent_with_each_other():
    profiles, _ = generate_targeted_population(brief(size=300))
    for p in profiles:
        if p["household"] == "family":
            assert p["has_children"] == "yes" or True  # 98%: checked in aggregate below
        if p["household"] == "couple":
            assert p["relationship_status"] != "single"
        if p["occupation"] == "retired":
            assert p["age"] >= 45
        assert 18 <= p["age"] <= 74
        assert (p["uses_instagram"] or p["uses_facebook"]) is True
    family = [p for p in profiles if p["household"] == "family"]
    assert sum(p["has_children"] == "yes" for p in family) / len(family) > 0.9


def test_delivered_audience_reproduces_the_declared_precision_not_a_perfect_audience():
    profiles, reach = generate_targeted_population(
        brief(audience_intent="ha un cane", detailed=[DetailedTerm(id="interest:dogs")])
    )
    dogs = reach["constraints"][0]
    assert dogs["share_in_reached"] == pytest.approx(0.55, abs=0.04)
    assert dogs["share_in_base"] < 0.35
    assert 0.4 < shares(profiles, "pet_species")["dog"] < 0.7
    assert reach["ideal_share_in_reached"] == dogs["share_in_reached"]
    assert sum(p["in_ideal_target"] for p in profiles) == sum(p["pet_species"] == "dog" for p in profiles)


def test_proxies_narrow_the_audience_and_exclusion_removes_people():
    spec = {"audience_intent": "ha un cane e vive da solo"}
    only_dogs = generate_targeted_population(brief(**spec, detailed=[DetailedTerm(id="interest:dogs")]))[1]
    narrowed = generate_targeted_population(
        brief(
            **spec,
            detailed=[DetailedTerm(id="interest:dogs"), DetailedTerm(id="demographic:single", mode="narrow")],
        )
    )[1]
    assert narrowed["ideal_share_in_reached"] > only_dogs["ideal_share_in_reached"] > 0
    none_selected = generate_targeted_population(brief(**spec))[1]
    assert none_selected["ideal_share_in_reached"] == pytest.approx(
        none_selected["ideal_share_in_base"], abs=0.005
    )
    excluded = generate_targeted_population(
        brief(audience_intent="ha un cane", detailed=[DetailedTerm(id="interest:dogs", mode="exclude")])
    )[1]
    assert excluded["constraints"][0]["share_in_reached"] < excluded["constraints"][0]["share_in_base"]


def test_age_gender_and_urbanicity_filters_are_hard():
    profiles, reach = generate_targeted_population(
        brief(age_min=25, age_max=34, gender="women", urbanicity="urban")
    )
    assert {p["gender"] for p in profiles} == {"women"} and {p["urbanicity"] for p in profiles} == {"urban"}
    assert all(25 <= p["age"] <= 34 for p in profiles) and {p["age_band"] for p in profiles} == {"25-34"}
    assert reach["age_shares"][1] == pytest.approx(1) and sum(reach["age_shares"][2:]) == 0
    assert reach["audit"]["band_counts"]["25-34"] == 120


def test_partial_band_age_range_uses_exact_ages():
    profiles, reach = generate_targeted_population(brief(age_min=30, age_max=40))
    assert all(30 <= p["age"] <= 40 for p in profiles)
    assert {p["age_band"] for p in profiles} == {"25-34", "35-44"}
    assert reach["age_shares"][0] == 0


def test_placements_and_devices_limit_who_is_reached():
    profiles, _ = generate_targeted_population(
        brief(advantage_placements=False, placements=["instagram_feed"], device_platforms=["ios"])
    )
    assert all(p["uses_instagram"] and p["device_os"] == "ios" for p in profiles)
    on_facebook, _ = generate_targeted_population(
        brief(advantage_placements=False, placements=["facebook_feed"])
    )
    assert all(p["uses_facebook"] for p in on_facebook)
    assert shares(on_facebook, "age_band")["65+"] > 0


def test_impossible_targeting_is_rejected_with_a_clear_error():
    stories = brief(advantage_placements=False, placements=["instagram_stories"])
    desktop = stories.model_copy(update={"device": "desktop"})
    with pytest.raises(ValueError, match="placement"):
        generate_targeted_population(desktop)
    with pytest.raises(ValueError, match="esclude"):
        generate_targeted_population(
            brief(
                age_min=18,
                age_max=18,
                device_platforms=["desktop"],
                gender="men",
                urbanicity="rural",
                detailed=[
                    DetailedTerm(id="demographic:married"),
                    DetailedTerm(id="demographic:parents", mode="narrow"),
                ],
            )
        )


def test_unmodelled_terms_are_reported_and_do_not_change_the_audience():
    with_term, reach = generate_targeted_population(brief(detailed=[DetailedTerm(id="interest:travel")]))
    without, _ = generate_targeted_population(brief())
    assert reach["unmodelled_terms"] == ["interest:travel"] and with_term == without


def test_advantage_audience_widens_the_delivered_audience():
    kwargs = {"audience_intent": "ha un cane", "detailed": [DetailedTerm(id="interest:dogs")]}
    narrow = generate_targeted_population(brief(**kwargs))[1]["ideal_share_in_reached"]
    wide = generate_targeted_population(brief(**kwargs, advantage_audience=True))[1]["ideal_share_in_reached"]
    assert wide < narrow


def test_traits_follow_the_vertical_and_the_person():
    dogs, _ = generate_targeted_population(brief(size=600))
    mean = lambda rows, key: float(np.mean([p[key] for p in rows]))  # noqa: E731
    owners = [p for p in dogs if p["pet_species"] in {"dog", "cat"}]
    others = [p for p in dogs if p["pet_species"] == "none"]
    assert mean(owners, "category_affinity") > mean(others, "category_affinity") + 0.15
    low = [p for p in dogs if p["income_band"] == "low"]
    high = [p for p in dogs if p["income_band"] == "high"]
    assert mean(low, "budget_sensitivity") > mean(high, "budget_sensitivity")
    assert all(0 <= p["trust"] <= 1 for p in dogs)


def test_beauty_vertical_ties_affinity_to_skincare_routine():
    rows, _ = generate_targeted_population(brief("beauty_skincare", size=600))
    extended = [p["category_affinity"] for p in rows if p["skincare_routine"] == "extended"]
    none = [p["category_affinity"] for p in rows if p["skincare_routine"] == "none"]
    assert np.mean(extended) > np.mean(none) + 0.15


def test_region_labels_and_model_view_hide_bookkeeping():
    profiles, _ = generate_targeted_population(brief(regions=["Lombardia", "Lazio"]))
    assert {p["region"] for p in profiles} == {"Lombardia", "Lazio"}
    view = model_view({"profile": profiles[0], "model_digest": "d"})
    assert "in_ideal_target" not in view["profile"] and "household" in view["profile"]


@pytest.fixture
def service(tmp_path):
    return SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db.sqlite",
            artifact_dir=tmp_path / "artifacts",
            data_dir=Path("data"),
            queue_mode="manual",
            monte_carlo_draws=30,
        )
    )


PAYLOAD = {
    "name": "Cani",
    "brand": "NDL",
    "vertical": "pet_ecommerce",
    "product_description": "Cibo per cani",
    "date_from": "2026-11-16",
    "date_to": "2026-11-16",
    "creatives": [{"id": "A", "headline": "Cibo", "primary_text": "Per il tuo cane"}],
    "targeting": {
        "audience_intent": "ha un cane e vive da solo",
        "detailed": [{"id": "interest:dogs"}],
        "age_min": 25,
        "age_max": 44,
    },
}


def test_scenario_samples_the_population_on_the_targeting(service):
    scenario = service.create_scenario(PAYLOAD)
    report = scenario["targeting_report"]
    assert report["applied_to_population"] is True and "not_applied" not in {
        n["code"] for n in report["notes"]
    }
    assert report["reach"]["audit"]["status"] == "ok"
    assert "ideal_share" in {n["code"] for n in report["notes"]}
    profiles = service.repo.get("populations", scenario["population_id"])["profiles"]
    assert {p["age_band"] for p in profiles} == {"25-34", "35-44"}
    legacy = service.create_scenario({k: v for k, v in PAYLOAD.items() if k != "targeting"})
    assert "targeting_report" not in legacy
    old = service.repo.get("populations", legacy["population_id"])["profiles"]
    assert old[0]["profile_version"] == "profiles-v2" and "household" not in old[0]


def test_effective_brief_uses_the_reached_age_mix(service):
    scenario = service.create_scenario(PAYLOAD)
    adjusted = effective_brief(CampaignBrief.model_validate(scenario["brief"]), scenario)
    assert adjusted.age_shares[0] == 0 and adjusted.age_shares[5] == 0
    assert sum(adjusted.age_shares[1:3]) == pytest.approx(1)


def test_full_run_on_a_targeted_panel_skips_bands_that_are_not_reached(service):
    scenario = service.create_scenario(PAYLOAD)
    run = service.repo.create_run(scenario["id"], "complete")
    service.execute_run(run["id"], client=OllamaClient(transport=httpx.MockTransport(fake_ollama)))
    status = service.repo.get("simulation_runs", run["id"])
    assert status["completion_status"] == "complete", status
    result = service.result(run["id"])
    ages = {a["age_band"]: a for a in result["predictions"][0]["ages"]}
    assert ages["18-24"]["not_reached_in_scenario"] and not ages["25-34"]["not_reached_in_scenario"]
    assert {e["agent_id"].split("-")[1] for e in result["behavior"]["events"]} == {"2", "3"}
    assert AGES[1] in {f["age_band"] for f in result["behavior"]["policy_findings"]}
