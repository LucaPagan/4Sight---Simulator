"""Independent verification harness: baselines, pair metrics, cluster statistics, and a locked test split.

Everything here operates on resolved pairs only (docs/PROMISE.md). The test split is readable only through
``run_validation(..., final=True)`` against a frozen configuration, and a final evaluation runs once.
"""

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from .calibration import _smoothed_logit
from .corpus import ComparableCampaign, sample_ids

SYSTEMS = ("B1", "B2")
LOG_KEY = "validation/test-evaluations.json"
FROZEN_KEY = "validation/frozen-config.json"
PROMISE = Path("docs/PROMISE.md")


def _stimulus_text(stimulus):
    return stimulus.headline or stimulus.primary_text or ""


def text_features(text):
    words = re.findall(r"\w+", text)
    letters = [c for c in text if c.isalpha()]
    return np.array(
        [
            math.log1p(len(text)),
            math.log1p(len(words)),
            float(any(c.isdigit() for c in text)),
            float("?" in text),
            float("!" in text),
            sum(c.isupper() for c in letters) / len(letters) if letters else 0.0,
            float(bool(words) and words[0].isdigit()),
        ]
    )


class TextBaseline:
    """B0: no LLM. Pairwise logistic model on simple text features, trained on resolved dev pairs."""

    def fit(self, campaigns):
        rows = []
        for campaign in campaigns:
            text = {s.id: text_features(_stimulus_text(s)) for s in campaign.stimuli}
            for item in campaign.resolved_pairs():
                lower = next(i for i in item["pair"] if i != item["higher"])
                rows.append(text[item["higher"]] - text[lower])
        if not rows:
            raise ValueError("Nessuna coppia risolta per addestrare la baseline")
        x = np.array(rows)
        self.scale = x.std(axis=0)
        self.scale[self.scale == 0] = 1.0
        z = np.vstack([x / self.scale, -x / self.scale])
        y = np.concatenate([np.ones(len(x)), np.zeros(len(x))])
        self.model = LogisticRegression(C=1.0, fit_intercept=False).fit(z, y)
        return self

    def score(self, campaign):
        weights = self.model.coef_[0] / self.scale
        return {s.id: float(weights @ text_features(_stimulus_text(s))) for s in campaign.stimuli}


def cross_validated_scores(campaigns, folds=5):
    """Out-of-fold B0 scores grouped by campaign; a campaign is never scored by a model that saw it."""
    fold = {
        c.campaign_id: int(hashlib.sha256(c.campaign_id.encode()).hexdigest()[:8], 16) % folds
        for c in campaigns
    }
    scores = {}
    for k in range(folds):
        train = [c for c in campaigns if fold[c.campaign_id] != k]
        held = [c for c in campaigns if fold[c.campaign_id] == k]
        if not held:
            continue
        model = TextBaseline().fit(train)
        scores.update({c.campaign_id: model.score(c) for c in held})
    return scores


def pair_outcomes(campaigns, scores, margin=0.0):
    """One row per resolved pair. A pair inside the margin is not declared and counts as not correct."""
    rows = []
    for campaign in campaigns:
        values = scores[campaign.campaign_id]
        for item in campaign.resolved_pairs():
            higher = item["higher"]
            lower = next(i for i in item["pair"] if i != higher)
            gap = values[higher] - values[lower]
            declared = abs(gap) > margin
            rows.append(
                {
                    "campaign_id": campaign.campaign_id,
                    "pair": list(item["pair"]),
                    "declared": declared,
                    "correct": bool(declared and gap > 0),
                    "p_higher": float(1 / (1 + math.exp(-gap))),
                }
            )
    return rows


def metrics(rows):
    n = len(rows)
    declared = [r for r in rows if r["declared"]]
    correct = sum(r["correct"] for r in rows)
    p = np.clip([r["p_higher"] for r in rows], 1e-9, 1 - 1e-9)
    on_declared = sum(r["correct"] for r in declared) / len(declared) if declared else None
    return {
        "resolved_pairs": n,
        "accuracy": correct / n if n else None,
        "declared_rate": len(declared) / n if n else None,
        "accuracy_on_declared": on_declared,
        "false_winner_rate": None if on_declared is None else 1 - on_declared,
        "brier": float(np.mean((1 - p) ** 2)) if n else None,
        "log_loss": float(-np.mean(np.log(p))) if n else None,
    }


