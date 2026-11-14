import hashlib

import httpx
import pandas as pd
import pytest
from audience_simulator.corpus import (
    UPWORTHY_SHA256,
    build_gwwc_campaigns,
    build_upworthy_campaigns,
    fetch_source,
    split_campaigns,
)


def upworthy_rows(tests=6, arms=3, **overrides):
    rows = []
    for t in range(tests):
        for a in range(arms):
            rows.append(
                {
                    "created_at": f"2014-03-0{1 + t % 8} 10:00:00",
                    "clickability_test_id": f"t{t}",
                    "headline": f"Titolo {t}-{a}",
                    "impressions": 1000 + 100 * a,
                    "clicks": 10 + 5 * a,
                    "problem": 0,
                    "excerpt": "non mostrato",
                    "lede": "non mostrato",
                    "share_text": "non mostrato",
                    "winner": a == 0,
                    "significance": 0.9,
                }
            )
    return pd.DataFrame(rows).assign(**overrides)


def test_stimuli_never_contain_outcomes_or_hidden_fields():
    campaigns, _ = build_upworthy_campaigns(upworthy_rows())
    campaign = campaigns[0]
    inputs = campaign.inputs()
    flat = str(inputs)
    for forbidden in ("impressions", "clicks", "winner", "significance", "excerpt", "lede"):
        assert forbidden not in flat
    assert {s["id"] for s in inputs["stimuli"]} == set(campaign.observations)


def test_inputs_are_independent_of_observed_clicks():
    rows = upworthy_rows()
    changed = rows.copy()
    changed["clicks"] = changed["clicks"] + 7
    a, _ = build_upworthy_campaigns(rows)
    b, _ = build_upworthy_campaigns(changed)
    assert [c.inputs() for c in a] == [c.inputs() for c in b]
    assert [c.observations for c in a] != [c.observations for c in b]


def test_arm_order_does_not_depend_on_outcomes():
    campaigns, _ = build_upworthy_campaigns(upworthy_rows(tests=1))
    flipped = upworthy_rows(tests=1)
    flipped["clicks"] = flipped["clicks"].iloc[::-1].to_numpy()
    other, _ = build_upworthy_campaigns(flipped)
    assert [s.id for s in campaigns[0].stimuli] == [s.id for s in other[0].stimuli]


def test_randomization_problem_tests_are_excluded_and_counted():
    rows = upworthy_rows(tests=3)
    rows.loc[rows.clickability_test_id == "t1", "problem"] = 1
    campaigns, report = build_upworthy_campaigns(rows)
    assert {c.campaign_id for c in campaigns} == {"upworthy:t0", "upworthy:t2"}
    assert report["excluded"]["randomization_problem"] == 1


def test_duplicate_headlines_inside_a_test_cannot_be_attributed_to_text():
    rows = upworthy_rows(tests=1, arms=3)
    rows.loc[1, "headline"] = rows.loc[0, "headline"]
    campaigns, report = build_upworthy_campaigns(rows)
    assert campaigns == []
    assert report["excluded"]["too_few_distinct_arms"] == 1


def test_arm_count_and_exposure_limits():
    rows = pd.concat(
        [
            upworthy_rows(tests=1, arms=5).assign(clickability_test_id="many"),
            upworthy_rows(tests=1, arms=2).assign(clickability_test_id="small", impressions=100),
            upworthy_rows(tests=1, arms=2).assign(clickability_test_id="ok"),
        ]
    )
    campaigns, report = build_upworthy_campaigns(rows)
    assert [c.campaign_id for c in campaigns] == ["upworthy:ok"]
    assert report["excluded"]["too_many_arms"] == 1
    assert report["excluded"]["low_impressions"] == 1


@pytest.mark.parametrize("column,value", [("clicks", 5000), ("clicks", -1), ("impressions", 2.5)])
def test_impossible_counts_fail_loudly(column, value):
    rows = upworthy_rows(tests=1)
    rows[column] = rows[column].astype(float)
    rows.loc[0, column] = value
    with pytest.raises(ValueError):
        build_upworthy_campaigns(rows)


