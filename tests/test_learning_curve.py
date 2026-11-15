import numpy as np
import pandas as pd
from audience_simulator.corpus import build_upworthy_campaigns
from audience_simulator.learning_curve import (
    RichTextModel,
    extra_training_pool,
    learning_curve,
    text_groups,
)
from audience_simulator.validation import TextBaseline

WORDS = ["cats", "dogs", "money", "health", "travel", "music", "science", "food", "sports", "movies"]


def frame(tests=120, arms=3, seed=0, start=0):
    """Synthetic archive where headlines containing 'secret' really get more clicks: a learnable signal."""
    rng = np.random.default_rng(seed)
    rows = []
    for t in range(start, start + tests):
        for a in range(arms):
            hot = a == 0
            topic = WORDS[(t + a) % len(WORDS)]
            headline = (
                f"{'The secret truth about' if hot else 'Some notes on'} {topic} number {t} variant {a}"
            )
            impressions = 4000
            rows.append(
                {
                    "created_at": "2014-06-01 10:00:00.000",
                    "clickability_test_id": f"t{t:04d}",
                    "headline": headline,
                    "impressions": impressions,
                    "clicks": int(rng.binomial(impressions, 0.06 if hot else 0.02)),
                }
            )
    return pd.DataFrame(rows)


def test_more_data_helps_a_model_with_capacity_and_the_curve_reports_it():
    dev, _ = build_upworthy_campaigns(frame())
    report = learning_curve(dev, fractions=(0.1, 1.0), bootstrap=200)
    rich = {r["training"]: r for r in report["curve"] if r["model"] == "rich_text"}
    assert (
        rich["100%"]["accuracy"] > 0.9
        and rich["100%"]["training_resolved_pairs"] > rich["10%"]["training_resolved_pairs"]
    )
    assert report["split"] == "dev" and all(len(r["ci95"]) == 2 for r in report["curve"])
    assert {"B0", "rich_text"} == {r["model"] for r in report["curve"]}
    assert "rich_text: 100% vs 25%" not in report["paired_tests"]  # that step was not requested


def test_campaigns_sharing_a_headline_stay_in_the_same_fold():
    dev, _ = build_upworthy_campaigns(frame(tests=20))
    twin = dev[0].model_copy(update={"campaign_id": "upworthy:twin"})
    groups = text_groups([*dev, twin])
    assert groups["upworthy:twin"] == groups[dev[0].campaign_id]
    assert len(set(groups.values())) == len(dev)


def test_extra_pool_is_training_only_and_never_overlaps_dev_or_test_inputs():
    source = frame(tests=40, arms=6, start=1000)
    dev, _ = build_upworthy_campaigns(frame(tests=20))
    pool_all, _ = build_upworthy_campaigns(source, max_arms=40)
    leaked = pool_all[0]
    test_inputs = [
        {"campaign_id": "upworthy:other", "stimuli": [{"id": "x", "headline": leaked.stimuli[0].headline}]}
    ]
    pool, info = extra_training_pool(source, dev, test_inputs)
    assert leaked.campaign_id not in {c.campaign_id for c in pool}
    assert info == {"extra_campaigns": len(pool_all) - 1, "dropped_for_text_overlap": 1}
    assert "observations" not in test_inputs[0]  # only inputs of the locked test are ever needed


def test_models_score_every_stimulus():
    dev, _ = build_upworthy_campaigns(frame(tests=40))
    for model in (TextBaseline().fit(dev), RichTextModel().fit(dev)):
        scores = model.score(dev[0])
        assert set(scores) == {s.id for s in dev[0].stimuli}
