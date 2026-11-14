import json

import numpy as np
import pytest
from audience_simulator.corpus import (
    ComparableCampaign,
    CorpusDomain,
    Observation,
    Stimulus,
    sample_campaigns,
)
from audience_simulator.validation import (
    TextBaseline,
    cluster_bootstrap,
    config_hash,
    cross_validated_scores,
    freeze_config,
    metrics,
    pair_outcomes,
    paired_permutation,
    run_validation,
)

DOMAIN = CorpusDomain(
    kind="news_headline", platform="p", country="US", language="en", objective="click", placement="x"
)


def campaign(index, long_wins=True, noise=False, n=20000):
    """Two arms; the longer headline gets the higher CTR (or the reverse when long_wins is False)."""
    short, long_ = f"Short title {index}", f"A much longer and more detailed title number {index} here"
    high, low = (1000, 500) if not noise else (800, 790)
    clicks_long, clicks_short = (high, low) if long_wins else (low, high)
    stimuli = [Stimulus(id=f"s{index}", headline=short), Stimulus(id=f"l{index}", headline=long_)]
    return ComparableCampaign(
        campaign_id=f"c{index:03d}",
        source="synthetic",
        domain=DOMAIN,
        stimuli=stimuli,
        observations={
            f"s{index}": Observation(impressions=n, clicks=clicks_short),
            f"l{index}": Observation(impressions=n, clicks=clicks_long),
        },
    )


def corpus(n=40, **kwargs):
    return [campaign(i, **kwargs) for i in range(n)]


def test_sample_is_deterministic_independent_of_order_and_of_outcomes():
    campaigns = corpus(100)
    first = sample_campaigns(campaigns, 60)
    assert first == sample_campaigns(list(reversed(campaigns)), 60)
    changed = [
        c.model_copy(update={"observations": campaign(0, long_wins=False).observations}) for c in campaigns
    ]
    assert first == sample_campaigns(changed, 60)
    assert len(first) == 60 and len(set(first)) == 60
    assert sample_campaigns(campaigns[:10], 60) == sorted(c.campaign_id for c in campaigns[:10])


def test_text_baseline_learns_a_text_feature_from_dev_and_ranks_new_campaigns():
    model = TextBaseline().fit(corpus(30))
    scores = model.score(campaign(99))
    assert scores["l99"] > scores["s99"]


def test_text_baseline_needs_resolved_training_pairs():
    with pytest.raises(ValueError):
        TextBaseline().fit(corpus(5, noise=True))


def test_pair_outcomes_cover_resolved_pairs_only_and_respect_margin():
    resolved = campaign(1)
    unresolved = campaign(2, noise=True)
    scores = {"c001": {"s1": 0.0, "l1": 1.0}, "c002": {"s2": 0.0, "l2": 1.0}}
    rows = pair_outcomes([resolved, unresolved], scores)
    assert [r["campaign_id"] for r in rows] == ["c001"]
    assert rows[0]["correct"] is True and rows[0]["declared"] is True
    rows = pair_outcomes([resolved], scores, margin=2.0)
    assert rows[0]["declared"] is False and rows[0]["correct"] is False


def test_metrics_define_accuracy_and_false_winners_on_resolved_pairs():
    rows = [
        {"campaign_id": "a", "declared": True, "correct": True, "p_higher": 0.9},
        {"campaign_id": "a", "declared": True, "correct": False, "p_higher": 0.4},
        {"campaign_id": "b", "declared": True, "correct": True, "p_higher": 0.8},
        {"campaign_id": "c", "declared": False, "correct": False, "p_higher": 0.5},
    ]
    m = metrics(rows)
    assert m["resolved_pairs"] == 4
    assert m["accuracy"] == 0.5
    assert m["declared_rate"] == 0.75
    assert m["accuracy_on_declared"] == pytest.approx(2 / 3)
    assert m["false_winner_rate"] == pytest.approx(1 / 3)
    assert 0 < m["brier"] < 1 and m["log_loss"] > 0


def test_cluster_bootstrap_resamples_campaigns_and_is_seeded():
    rows = [
        {"campaign_id": f"c{i}", "declared": True, "correct": i % 4 != 0, "p_higher": 0.7} for i in range(40)
    ]
    first = cluster_bootstrap(rows, "accuracy", n=300, seed=1)
    assert first == cluster_bootstrap(rows, "accuracy", n=300, seed=1)
    assert first["low"] < metrics(rows)["accuracy"] < first["high"]


def test_permutation_test_separates_a_real_difference_from_none():
    good = [{"campaign_id": f"c{i}", "declared": True, "correct": True, "p_higher": 0.9} for i in range(40)]
    rng = np.random.default_rng(0)
    coin = [
        {"campaign_id": f"c{i}", "declared": True, "correct": bool(rng.integers(2)), "p_higher": 0.5}
        for i in range(40)
    ]
    assert paired_permutation(good, coin, n=2000, seed=0)["p_value"] < 0.01
    assert paired_permutation(good, good, n=2000, seed=0)["p_value"] > 0.5


def test_cross_validation_never_scores_a_campaign_with_a_model_trained_on_it(monkeypatch):
    seen = []
    original = TextBaseline.fit

    def spy(self, campaigns):
        seen.append({c.campaign_id for c in campaigns})
        return original(self, campaigns)

    monkeypatch.setattr(TextBaseline, "fit", spy)
    campaigns = corpus(30)
    scores = cross_validated_scores(campaigns, folds=5)
    assert set(scores) == {c.campaign_id for c in campaigns}
    assert all(len(train) < 30 for train in seen)
    for campaign_id in scores:
        assert sum(campaign_id in train for train in seen) == len(seen) - 1