def test_missing_required_columns_fail():
    with pytest.raises(ValueError, match="colonne"):
        build_upworthy_campaigns(upworthy_rows().drop(columns=["headline"]))


def test_domain_is_declared_as_news_headline_not_paid_ads():
    campaigns, _ = build_upworthy_campaigns(upworthy_rows(tests=1))
    assert campaigns[0].domain.kind == "news_headline"
    assert campaigns[0].domain.language == "en"
    assert any("immagin" in x for x in campaigns[0].limitations)


def gwwc_rows():
    rows = []
    for ad in ("Ad A", "Ad B"):
        for i in range(3):
            rows.append(
                {
                    "Campaign name": "Giving Guide 2021 - Emotional",
                    "Ad name": ad,
                    "Text": f"{ad} testo {i}",
                    "Impressions": 2000 + i,
                    "Link clicks": 20 + i,
                    "Amount spent (USD)": 50.0,
                    "Reporting starts": "2021-11-15",
                    "Reporting ends": "2022-01-31",
                }
            )
    return pd.DataFrame(rows)


def test_gwwc_experiments_are_ad_groups_with_distinct_texts_and_paid_domain():
    campaigns, _ = build_gwwc_campaigns(gwwc_rows())
    assert len(campaigns) == 2
    assert all(c.domain.kind == "paid_social" for c in campaigns)
    assert all(len(c.stimuli) == 3 for c in campaigns)
    assert "clicks" not in str(campaigns[0].inputs())


def test_pairs_cover_all_arm_combinations():
    campaigns, _ = build_gwwc_campaigns(gwwc_rows())
    assert len(campaigns[0].pairs()) == 3


def test_split_is_by_campaign_deterministic_and_disjoint():
    campaigns, _ = build_upworthy_campaigns(upworthy_rows(tests=40, arms=2))
    first = split_campaigns(campaigns, test_fraction=0.3)
    again = split_campaigns(list(reversed(campaigns)), test_fraction=0.3)
    dev = {c.campaign_id for c in first["dev"]}
    test = {c.campaign_id for c in first["test"]}
    assert dev and test and not dev & test
    assert dev | test == {c.campaign_id for c in campaigns}
    assert first["manifest"]["test_sha256"] == again["manifest"]["test_sha256"]
    assert {c.campaign_id for c in again["test"]} == test


def test_split_does_not_change_when_outcomes_change():
    rows = upworthy_rows(tests=40, arms=2)
    changed = rows.assign(clicks=rows.clicks + 3)
    a = split_campaigns(build_upworthy_campaigns(rows)[0], test_fraction=0.3)
    b = split_campaigns(build_upworthy_campaigns(changed)[0], test_fraction=0.3)
    assert a["manifest"]["test_sha256"] == b["manifest"]["test_sha256"]


def test_test_campaigns_sharing_text_with_dev_are_dropped_not_leaked():
    rows = upworthy_rows(tests=40, arms=2)
    campaigns, _ = build_upworthy_campaigns(rows)
    split = split_campaigns(campaigns, test_fraction=0.3)
    victim = split["test"][0]
    dev_text = split["dev"][0].stimuli[0].headline
    leaked = [
        c
        if c.campaign_id != victim.campaign_id
        else c.model_copy(
            update={"stimuli": [c.stimuli[0].model_copy(update={"headline": dev_text}), *c.stimuli[1:]]}
        )
        for c in campaigns
    ]
    again = split_campaigns(leaked, test_fraction=0.3)
    assert victim.campaign_id not in {c.campaign_id for c in again["test"]}
    assert victim.campaign_id in again["manifest"]["dropped_for_text_overlap"]


def test_fetch_source_rejects_modified_files():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"not the file"))
    with pytest.raises(ValueError, match="checksum"):
        fetch_source("upworthy", transport=transport)


def test_fetch_source_accepts_the_pinned_checksum(monkeypatch):
    payload = b"a,b\n1,2\n"
    monkeypatch.setattr("audience_simulator.corpus.UPWORTHY_SHA256", hashlib.sha256(payload).hexdigest())
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=payload))
    assert fetch_source("upworthy", transport=transport) == payload
    assert len(UPWORTHY_SHA256) == 64


