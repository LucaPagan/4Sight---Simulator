"""Learn how panel assessments relate to relative CTR, and let them move KPIs only if that relation holds.

The model is relative by construction: it regresses the observed log-odds difference of CTR between two
creatives of the same campaign on the difference of their panel features. It carries no absolute level,
so it cannot change a campaign's baseline CTR, only how creatives sit relative to each other. A gate on
out-of-fold loss decides whether the panel may move KPIs at all; if it fails, the shift is exactly zero.
"""

import hashlib
import itertools

import numpy as np
from scipy.special import expit, logit

FEATURES = [
    "interest",
    "clarity",
    "credibility",
    "friction",
    "consider_click_share",
    "not_interested_share",
]
SCORED = ("interest", "clarity", "credibility", "friction")
TAU2 = 0.02  # extra between-creative variance so very large samples do not get unlimited weight


def creative_features(records):
    """Weighted panel features for one creative. records: {input: {profile: {...}}, evaluation: {...}}."""
    weights = np.array([float(r["input"]["profile"].get("population_weight", 1.0)) for r in records], float)
    if weights.sum() <= 0:
        raise ValueError("Pesi del panel non validi")
    weights /= weights.sum()
    evaluations = [r["evaluation"] for r in records]
    result = {n: float(weights @ [(e[n] - 2) / 2 for e in evaluations]) for n in SCORED}
    for name, action in (
        ("consider_click_share", "consider_click"),
        ("not_interested_share", "not_interested"),
    ):
        result[name] = float(weights @ [float(e["conditional_action"] == action) for e in evaluations])
    return result


def _vector(features):
    return np.array([features[name] for name in FEATURES], float)


def _smoothed_logit(clicks, impressions):
    return float(logit((clicks + 0.5) / (impressions + 1)))


def _pairs(campaigns, features):
    rows = []
    for campaign in campaigns:
        feats = features.get(campaign.campaign_id, {})
        for a, b in itertools.combinations(sorted(campaign.observations), 2):
            if a not in feats or b not in feats:
                continue
            oa, ob = campaign.observations[a], campaign.observations[b]
            variance = (
                1 / (oa.clicks + 0.5)
                + 1 / (oa.impressions - oa.clicks + 0.5)
                + 1 / (ob.clicks + 0.5)
                + 1 / (ob.impressions - ob.clicks + 0.5)
            )
            rows.append(
                {
                    "campaign_id": campaign.campaign_id,
                    "a": a,
                    "b": b,
                    "x": _vector(feats[a]) - _vector(feats[b]),
                    "y": _smoothed_logit(oa.clicks, oa.impressions)
                    - _smoothed_logit(ob.clicks, ob.impressions),
                    "w": 1 / (variance + TAU2),
                }
            )
    return rows


def _ridge(x, y, w, alpha):
    scale = np.sqrt(np.average(x**2, axis=0, weights=w))
    scale[scale == 0] = 1.0
    z = x / scale
    gram = z.T @ (z * w[:, None]) + alpha * np.eye(z.shape[1])
    coef = np.linalg.solve(gram, z.T @ (w * y))
    return coef / scale


def _fold(campaign_id, folds):
    return int(hashlib.sha256(campaign_id.encode()).hexdigest()[:8], 16) % folds


def _out_of_fold(rows, alpha, folds):
    ids = np.array([_fold(r["campaign_id"], folds) for r in rows])
    x, y, w = (np.array([r[k] for r in rows]) for k in ("x", "y", "w"))
    prediction = np.zeros(len(rows))
    for k in range(folds):
        train, test = ids != k, ids == k
        if train.sum() < 5 or not test.any():
            continue
        prediction[test] = x[test] @ _ridge(x[train], y[train], w[train], alpha)
    return prediction


