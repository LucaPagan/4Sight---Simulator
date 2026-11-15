"""Does more training data make the trainable parts more accurate? Learning curves on the dev split only.

What can be trained here is a pairwise text model (which headline of a pair gets the higher CTR). The language model
behind the agents is not trained by this project, so more campaign data cannot change it; data can only improve the
models and calibrations fitted around it. This module measures that honestly:

- out-of-fold accuracy on resolved dev pairs, folds grouped by campaign, as in ``validation.cross_validated_scores``;
- nested training subsets (5% ... 100% of the training campaigns of each fold), then 100% plus an *extra* pool:
  Upworthy tests with more than four headlines, excluded from the benchmark only for LLM cost. Extra campaigns that
  share a normalised headline with the test inputs or with dev are dropped; test *outcomes* are never read;
- two models: B0 (seven surface features, the pre-registered baseline) and a richer text model (word and character
  n-grams) that has enough capacity to profit from more data.

PROMISE rule 1 holds: nothing here touches the locked test observations, and results are development evidence only.
"""

import hashlib

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from .corpus import ComparableCampaign, _normalized, build_upworthy_campaigns
from .validation import (
    TextBaseline,
    _stimulus_text,
    cluster_bootstrap,
    metrics,
    pair_outcomes,
    paired_permutation,
    text_features,
)

FRACTIONS = (0.05, 0.1, 0.25, 0.5, 1.0)
FOLDS = 5
EXTRA_MAX_ARMS = 40


class RichTextModel:
    """Pairwise logistic model on word and character n-grams plus the seven surface features."""

    def __init__(self, c=0.3):
        self.c = c

    def _matrix(self, texts):
        surface = np.array([text_features(t) for t in texts]) / self.scale
        return hstack([self.words.transform(texts), self.chars.transform(texts), surface]).tocsr()

    def fit(self, campaigns):
        texts = [_stimulus_text(s) for c in campaigns for s in c.stimuli]
        self.words = TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True, lowercase=True).fit(
            texts
        )
        self.chars = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), min_df=5, sublinear_tf=True, lowercase=True
        ).fit(texts)
        surface = np.array([text_features(t) for t in texts])
        self.scale = surface.std(axis=0)
        self.scale[self.scale == 0] = 1.0
        higher, lower = [], []
        for campaign in campaigns:
            text = {s.id: _stimulus_text(s) for s in campaign.stimuli}
            for item in campaign.resolved_pairs():
                higher.append(text[item["higher"]])
                lower.append(text[next(i for i in item["pair"] if i != item["higher"])])
        if not higher:
            raise ValueError("Nessuna coppia risolta per addestrare il modello")
        diff = self._matrix(higher) - self._matrix(lower)
        x = np.vstack([diff.toarray(), -diff.toarray()]) if diff.shape[0] * diff.shape[1] < 2e7 else None
        y = np.concatenate([np.ones(diff.shape[0]), np.zeros(diff.shape[0])])
        if x is None:
            from scipy.sparse import vstack

            x = vstack([diff, -diff]).tocsr()
        self.model = LogisticRegression(C=self.c, fit_intercept=False, max_iter=2000).fit(x, y)
        return self

    def score(self, campaign):
        texts = [_stimulus_text(s) for s in campaign.stimuli]
        values = self._matrix(texts) @ self.model.coef_[0]
        return {s.id: float(v) for s, v in zip(campaign.stimuli, values, strict=True)}


MODELS = {"B0": TextBaseline, "rich_text": RichTextModel}


def _fold(campaign_id, folds=FOLDS):
    return int(hashlib.sha256(campaign_id.encode()).hexdigest()[:8], 16) % folds


def text_groups(campaigns):
    """campaign_id -> group id; campaigns sharing a normalised headline are one group (same article retested).

    Folds are assigned by group, otherwise a model can memorise a headline it meets again in the held-out fold."""
    parent = {c.campaign_id: c.campaign_id for c in campaigns}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner = {}
    for campaign in campaigns:
        for stimulus in campaign.stimuli:
            key = _normalized(_stimulus_text(stimulus))
            if key in owner:
                parent[find(campaign.campaign_id)] = find(owner[key])
            else:
                owner[key] = campaign.campaign_id
    return {c.campaign_id: find(c.campaign_id) for c in campaigns}