class FakeStore:
    def __init__(self):
        self.files = {}

    def write_json(self, key, value):
        self.files[key] = json.loads(json.dumps(value))

    def write_bytes(self, key, raw, content_type="application/octet-stream"):
        self.files[key] = raw

    def read_json(self, key):
        if key not in self.files:
            raise FileNotFoundError(key)
        return self.files[key]


def stored_corpus(dev=60, test=70):
    campaigns = corpus(dev + test)
    dev_set, test_set = campaigns[:dev], campaigns[dev:]
    store = FakeStore()
    store.write_json("corpus/dev.json", [c.model_dump(mode="json") for c in dev_set])
    store.write_json("corpus/test/inputs.json", [c.inputs() for c in test_set])
    store.write_json(
        "corpus/test/observations.json",
        {c.campaign_id: {k: v.model_dump() for k, v in c.observations.items()} for c in test_set},
    )
    store.write_json("corpus/split-manifest.json", {"test_sha256": "abc"})
    return store


CONFIG = {"prompt_version": "v-test", "model": "none", "margin": 0.0, "sample_size": 60}


@pytest.fixture
def promise(tmp_path):
    path = tmp_path / "PROMISE.md"
    path.write_text("pre-registered v1")
    return path


def test_dev_evaluation_reports_the_baseline_and_never_reads_test_outcomes(promise):
    store = stored_corpus()
    report = run_validation(store, "dev")
    assert report["systems"]["B0"]["metrics"]["resolved_pairs"] > 0
    assert report["systems"]["B0"]["metrics"]["accuracy"] > 0.9
    assert "random_accuracy" in report["reference"]


def test_test_split_refuses_without_final_flag_and_logs_the_attempt(promise):
    store = stored_corpus()
    with pytest.raises(PermissionError, match="final"):
        run_validation(store, "test", promise_path=promise)
    log = store.read_json("validation/test-evaluations.json")
    assert [e["status"] for e in log] == ["refused_not_final"]


def test_test_split_refuses_without_frozen_config_or_with_wrong_hash(promise):
    store = stored_corpus()
    with pytest.raises(PermissionError, match="congelata"):
        run_validation(store, "test", final=True, config_hash="x", promise_path=promise)
    freeze_config(store, CONFIG, promise_path=promise)
    with pytest.raises(PermissionError, match="hash"):
        run_validation(store, "test", final=True, config_hash="wrong", promise_path=promise)


def test_changing_the_preregistration_after_freezing_blocks_the_test(promise):
    store = stored_corpus()
    frozen = freeze_config(store, CONFIG, promise_path=promise)
    promise.write_text("pre-registered v2, thresholds relaxed")
    with pytest.raises(PermissionError, match="PROMISE"):
        run_validation(store, "test", final=True, config_hash=frozen["config_hash"], promise_path=promise)


def test_final_evaluation_runs_once_on_the_frozen_sample_only(promise):
    store = stored_corpus()
    frozen = freeze_config(store, CONFIG, promise_path=promise)
    assert len(frozen["sample_ids"]) == 60
    report = run_validation(
        store, "test", final=True, config_hash=frozen["config_hash"], promise_path=promise
    )
    assert report["campaigns_evaluated"] == 60
    assert set(report["systems"]) == {"B0"}
    with pytest.raises(PermissionError, match="già"):
        run_validation(store, "test", final=True, config_hash=frozen["config_hash"], promise_path=promise)
    statuses = [e["status"] for e in store.read_json("validation/test-evaluations.json")]
    assert statuses == ["completed", "refused_already_final"]


def test_config_hash_depends_on_every_frozen_field():
    base = config_hash({"a": 1}, ["x"], "t", "p")
    assert base != config_hash({"a": 2}, ["x"], "t", "p")
    assert base != config_hash({"a": 1}, ["y"], "t", "p")
    assert base != config_hash({"a": 1}, ["x"], "u", "p")
    assert base != config_hash({"a": 1}, ["x"], "t", "q")


def test_external_system_scores_are_compared_against_the_baseline(promise):
    store = stored_corpus()
    frozen = freeze_config(store, CONFIG, promise_path=promise)
    inputs = {c["campaign_id"]: c for c in store.read_json("corpus/test/inputs.json")}
    scores = {
        cid: {s["id"]: (1.0 if s["id"].startswith("l") else 0.0) for s in inputs[cid]["stimuli"]}
        for cid in frozen["sample_ids"]
    }
    store.write_json("validation/scores/B2-test.json", scores)
    report = run_validation(
        store, "test", final=True, config_hash=frozen["config_hash"], promise_path=promise
    )
    assert set(report["systems"]) == {"B0", "B2"}
    assert "vs_B0" in report["systems"]["B2"]


def test_dev_comparison_is_restricted_to_campaigns_every_system_scored():
    store = stored_corpus(dev=60)
    campaigns = [campaign(i) for i in range(60)]
    subset = campaigns[:20]
    store.write_json(
        "validation/scores/B2-dev.json",
        {c.campaign_id: {s.id: float(s.id.startswith("l")) for s in c.stimuli} for c in subset},
    )
    report = run_validation(store, "dev")
    assert report["campaigns_evaluated"] == 20
    assert (
        report["systems"]["B0"]["metrics"]["resolved_pairs"]
        == report["systems"]["B2"]["metrics"]["resolved_pairs"]
    )