def fit_calibration(
    campaigns, features, folds=5, alphas=(1.0, 10.0, 100.0, 1000.0), n_boot=1000, seed=0, min_pairs=30
):
    rows = _pairs(campaigns, features)
    if len(rows) < min_pairs:
        raise ValueError(f"Servono almeno {min_pairs} coppie con feature del panel (trovate {len(rows)})")
    x, y, w = (np.array([r[k] for r in rows]) for k in ("x", "y", "w"))
    best = min(
        ((alpha, _out_of_fold(rows, alpha, folds)) for alpha in alphas),
        key=lambda item: float(np.sum(w * (y - item[1]) ** 2)),
    )
    alpha, oof = best
    denominator = float(np.sum(w * oof**2))
    scale = float(np.clip(np.sum(w * y * oof) / denominator, 0, 1)) if denominator > 0 else 0.0
    null_loss = w * y**2
    model_loss = w * (y - scale * oof) ** 2
    ids = sorted({r["campaign_id"] for r in rows})
    index = {c: i for i, c in enumerate(ids)}
    per_null, per_model = np.zeros(len(ids)), np.zeros(len(ids))
    for r, n0, n1 in zip(rows, null_loss, model_loss, strict=True):
        per_null[index[r["campaign_id"]]] += n0
        per_model[index[r["campaign_id"]]] += n1
    rng = np.random.default_rng(seed)
    gains = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(ids), len(ids))
        gains.append(1 - per_model[pick].sum() / per_null[pick].sum())
    low, high = np.percentile(gains, [2.5, 97.5])
    improvement = 1 - per_model.sum() / per_null.sum()
    passed = bool(low > 0 and scale > 0)
    coef = _ridge(x, y, w, alpha)
    scores = _relative_scores(rows, oof)
    residuals = np.abs(y - scale * oof)
    level = 0.9
    rank = min(1.0, np.ceil((len(residuals) + 1) * level) / len(residuals))
    conformal_q = float(np.quantile(residuals, rank, method="higher"))
    artifact = {
        "version": "calibration-v1",
        "features": FEATURES,
        "weights": {n: float(c) for n, c in zip(FEATURES, coef, strict=True)},
        "alpha": alpha,
        "beta": scale if passed else 0.0,
        "pairs": len(rows),
        "campaigns": len(ids),
        "conformal": {
            "level": level,
            "quantile": conformal_q,
            "pairs": len(residuals),
            "method": "split conformal sui residui fuori campione, in log-odds di CTR relativo",
            "caveat": "Le coppie della stessa campagna sono correlate: la copertura va verificata sul test.",
        },
        "gate": {
            "passed": passed,
            "out_of_fold_scale": scale,
            "loss_improvement": float(improvement),
            "improvement_ci95": [float(low), float(high)],
            "rule": "ci95 inferiore del miglioramento fuori campione > 0 e scala > 0",
        },
    }
    return artifact, scores


def _relative_scores(rows, prediction):
    """Per-arm out-of-fold scores: least-squares arm effects reproducing the pairwise predictions."""
    scores = {}
    for campaign_id in sorted({r["campaign_id"] for r in rows}):
        items = [(r, p) for r, p in zip(rows, prediction, strict=True) if r["campaign_id"] == campaign_id]
        arms = sorted({a for r, _ in items for a in (r["a"], r["b"])})
        design = np.zeros((len(items), len(arms)))
        for i, (r, _) in enumerate(items):
            design[i, arms.index(r["a"])], design[i, arms.index(r["b"])] = 1, -1
        solution = np.linalg.lstsq(design, np.array([p for _, p in items]), rcond=None)[0]
        solution -= solution.mean()
        scores[campaign_id] = {a: float(s) for a, s in zip(arms, solution, strict=True)}
    return scores


def shifts_for(artifact, features_by_creative):
    """Log-odds CTR shift per creative of one brief: beta * w . (features - mean over the brief)."""
    ids = list(features_by_creative)
    if len(ids) < 2 or not artifact.get("beta"):
        return dict.fromkeys(ids, 0.0)
    matrix = np.array([_vector(features_by_creative[i]) for i in ids])
    weights = np.array([artifact["weights"][n] for n in FEATURES])
    raw = (matrix - matrix.mean(axis=0)) @ weights * float(artifact["beta"])
    return {i: float(v) for i, v in zip(ids, raw, strict=True)}


def apply_ctr_shifts(predictions, draws, shifts, assumption="panel_ctr_shift_calibrated"):
    """Shift CTR draws per creative. Impressions, CPM and spend (delivery) are never touched."""
    if not any(abs(s) > 0 for s in shifts.values()):
        return predictions, draws
    for i, row in enumerate(predictions):
        shift = shifts.get(row["ad_id"], 0.0)
        if not shift:
            continue
        draws["p"][:, i] = expit(logit(np.clip(draws["p"][:, i], 1e-9, 1 - 1e-9)) + shift)
        draws["clicks"][:, i] = draws["impressions"][:, i] * draws["p"][:, i]
        impressions, clicks = float(draws["impressions"][:, i].mean()), float(draws["clicks"][:, i].mean())
        row["ctr_pred"] = 100 * clicks / impressions if impressions else float(draws["p"][:, i].mean() * 100)
        row["expected_clicks"] = clicks
        if "ctr_interval" in row:
            row["ctr_interval"] = np.quantile(draws["p"][:, i] * 100, [0.05, 0.95]).tolist()
        row["assumptions"] = [*row.get("assumptions", []), assumption]
    return predictions, draws
