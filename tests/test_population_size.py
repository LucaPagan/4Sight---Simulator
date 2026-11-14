from pathlib import Path

import httpx
import pytest
from audience_simulator.agents import OllamaClient
from audience_simulator.audience import band_sizes, generate_population
from audience_simulator.schemas import AGES, CampaignBrief, Creative
from pydantic import ValidationError
from test_simulation_api import brief as api_brief
from test_simulation_api import fake_ollama, service  # noqa: F401


def make_brief(size=None, **extra):
    data = dict(
        name="Test",
        brand="Brand",
        product_description="Kit routine",
        vertical="beauty_skincare",
        creatives=[Creative(id="a", headline="Titolo", primary_text="Testo")],
        **extra,
    )
    if size is not None:
        data["population_size"] = size
    return CampaignBrief(**data)


@pytest.mark.parametrize("size", [30, 60, 120, 250, 600, 1000])
def test_population_has_requested_size_and_unit_weight(size):
    brief = make_brief(size)
    profiles = generate_population(brief)
    assert len(profiles) == size
    assert len({p["agent_id"] for p in profiles}) == size
    assert sum(p["population_weight"] for p in profiles) == pytest.approx(1)
    counts = [sum(p["age_band"] == band for p in profiles) for band in AGES]
    assert max(counts) - min(counts) <= 1
    assert counts == band_sizes(size)


def test_default_panel_is_unchanged():
    profiles = generate_population(make_brief())
    assert len(profiles) == 120
    assert {p["age_band"] for p in profiles} == set(AGES)
    assert profiles == generate_population(make_brief(120))


def test_weights_follow_age_shares_for_uneven_bands():
    shares = [0.4, 0.2, 0.1, 0.1, 0.1, 0.1]
    profiles = generate_population(make_brief(100, age_shares=shares))
    for band, share in zip(AGES, shares):
        assert sum(p["population_weight"] for p in profiles if p["age_band"] == band) == pytest.approx(share)


@pytest.mark.parametrize("size", [0, 29, 1001, 120.5])
def test_population_size_is_bounded(size):
    with pytest.raises(ValidationError):
        make_brief(size)


@pytest.mark.skipif(not Path("data/storico_giornaliero.csv").exists(), reason="Kit CSV non distribuito")
@pytest.mark.parametrize("size", [60, 1000])
def test_run_scales_with_panel_size(service, size):  # noqa: F811
    scenario = service.create_scenario({**api_brief(), "population_size": size})
    assert service.repo.get("populations", scenario["population_id"])["size"] == size
    check = service.preflight(scenario["id"], client=OllamaClient(transport=httpx.MockTransport(fake_ollama)))
    assert check["population_size"] == size
    assert check["required_policies"] == size * 2
    run = service.repo.create_run(scenario["id"], f"size-{size}")
    service.execute_run(run["id"], client=OllamaClient(transport=httpx.MockTransport(fake_ollama)))
    status = service.repo.get("simulation_runs", run["id"])
    assert status["completion_status"] == "complete", status
    result = service.result(run["id"])
    assert len(result["profiles"]) == size
    assert result["coverage"]["profiles"] == size
    assert f"{size} agenti" in result["report"]["limitations"][2]
    assert abs(sum(p["population_weight"] for p in result["profiles"]) - 1) < 1e-9