def _by_campaign(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["campaign_id"], []).append(row)
    return groups


def cluster_bootstrap(rows, statistic="accuracy", n=2000, seed=0):
    groups = _by_campaign(rows)
    keys = sorted(groups)
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n):
        chosen = rng.integers(0, len(keys), len(keys))
        value = metrics([r for i in chosen for r in groups[keys[i]]])[statistic]
        if value is not None:
            values.append(value)
    low, high = np.percentile(values, [2.5, 97.5])
    return {"estimate": metrics(rows)[statistic], "low": float(low), "high": float(high), "resamples": n}


def paired_permutation(rows_a, rows_b, n=10000, seed=0):
    """Sign-flip test per campaign on the difference in correct pairs (a better than b, one-sided)."""
    a, b = _by_campaign(rows_a), _by_campaign(rows_b)
    if set(a) != set(b) or any(len(a[k]) != len(b[k]) for k in a):
        raise ValueError("Le due valutazioni non coprono le stesse coppie")
    diffs = np.array(
        [sum(r["correct"] for r in a[k]) - sum(r["correct"] for r in b[k]) for k in sorted(a)], float
    )
    total = sum(len(v) for v in a.values())
    observed = diffs.sum()
    rng = np.random.default_rng(seed)
    flips = rng.choice([-1.0, 1.0], size=(n, len(diffs)))
    exceed = int(((flips * diffs).sum(axis=1) >= observed).sum())
    return {
        "difference_accuracy": float(observed / total),
        "p_value": (exceed + 1) / (n + 1),
        "permutations": n,
    }


def interval_coverage(campaigns, scores, scale, quantile):
    """Share of pairs whose observed log-odds CTR difference falls inside scale*(score gap) +- quantile."""
    covered = total = 0
    for campaign in campaigns:
        values = scores[campaign.campaign_id]
        for a, b in campaign.pairs():
            oa, ob = campaign.observations[a], campaign.observations[b]
            observed = _smoothed_logit(oa.clicks, oa.impressions) - _smoothed_logit(ob.clicks, ob.impressions)
            covered += abs(observed - scale * (values[a] - values[b])) <= quantile
            total += 1
    return {"coverage": covered / total if total else None, "pairs": total, "nominal": 0.9}


