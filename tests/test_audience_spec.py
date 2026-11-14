import httpx
import numpy as np
import pytest
from audience_simulator import audience_spec
from audience_simulator.audience import generate_population
from audience_simulator.audience_spec import (
    AGE_TO_EUROSTAT,
    build_spec,
    fetch_marginals,
    generate_profiles_v2,
    parse_jsonstat,
)
from audience_simulator.schemas import AGES, CampaignBrief, Creative


def marginals():
    return {
        "version": "eurostat-test",
        "retrieved": "2026-11-14",
        "sources": {"population": {"dataset": "demo_pjan"}},
        "countries": {
            "IT": {
                "population_18plus_by_band": dict(zip(AGES, [4, 6, 7, 9, 7, 17], strict=True)),
                "social_network_use_pct": dict(zip(AGES, [90, 85, 75, 60, 45, 20], strict=True)),
                "online_purchase_12m_pct": dict(zip(AGES, [70, 75, 70, 60, 45, 20], strict=True)),
                "periods": {"social": "2024", "shopping": "2024", "population": "2025"},
            }
        },
    }


def brief(**changes):
    values = {
        "name": "T",
        "brand": "Marca",
        "product_description": "Crema viso",
        "vertical": "beauty_skincare",
        "creatives": [Creative(id="A", headline="x", primary_text="y")],
    }
    return CampaignBrief(**{**values, **changes})


def test_audience_age_mix_weights_population_by_social_network_use():
    spec = build_spec(marginals(), "IT")
    expected = np.array([4 * 0.9, 6 * 0.85, 7 * 0.75, 9 * 0.6, 7 * 0.45, 17 * 0.2])
    assert spec["age_shares"] == pytest.approx(list(expected / expected.sum()))
    assert sum(spec["age_shares"]) == pytest.approx(1)
    assert spec["online_purchase_rate"]["25-34"] == 0.75


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["countries"].pop("IT"),
        lambda m: m["countries"]["IT"]["social_network_use_pct"].pop("65+"),
        lambda m: m["countries"]["IT"]["online_purchase_12m_pct"].update({"18-24": 140}),
    ],
)
def test_invalid_marginals_fail_loudly(mutate):
    data = marginals()
    mutate(data)
    with pytest.raises((ValueError, KeyError)):
        build_spec(data, "IT")


def test_v2_profiles_keep_the_panel_shape_and_label_what_is_observed():
    spec = build_spec(marginals(), "IT")
    profiles = generate_profiles_v2(42, "beauty_skincare", "Marca", spec, size=120)
    assert len(profiles) == 120
    assert {p["age_band"] for p in profiles} == set(AGES)
    assert sum(p["population_weight"] for p in profiles) == pytest.approx(1)
    first = profiles[0]
    assert first["profile_version"] == "profiles-v2"
    assert first["provenance"]["age_band"] == "observed_distribution"
    assert first["provenance"]["online_shopper"] == "observed_distribution"
    assert first["provenance"]["category_affinity"] == "assumption"
    assert profiles == generate_profiles_v2(42, "beauty_skincare", "Marca", spec, size=120)


def test_online_shopper_attribute_follows_the_observed_rate_by_band():
    spec = build_spec(marginals(), "IT")
    profiles = generate_profiles_v2(7, "beauty_skincare", "Marca", spec, size=3000)
    for band, rate in spec["online_purchase_rate"].items():
        group = [p["online_shopper"] for p in profiles if p["age_band"] == band]
        assert np.mean(group) == pytest.approx(rate, abs=0.08)


def test_traits_remain_in_the_unit_interval_and_shopper_status_has_a_declared_effect():
    spec = build_spec(marginals(), "IT")
    profiles = generate_profiles_v2(3, "pet_ecommerce", "Marca", spec, size=1200)
    for p in profiles:
        assert all(
            0 <= p[t] <= 1 for t in ("trust", "purchase_need", "category_affinity", "budget_sensitivity")
        )
    shoppers = np.mean([p["trust"] for p in profiles if p["online_shopper"]])
    others = np.mean([p["trust"] for p in profiles if not p["online_shopper"]])
    assert shoppers > others


def test_without_marginals_the_legacy_panel_is_unchanged(monkeypatch):
    monkeypatch.setattr(audience_spec, "load_marginals", lambda: None)
    profiles = generate_population(brief())
    assert profiles[0]["profile_version"] == "profiles-v1"


def test_with_marginals_default_age_mix_comes_from_the_spec_but_user_shares_win(monkeypatch):
    monkeypatch.setattr(audience_spec, "load_marginals", marginals)
    profiles = generate_population(brief())
    assert profiles[0]["profile_version"] == "profiles-v2"
    by_band = {p["age_band"]: p["population_weight"] * 20 for p in profiles}
    spec = build_spec(marginals(), "IT")
    assert [by_band[b] for b in AGES] == pytest.approx(spec["age_shares"])
    custom = generate_population(brief(age_shares=[1 / 6] * 6))
    assert {round(p["population_weight"] * 20, 6) for p in custom} == {round(1 / 6, 6)}


def test_unsupported_country_falls_back_to_legacy(monkeypatch):
    monkeypatch.setattr(audience_spec, "load_marginals", marginals)
    assert generate_population(brief(country="FR"))[0]["profile_version"] == "profiles-v1"


def jsonstat(values, dims):
    return {
        "id": [d for d, _ in dims],
        "size": [len(c) for _, c in dims],
        "dimension": {d: {"category": {"index": {c: i for i, c in enumerate(cats)}}} for d, cats in dims},
        "value": values,
        "updated": "2026-04-17T11:00:00+0200",
    }


def test_parse_jsonstat_decodes_flat_values_into_labelled_cells():
    data = jsonstat(
        {"0": 10, "1": 11, "3": 31},
        [("geo", ["IT"]), ("ind_type", ["Y25_34", "Y35_44"]), ("time", ["2023", "2024"])],
    )
    cells = parse_jsonstat(data)
    assert cells[("IT", "Y25_34", "2023")] == 10
    assert cells[("IT", "Y25_34", "2024")] == 11
    assert cells[("IT", "Y35_44", "2024")] == 31
    assert ("IT", "Y35_44", "2023") not in cells


def test_fetch_marginals_uses_the_latest_period_with_every_band_and_records_it():
    ages = [AGE_TO_EUROSTAT[b] for b in AGES]

    def handler(request):
        dataset = request.url.path.rsplit("/", 1)[-1]
        if dataset == "demo_pjan":
            codes = [f"Y{a}" for a in range(18, 100)] + ["Y_OPEN"]
            return httpx.Response(
                200,
                json=jsonstat(
                    {str(i): 1000 for i in range(len(codes))},
                    [("geo", ["IT"]), ("age", codes), ("time", ["2025"])],
                ),
            )
        values = {}
        for i in range(len(ages)):
            values[str(i * 2)] = 50 + i  # 2023 complete
            if i < 5:  # 2024 missing the oldest band
                values[str(i * 2 + 1)] = 60 + i
        return httpx.Response(
            200, json=jsonstat(values, [("geo", ["IT"]), ("ind_type", ages), ("time", ["2023", "2024"])])
        )

    result = fetch_marginals(["IT"], transport=httpx.MockTransport(handler), today="2026-11-14")
    country = result["countries"]["IT"]
    assert country["periods"]["social"] == "2023"
    assert country["social_network_use_pct"]["18-24"] == 50
    assert sum(country["population_18plus_by_band"].values()) == 1000 * 83
    assert result["retrieved"] == "2026-11-14"
    build_spec(result, "IT")
