import json

import pytest
from audience_simulator.domain import (
    VERIFIED_DOMAINS,
    Domain,
    DomainEntry,
    VerifiedConfig,
    assess_domain,
)
from audience_simulator.schemas import CampaignBrief, Creative

CONFIG = VerifiedConfig(prompt_version="consumer-policy-v6", model="gemini-3.5-flash-lite", benchmark_id="b1")


def brief(**changes):
    values = {
        "name": "Test",
        "brand": "Marca",
        "product_description": "Crema viso idratante",
        "vertical": "beauty_skincare",
        "creatives": [Creative(id="a", headline="x", primary_text="y")],
    }
    return CampaignBrief(**{**values, **changes})


def entry():
    return DomainEntry(
        domain=Domain.from_brief(brief()),
        verified_for=[CONFIG],
    )


def test_registry_is_empty_until_a_benchmark_has_passed():
    assert VERIFIED_DOMAINS == ()


def test_domain_is_derived_from_the_brief_including_language():
    domain = Domain.from_brief(brief(country="ES", objective="traffico", placement="facebook_feed"))
    assert domain.model_dump() == {
        "vertical": "beauty_skincare",
        "country": "ES",
        "objective": "traffico",
        "placement": "facebook_feed",
        "language": "es",
    }


def test_empty_registry_means_out_of_domain():
    result = assess_domain(Domain.from_brief(brief()), CONFIG.prompt_version, CONFIG.model)
    assert result.status == "out_of_domain"
    assert not result.verified
    assert "nessun benchmark" in result.reason.lower()


@pytest.mark.parametrize(
    "changes",
    [
        {"vertical": "pet_ecommerce"},
        {"country": "FR"},
        {"objective": "traffico"},
        {"placement": "instagram_stories"},
    ],
)
def test_any_difference_in_the_domain_is_out_of_domain(changes):
    result = assess_domain(
        Domain.from_brief(brief(**changes)), CONFIG.prompt_version, CONFIG.model, registry=(entry(),)
    )
    assert result.status == "out_of_domain"
    assert result.reason


def test_known_domain_with_a_new_prompt_or_model_is_not_verified():
    for prompt_version, model in (
        ("consumer-policy-v7", CONFIG.model),
        (CONFIG.prompt_version, "altro-modello"),
    ):
        result = assess_domain(Domain.from_brief(brief()), prompt_version, model, registry=(entry(),))
        assert result.status == "unverified_configuration"
        assert not result.verified


def test_exact_domain_and_configuration_is_verified():
    result = assess_domain(
        Domain.from_brief(brief()), CONFIG.prompt_version, CONFIG.model, registry=(entry(),)
    )
    assert result.status == "verified"
    assert result.verified
    assert result.benchmark_id == "b1"


def test_missing_configuration_never_counts_as_verified():
    result = assess_domain(Domain.from_brief(brief()), None, None, registry=(entry(),))
    assert result.status == "unverified_configuration"


def test_entry_without_any_verified_configuration_is_rejected():
    with pytest.raises(ValueError):
        DomainEntry(domain=Domain.from_brief(brief()), verified_for=[])


def test_registry_entries_need_a_committed_benchmark_manifest(tmp_path):
    from audience_simulator.domain import registry_problems

    assert registry_problems((), tmp_path) == []
    assert registry_problems((entry(),), tmp_path) == ["manifest mancante per il benchmark b1"]
    (tmp_path / "b1.json").write_text(
        json.dumps({"benchmark_id": "b1", "prompt_version": "consumer-policy-v6", "model": "altro"})
    )
    assert "non coincide" in registry_problems((entry(),), tmp_path)[0]
    (tmp_path / "b1.json").write_text(
        json.dumps({"benchmark_id": "b1", "prompt_version": CONFIG.prompt_version, "model": CONFIG.model})
    )
    assert registry_problems((entry(),), tmp_path) == []


def test_the_shipped_registry_has_no_unbacked_entries():
    from audience_simulator.domain import registry_problems

    assert registry_problems() == []
