from audience_simulator import agents, cloud, cloudflare, prompts
from audience_simulator.agents import evaluation_plan, evaluation_schema
from audience_simulator.audience import generate_population
from audience_simulator.schemas import CampaignBrief, Creative


def brief():
    return CampaignBrief(
        name="t",
        brand="B",
        product_description="Cibo per cani",
        vertical="pet_ecommerce",
        creatives=[Creative(id="a", headline="Titolo", primary_text="Testo")],
        population_size=30,
    )


def test_one_prompt_version_for_every_provider():
    assert agents.PROMPT_VERSION == prompts.PROMPT_VERSION
    assert agents.SYSTEM_PROMPT is prompts.SYSTEM_PROMPT
    assert cloud.CLOUD_PROMPT_VERSION.startswith(prompts.PROMPT_VERSION)
    assert cloudflare.CloudflareClient.prompt_version.startswith(prompts.PROMPT_VERSION)


def test_model_view_hides_bookkeeping_but_cache_payload_keeps_it():
    b = brief()
    item = evaluation_plan(b, generate_population(b)[:1], "digest", prompts.PROMPT_VERSION)[0]
    payload = item["input"]
    view = prompts.model_view(payload)
    assert {"model_digest", "prompt_version"} <= set(payload)
    assert not {"model_digest", "prompt_version"} & set(view)
    assert not set(prompts.PROFILE_NOISE) & set(view["profile"])
    assert "category_affinity" in view["profile"]
    assert view["creative"] == payload["creative"] and view["campaign"] == payload["campaign"]
    assert "profile.seed" not in evaluation_schema(view)["properties"]["evidence"]["items"]["enum"]
    assert "profile.seed" in evaluation_schema(payload)["properties"]["evidence"]["items"]["enum"]