def test_newcombe_interval_resolves_a_large_difference_and_not_a_tiny_one():
    from audience_simulator.corpus import newcombe_interval

    low, high = newcombe_interval(500, 10000, 300, 10000)
    assert low > 0
    low, high = newcombe_interval(51, 1000, 50, 1000)
    assert low < 0 < high


def test_newcombe_handles_zero_clicks():
    from audience_simulator.corpus import newcombe_interval

    low, high = newcombe_interval(0, 1000, 0, 1000)
    assert low < 0 < high


def test_resolved_pairs_use_only_observed_counts():
    campaigns, _ = build_upworthy_campaigns(upworthy_rows(tests=1, arms=2))
    resolved = campaigns[0].resolved_pairs()
    assert isinstance(resolved, list)
    big = upworthy_rows(tests=1, arms=2)
    big["impressions"] = [20000, 20000]
    big["clicks"] = [1000, 400]
    campaign = build_upworthy_campaigns(big)[0][0]
    assert len(campaign.resolved_pairs()) == 1
    assert campaign.resolved_pairs()[0]["higher"] in campaign.observations


class FakeStore:
    def __init__(self):
        self.files = {}

    def write_json(self, key, value):
        self.files[key] = value

    def write_bytes(self, key, raw, content_type="application/octet-stream"):
        self.files[key] = raw


def test_prepare_keeps_test_outcomes_out_of_the_inputs_file():
    from audience_simulator.corpus import prepare_corpus

    rows = upworthy_rows(tests=40, arms=2)
    store = FakeStore()
    summary = prepare_corpus(store, rows)
    assert summary["status"] == "prepared_no_ai_calls"
    assert summary["test"]["campaigns"] > 0
    inputs = str(store.files["corpus/test/inputs.json"])
    assert "impressions" not in inputs and "clicks" not in inputs
    assert (
        "observations" in store.files["corpus/test/observations.json"]
        or store.files["corpus/test/observations.json"]
    )
    assert store.files["corpus/split-manifest.json"]["test_sha256"] == summary["manifest"]["test_sha256"]
    assert "corpus/dev.json" in store.files


def test_prepare_reports_power_feasibility_against_the_preregistered_minimum():
    from audience_simulator.corpus import MIN_RESOLVED_TEST_PAIRS, prepare_corpus

    rows = upworthy_rows(tests=40, arms=2)
    summary = prepare_corpus(FakeStore(), rows)
    assert MIN_RESOLVED_TEST_PAIRS == 69
    assert summary["feasibility"]["minimum_resolved_test_pairs"] == 69
    assert summary["feasibility"]["meets_minimum"] is (
        summary["test"]["resolved_pairs"] >= MIN_RESOLVED_TEST_PAIRS
    )


def test_randomization_window_is_applied_by_date_when_the_flag_column_is_absent():
    rows = upworthy_rows(tests=3).drop(columns=["problem"])
    rows.loc[rows.clickability_test_id == "t1", "created_at"] = "2013-08-01 09:00:00"
    campaigns, report = build_upworthy_campaigns(rows)
    assert {c.campaign_id for c in campaigns} == {"upworthy:t0", "upworthy:t2"}
    assert report["excluded"]["randomization_problem"] == 1


def test_unparseable_dates_without_flag_column_fail_instead_of_slipping_through():
    rows = upworthy_rows(tests=1).drop(columns=["problem"])
    rows["created_at"] = "non una data"
    with pytest.raises(ValueError, match="data"):
        build_upworthy_campaigns(rows)


def test_gwwc_ambiguous_groups_are_excluded_and_counted_not_fatal():
    rows = gwwc_rows()
    duplicate = rows.iloc[[0, 1]].copy().assign(**{"Ad name": "Ad dup", "Text": "stesso testo"})
    missing = rows.iloc[[0, 1]].copy().assign(**{"Ad name": "Ad vuoto", "Text": [None, "ok"]})
    campaigns, report = build_gwwc_campaigns(pd.concat([rows, duplicate, missing], ignore_index=True))
    assert len(campaigns) == 2
    assert report["excluded"]["ambiguous_text"] == 2