def config_hash(config, sample_ids, test_sha256, promise_sha256):
    canonical = json.dumps(
        {"config": config, "sample_ids": sorted(sample_ids), "test": test_sha256, "promise": promise_sha256},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _promise_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(store, key, default):
    try:
        return store.read_json(key)
    except FileNotFoundError:
        return default


def _log(store, status, split, digest):
    log = _read(store, LOG_KEY, [])
    log.append({"at": datetime.now(UTC).isoformat(), "status": status, "split": split, "config_hash": digest})
    store.write_json(LOG_KEY, log)


def freeze_config(store, config, promise_path=PROMISE):
    """Freeze configuration, test sample and pre-registration hash before any test evaluation."""
    if any(e["status"] == "completed" for e in _read(store, LOG_KEY, [])):
        raise PermissionError(
            "Una valutazione finale è già stata completata: la configurazione non si modifica"
        )
    test_sha = store.read_json("corpus/split-manifest.json")["test_sha256"]
    test_ids = [c["campaign_id"] for c in store.read_json("corpus/test/inputs.json")]
    sample = sample_ids(test_ids, int(config.get("sample_size", 60)))
    promise = _promise_sha(promise_path)
    frozen = {
        "config": config,
        "sample_ids": sample,
        "test_sha256": test_sha,
        "promise_sha256": promise,
        "config_hash": config_hash(config, sample, test_sha, promise),
    }
    store.write_json(FROZEN_KEY, frozen)
    return frozen


def _external_scores(store, split, wanted=None):
    """Scores supplied by B1/B2 runs. With `wanted`, they must cover every campaign (test); else any subset."""
    systems = {}
    for name in SYSTEMS:
        scores = _read(store, f"validation/scores/{name}-{split}.json", None)
        if scores is None:
            continue
        if wanted is not None and not set(wanted) <= set(scores):
            raise ValueError(f"Punteggi incompleti per {name}")
        systems[name] = scores
    return systems


def _calibrations(store, scores):
    return {n: _read(store, f"validation/calibration-{n}.json", None) for n in scores if n != "B0"}


def _report(split, campaigns, scores_by_system, margin, calibrations=None):
    outcomes = {name: pair_outcomes(campaigns, s, margin) for name, s in scores_by_system.items()}
    systems = {}
    for name, rows in outcomes.items():
        entry = {"metrics": metrics(rows), "accuracy_ci95": cluster_bootstrap(rows, "accuracy")}
        if name != "B0":
            entry["vs_B0"] = paired_permutation(rows, outcomes["B0"])
            artifact = (calibrations or {}).get(name)
            if artifact and "conformal" in artifact:
                entry["interval_coverage"] = interval_coverage(
                    campaigns,
                    scores_by_system[name],
                    artifact["gate"]["out_of_fold_scale"],
                    artifact["conformal"]["quantile"],
                )
        systems[name] = entry
    return {
        "split": split,
        "campaigns_evaluated": len(campaigns),
        "margin": margin,
        "systems": systems,
        "reference": {"random_accuracy": 0.5},
    }


def run_validation(store, split, final=False, config_hash=None, promise_path=PROMISE):
    if split == "dev":
        campaigns = [ComparableCampaign.model_validate(c) for c in store.read_json("corpus/dev.json")]
        scores = {"B0": cross_validated_scores(campaigns)}
        scores.update(_external_scores(store, "dev"))
        common = set.intersection(*(set(v) for v in scores.values()))
        campaigns = [c for c in campaigns if c.campaign_id in common]
        scores = {name: {c.campaign_id: v[c.campaign_id] for c in campaigns} for name, v in scores.items()}
        report = _report("dev", campaigns, scores, 0.0, _calibrations(store, scores))
        store.write_json("validation/dev-report.json", report)
        return report
    if split != "test":
        raise ValueError("split deve essere dev o test")
    if not final:
        _log(store, "refused_not_final", "test", config_hash)
        raise PermissionError("Il test si valuta solo con --final e una configurazione congelata")
    frozen = _read(store, FROZEN_KEY, None)
    if frozen is None:
        _log(store, "refused_no_frozen_config", "test", config_hash)
        raise PermissionError("Configurazione congelata mancante: eseguire prima freeze")
    if config_hash != frozen["config_hash"]:
        _log(store, "refused_hash_mismatch", "test", config_hash)
        raise PermissionError("config_hash non corrisponde alla configurazione congelata")
    if _promise_sha(promise_path) != frozen["promise_sha256"]:
        _log(store, "refused_promise_changed", "test", config_hash)
        raise PermissionError("PROMISE.md è cambiato dopo il congelamento")
    if store.read_json("corpus/split-manifest.json")["test_sha256"] != frozen["test_sha256"]:
        _log(store, "refused_test_changed", "test", config_hash)
        raise PermissionError("Il test è cambiato dopo il congelamento")
    if any(e["status"] == "completed" and e["config_hash"] == config_hash for e in _read(store, LOG_KEY, [])):
        _log(store, "refused_already_final", "test", config_hash)
        raise PermissionError("Valutazione finale già eseguita per questa configurazione")
    dev = [ComparableCampaign.model_validate(c) for c in store.read_json("corpus/dev.json")]
    observations = store.read_json("corpus/test/observations.json")
    sample = set(frozen["sample_ids"])
    campaigns = [
        ComparableCampaign.model_validate(
            {**c, "source": "test", "observations": observations[c["campaign_id"]]}
        )
        for c in store.read_json("corpus/test/inputs.json")
        if c["campaign_id"] in sample
    ]
    baseline = TextBaseline().fit(dev)
    scores = {"B0": {c.campaign_id: baseline.score(c) for c in campaigns}}
    scores.update(_external_scores(store, "test", sample))
    report = _report(
        "test", campaigns, scores, float(frozen["config"].get("margin", 0.0)), _calibrations(store, scores)
    )
    report["config_hash"] = config_hash
    store.write_json(f"validation/test-report-{config_hash[:12]}.json", report)
    _log(store, "completed", "test", config_hash)
    return report