def _order(campaigns):
    """Deterministic order independent of outcomes, so smaller subsets are nested in larger ones."""
    return sorted(campaigns, key=lambda c: hashlib.sha256(f"subset|{c.campaign_id}".encode()).hexdigest())


def extra_training_pool(frame, dev, test_inputs):
    """Upworthy tests left out of the benchmark for having more than four headlines. Training only."""
    campaigns, _ = build_upworthy_campaigns(frame, max_arms=EXTRA_MAX_ARMS)
    blocked_ids = {c.campaign_id for c in dev} | {c["campaign_id"] for c in test_inputs}
    blocked_text = {_normalized(_stimulus_text(s)) for c in dev for s in c.stimuli} | {
        _normalized(s.get("headline") or s.get("primary_text") or "")
        for c in test_inputs
        for s in c["stimuli"]
    }
    pool, dropped = [], 0
    for campaign in campaigns:
        if campaign.campaign_id in blocked_ids:
            continue
        if any(_normalized(_stimulus_text(s)) in blocked_text for s in campaign.stimuli):
            dropped += 1
            continue
        pool.append(campaign)
    return pool, {"extra_campaigns": len(pool), "dropped_for_text_overlap": dropped}


def learning_curve(dev, extra=(), fractions=FRACTIONS, models=MODELS, folds=FOLDS, bootstrap=1000):
    """Out-of-fold dev accuracy per model and training size. Returns the curve and paired tests on the last steps."""
    rows = {}
    sizes = {}
    group = text_groups(dev)
    for k in range(folds):
        train = _order([c for c in dev if _fold(group[c.campaign_id], folds) != k])
        held = [c for c in dev if _fold(group[c.campaign_id], folds) == k]
        if not held:
            continue
        steps = [(f"{int(f * 100)}%", train[: max(2, int(round(f * len(train))))]) for f in fractions]
        if extra:
            steps.append(("100%+extra", train + list(extra)))
        for label, subset in steps:
            pairs = sum(len(c.resolved_pairs()) for c in subset)
            sizes.setdefault(label, []).append((len(subset), pairs))
            for name, factory in models.items():
                try:
                    model = factory().fit(subset)
                except ValueError:
                    continue
                scores = {c.campaign_id: model.score(c) for c in held}
                rows.setdefault((name, label), []).extend(pair_outcomes(held, scores))
    curve = []
    for (name, label), outcome in rows.items():
        ci = cluster_bootstrap(outcome, n=bootstrap)
        campaigns, pairs = np.mean(sizes[label], axis=0)
        curve.append(
            {
                "model": name,
                "training": label,
                "training_campaigns": float(campaigns),
                "training_resolved_pairs": float(pairs),
                "evaluated_pairs": metrics(outcome)["resolved_pairs"],
                "accuracy": ci["estimate"],
                "ci95": [ci["low"], ci["high"]],
                "log_loss": metrics(outcome)["log_loss"],
            }
        )
    tests = {}

    def compare(key, a, b):
        if a in rows and b in rows and len(rows[a]) == len(rows[b]):
            tests[key] = paired_permutation(rows[a], rows[b])

    for name in models:
        compare(f"{name}: 100% vs 25%", (name, "100%"), (name, "25%"))
        compare(f"{name}: 100%+extra vs 100%", (name, "100%+extra"), (name, "100%"))
    last = "100%+extra" if extra else "100%"
    compare(f"rich_text vs B0 ({last})", ("rich_text", last), ("B0", last))
    return {
        "split": "dev",
        "folds": folds,
        "curve": sorted(curve, key=lambda r: (r["model"], r["training_campaigns"])),
        "paired_tests": tests,
        "shared_headline_groups": len(set(group.values())),
        "note": "Accuratezza fuori campione sulle coppie risolte di sviluppo, fold per campagna. Il test congelato non è stato letto.",
    }


def run(store, source_csv):
    dev = [ComparableCampaign.model_validate(c) for c in store.read_json("corpus/dev.json")]
    test_inputs = store.read_json("corpus/test/inputs.json")
    frame = pd.read_csv(source_csv, index_col=0, low_memory=False)
    extra, info = extra_training_pool(frame, dev, test_inputs)
    report = learning_curve(dev, extra)
    report["extra_pool"] = info
    store.write_json("validation/learning-curve.json", report)
    return report
