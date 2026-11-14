"""Aggregate models trained only before the declared cutoff; no individual pseudo-labels."""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.special import expit, logit
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .context import market_reference_date
from .delivery import allocate_spend, impressions_from

CATEGORICAL = ["vertical", "adset_id", "leva", "formato", "weekday"]
NUMERIC = ["log_budget", "age_days", "history_logit", "history_log_cpm", "market_ctr", "market_cpm"]


def residual_components(dates, residuals):
    frame = pd.DataFrame(residuals)
    frame["date"] = np.asarray(dates)
    grouped = frame.groupby("date")
    daily = grouped[[0, 1, 2]].mean().to_numpy()
    within = frame[[0, 1]].to_numpy() - grouped[[0, 1]].transform("mean").to_numpy()
    return daily, np.sqrt(np.mean(within**2, axis=0))


def build_features(kit: dict, rows: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    hist = kit["history"].loc[kit["history"].data <= as_of_date]
    if hist.empty:
        raise ValueError("Training vuoto al cutoff richiesto")
    frame = rows.reset_index(drop=True).copy()
    result = frame[["vertical", "adset_id", "leva", "formato"]].astype(str).copy()
    result["weekday"] = pd.to_datetime(frame.data).dt.dayofweek.astype(str)
    result["log_budget"] = np.log1p(frame.budget_giornaliero_adset.astype(float))
    launch = frame.asset_id.map(kit["assets"].set_index("asset_id").data_lancio)
    launch = launch.fillna(as_of_date)
    result["age_days"] = (pd.to_datetime(frame.data) - pd.to_datetime(launch)).dt.days.clip(lower=0)
    global_p = (hist.click.sum() + 1) / (hist.impression.sum() + 100)
    global_cpm = 1000 * hist.spesa.sum() / hist.impression.sum()
    base_p = np.full(len(frame), global_p)
    base_cpm = np.full(len(frame), global_cpm)
    for key, strength in [("vertical", 50000), ("adset_id", 20000), ("ad_id", 10000)]:
        sums = hist.groupby(key)[["click", "impression", "spesa"]].sum()
        clicks = frame[key].map(sums.click).to_numpy(dtype=float)
        impressions = frame[key].map(sums.impression).to_numpy(dtype=float)
        spend = frame[key].map(sums.spesa).to_numpy(dtype=float)
        known = np.isfinite(impressions)
        base_p[known] = (clicks[known] + strength * base_p[known]) / (impressions[known] + strength)
        base_cpm[known] = (1000 * spend[known] + strength * base_cpm[known]) / (impressions[known] + strength)
    result["history_logit"] = logit(np.clip(base_p, 1e-7, 1 - 1e-7))
    result["history_log_cpm"] = np.log(np.maximum(base_cpm, 0.1))
    weekly = kit["weekly_market"]
    # shortcut: transfer 2025 seasonality by Black-Friday distance; validate when 2026 market labels arrive.
    mapped = pd.to_datetime(frame.data.map(market_reference_date))
    mondays = mapped - pd.to_timedelta(mapped.dt.dayofweek, unit="D")
    for source, dest in [("indice_ctr", "market_ctr"), ("indice_cpm", "market_cpm")]:
        index = weekly.set_index(["vertical", "settimana_dal"])[source]
        result[dest] = [
            np.log(max(float(index.get((v, day.strftime("%Y-%m-%d")), 100)), 1) / 100)
            for v, day in zip(frame.vertical, mondays)
        ]
    return result[CATEGORICAL + NUMERIC]


@dataclass
class ForecastModels:
    cutoff: str
    preprocessor: object
    ctr_coefficients: np.ndarray
    cpm_model: object
    utilization: dict
    allocation: dict
    known_ads: set
    ctr_model: str = "glm_binomial"
    version: str = "aggregate-v4"
    row_noise_scale: tuple = (0.12, 0.08)
    recipe: dict = field(default_factory=dict)
    calibration_residuals: np.ndarray = field(default_factory=lambda: np.array([[0.25, 0.15, 0.05]]))

    @classmethod
    def fit(cls, kit: dict, cutoff: str = "2026-11-01"):
        train = kit["history"].loc[kit["history"].data <= cutoff].copy()
        if len(train) < 20:
            raise ValueError("Almeno 20 righe storiche richieste")
        # In-time training history excludes each row's own day, including aggregate features.
        parts = []
        for day, indices in train.groupby("data", sort=True).groups.items():
            previous = (date.fromisoformat(str(day)) - timedelta(days=1)).isoformat()
            if (kit["history"].data <= previous).any():
                x = build_features(kit, train.loc[indices], previous)
                x.index = indices
                parts.append(x)
        features = pd.concat(parts).sort_index()
        train = train.loc[features.index]
        pre = ColumnTransformer(
            [
                ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
                ("num", StandardScaler(), NUMERIC),
            ]
        )
        x = sm.add_constant(pre.fit_transform(features), has_constant="add")
        y = np.column_stack([train.click, train.impression - train.click])
        fitted = sm.GLM(y, x, family=sm.families.Binomial()).fit_regularized(
            alpha=1.0, L1_wt=0.0, maxiter=250
        )
        cpm = Ridge(alpha=20).fit(
            x, np.log(train.cpm.clip(lower=0.1)), sample_weight=train.impression / train.impression.mean()
        )
        daily = train.groupby(["data", "adset_id"]).agg(
            spend=("spesa", "sum"), budget=("budget_giornaliero_adset", "first")
        )
        daily = daily.loc[daily.spend <= daily.budget + 0.02]
        utilization = (
            (daily.spend / daily.budget.clip(lower=0.01)).clip(0, 1).groupby("adset_id").median().to_dict()
        )
        allocation = (
            train.loc[~((train.data == "2026-10-21") & (train.adset_id == "FGR-AS1"))]
            .groupby("ad_id")
            .spesa.mean()
            .to_dict()
        )
        model = cls(cutoff, pre, np.asarray(fitted.params), cpm, utilization, allocation, set(train.ad_id))
        pred = expit(x @ model.ctr_coefficients)
        residual = np.column_stack(
            [
                logit(
                    np.clip(
                        (train.click.to_numpy() + 0.5) / (train.impression.to_numpy() + 1), 1e-6, 1 - 1e-6
                    )
                )
                - logit(np.clip(pred, 1e-6, 1 - 1e-6)),
                np.log(train.cpm.to_numpy()) - cpm.predict(x),
                np.zeros(len(train)),
            ]
        )
        day_res, noise = residual_components(train.data, residual)
        # Training residuals alone understate transfer uncertainty; retain a declared weak scenario floor.
        model.calibration_residuals = day_res
        model.row_noise_scale = tuple(np.maximum(noise, [0.12, 0.08]))
        return model

    def predict(self, kit, rows):
        features = build_features(kit, rows, self.cutoff)
        x = sm.add_constant(self.preprocessor.transform(features), has_constant="add")
        p = expit(x @ self.ctr_coefficients)
        if self.ctr_model == "hierarchical_smoothing":
            p = expit(features.history_logit.to_numpy())
        p = np.clip(p, 1e-7, 1 - 1e-7)
        cpm = np.exp(np.clip(self.cpm_model.predict(x), -2, 8))
        return p, cpm


def forecast(kit, models, rows, seed=42, n_draws=1000):
    rows = rows.reset_index(drop=True)
    p, cpm = models.predict(kit, rows)
    rng = np.random.default_rng(seed)
    n = len(rows)
    residuals = models.calibration_residuals
    picked = residuals[rng.integers(0, len(residuals), size=n_draws)]
    # Common draws retain day-level dependence across creatives; row noise captures cold-start uncertainty.
    cold = ~rows.ad_id.isin(models.known_ads).to_numpy()
    ctr_noise = picked[:, 0, None] + rng.normal(0, models.row_noise_scale[0] + 0.22 * cold, (n_draws, n))
    cpm_noise = picked[:, 1, None] + rng.normal(0, models.row_noise_scale[1] + 0.12 * cold, (n_draws, n))
    p_draw = expit(logit(p)[None, :] + ctr_noise)
    cpm_draw = cpm[None, :] * np.exp(cpm_noise)
    spend = allocate_spend(rows, models, rng, n_draws)
    impressions = impressions_from(spend, cpm_draw)
    clicks = impressions * p_draw
    result = []
    for i, row in rows.iterrows():
        ei, ec, es = float(impressions[:, i].mean()), float(clicks[:, i].mean()), float(spend[:, i].mean())
        predicted_p = ec / ei if ei else float(p_draw[:, i].mean())
        result.append(
            {
                "row_index": int(row.get("row_index", i)),
                "date": row.data,
                "ad_id": row.ad_id,
                "asset_id": row.asset_id,
                "adset_id": row.adset_id,
                "campaign_id": row.campaign_id,
                "vertical": row.vertical,
                "lever": row.leva,
                "format": row.formato,
                "ctr_pred": 100 * predicted_p,
                "cpm_pred": 1000 * es / ei if ei else float(cpm_draw[:, i].mean()),
                "ctr_interval": np.quantile(p_draw[:, i] * 100, [0.05, 0.95]).tolist(),
                "cpm_interval": np.quantile(cpm_draw[:, i], [0.05, 0.95]).tolist(),
                "expected_impressions": ei,
                "expected_clicks": ec,
                "expected_spend": es,
                "cold_start": bool(cold[i]),
                "confidence_status": "extrapolation"
                if cold[i] or row.leva == "black_friday"
                else "unvalidated",
                "evidence_level": "modeled_assumption",
                "model_version": models.version,
                "training_cutoff": models.cutoff,
                "assumptions": [
                    "country_IT_assumed",
                    "2025_seasonality_transfer",
                    "training_residual_uncertainty",
                ],
                "quality_flags": ["no_delivery"] if not ei else [],
            }
        )
    return result, {
        "p": p_draw,
        "cpm": cpm_draw,
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
    }


def forecast_new_campaign(kit, models, rows, seed=42, n_draws=1000):
    """New brief labels cannot reference historical ads or adsets, including imported datasets."""
    scoped = rows.reset_index(drop=True).copy()
    for column, known in [("ad_id", models.known_ads), ("adset_id", models.utilization)]:
        public = scoped[column].astype(str)
        reserved = set(kit["history"][column]) | set(known)
        prefix = "user-brief:"
        while any(prefix + value in reserved for value in public):
            prefix = "_" + prefix
        scoped[column] = prefix + public
    predictions, draws = forecast(kit, models, scoped, seed=seed, n_draws=n_draws)
    for prediction, (_, row) in zip(predictions, rows.iterrows()):
        prediction["ad_id"], prediction["adset_id"] = row.ad_id, row.adset_id
    return predictions, draws


def validate_models(kit, models, n_draws=1000):
    val = (
        kit["history"]
        .loc[(kit["history"].data > models.cutoff) & (kit["history"].data <= "2026-11-15")]
        .reset_index(drop=True)
    )
    predicted, draws = forecast(kit, models, val, n_draws=n_draws)
    phat = np.array([r["ctr_pred"] / 100 for r in predicted])
    actual = val.click.to_numpy() / val.impression.to_numpy()
    weights = val.impression.to_numpy()
    eps = 1e-12

    def loss(pp):
        return float(
            -np.sum(
                val.click * np.log(np.clip(pp, eps, 1 - eps))
                + (val.impression - val.click) * np.log(np.clip(1 - pp, eps, 1 - eps))
            )
            / weights.sum()
        )

    smooth = expit(build_features(kit, val, models.cutoff).history_logit.to_numpy())
    cpm_hat = np.array([r["cpm_pred"] for r in predicted])
    lo, hi = np.quantile(draws["p"], [0.05, 0.95], axis=0)
    c_lo, c_hi = np.quantile(draws["cpm"], [0.05, 0.95], axis=0)
    metrics = {
        "training_rows": int((kit["history"].data <= models.cutoff).sum()),
        "validation_rows": len(val),
        "training_cutoff": models.cutoff,
        "validation_from": "2026-11-02",
        "validation_to": "2026-11-15",
        "future_test_score": None,
        "age_accuracy": None,
        "binomial_log_loss": loss(phat),
        "baseline_log_loss": loss(smooth),
        "ctr_weighted_mae_pp": float(np.average(abs(actual - phat) * 100, weights=weights)),
        "baseline_ctr_weighted_mae_pp": float(np.average(abs(actual - smooth) * 100, weights=weights)),
        "cpm_mae_eur": float(abs(val.cpm.to_numpy() - cpm_hat).mean()),
        "ctr_coverage_90": float(np.mean((actual >= lo) & (actual <= hi))),
        "cpm_coverage_90": float(np.mean((val.cpm.to_numpy() >= c_lo) & (val.cpm.to_numpy() <= c_hi))),
        "interval_method": "training_day_residual_bootstrap_plus_declared_transfer_prior",
        "selection_limit": "Validation used for candidate comparison; not an independent future test.",
        "ablation": {"baseline": "measured", "llm_without_persona": "not_run", "individual_panel": "not_run"},
    }
    metrics["status"] = (
        "validated_on_validation"
        if 0.85 <= metrics["ctr_coverage_90"] <= 0.98 and loss(phat) <= loss(smooth)
        else "unvalidated"
    )
    return metrics


def train_model_registry(kit):
    folds = [("2026-09-20", "2026-10-04"), ("2026-10-04", "2026-10-18"), ("2026-10-18", "2026-11-01")]
    residuals, fold_reports = [], []
    noise_sums = np.zeros(2)
    noise_count = 0
    for cutoff, end in folds:
        model = ForecastModels.fit(kit, cutoff=cutoff)
        rows = kit["history"].loc[(kit["history"].data > cutoff) & (kit["history"].data <= end)]
        p, cpm = model.predict(kit, rows)
        observed = (rows.click.to_numpy() + 0.5) / (rows.impression.to_numpy() + 1)
        residual = pd.DataFrame(
            {
                "ctr": logit(observed) - logit(p),
                "cpm": np.log(rows.cpm.to_numpy() / cpm),
                "delivery": np.zeros(len(rows)),
                "date": rows.data.to_numpy(),
            }
        )
        daily, noise = residual_components(rows.data, residual[["ctr", "cpm", "delivery"]].to_numpy())
        residuals.extend(daily.tolist())
        noise_sums += len(rows) * noise**2
        noise_count += len(rows)
        fold_reports.append({"training_cutoff": cutoff, "validation_end": end, "rows": len(rows)})
    final = ForecastModels.fit(kit)
    val = kit["history"].loc[(kit["history"].data > final.cutoff) & (kit["history"].data <= "2026-11-15")]
    p_glm, _ = final.predict(kit, val)
    p_smooth = expit(build_features(kit, val, final.cutoff).history_logit.to_numpy())

    def loss(p):
        return float(
            -np.sum(
                val.click * np.log(np.clip(p, 1e-9, 1 - 1e-9))
                + (val.impression - val.click) * np.log(np.clip(1 - p, 1e-9, 1 - 1e-9))
            )
            / val.impression.sum()
        )

    losses = {"glm_binomial": loss(p_glm), "hierarchical_smoothing": loss(p_smooth)}
    final.ctr_model = min(losses, key=losses.get)
    if final.ctr_model == "hierarchical_smoothing":
        ctr_errors = []
        noise_sums[0] = 0
        for cutoff, end in folds:
            rows = kit["history"].loc[(kit["history"].data > cutoff) & (kit["history"].data <= end)]
            features = build_features(kit, rows, cutoff)
            observed = (rows.click.to_numpy() + 0.5) / (rows.impression.to_numpy() + 1)
            errors = pd.DataFrame(
                {"ctr": logit(observed) - features.history_logit.to_numpy(), "date": rows.data.to_numpy()}
            )
            ctr_errors.extend(errors.groupby("date").ctr.mean().tolist())
            within = errors.ctr - errors.groupby("date").ctr.transform("mean")
            noise_sums[0] += float(np.sum(within**2))
        for row, error in zip(residuals, ctr_errors):
            row[0] = error
    final.calibration_residuals = np.asarray(residuals)
    final.row_noise_scale = tuple(np.maximum(np.sqrt(noise_sums / noise_count), [0.12, 0.08]))
    final.recipe = {
        "inner_folds": fold_reports,
        "calibration_cutoff": "2026-11-01",
        "within_day_noise_std": list(final.row_noise_scale),
        "selection_period": "2026-11-02..2026-11-15",
        "selection_limit": "Validation used for selection, not an independent test",
        "selection": {
            "model": final.ctr_model,
            "selected_log_loss": min(losses.values()),
            "other_log_loss": max(losses.values()),
        },
    }
    return final


def validate_new_campaigns(kit, n_draws=100):
    """Leave whole adsets out of training; score future dates through the new-brief path."""
    from .agents import policy_key

    history = kit["history"]
    validation = history.loc[(history.data > "2026-11-01") & (history.data <= "2026-11-15")]
    if validation.empty:
        raise ValueError("Nessuna osservazione per la verifica cold start")
    folds, errors, weights = [], [], []
    for adset, actual in validation.groupby("adset_id", sort=True):
        restricted = {**kit, "history": history.loc[history.adset_id != adset].copy()}
        # Fixed GLM recipe; do not select its algorithm using the held-out outcomes.
        model = ForecastModels.fit(restricted, cutoff="2026-11-01")
        rows = actual.copy()
        rows["adset_id"] = "user-adset"
        rows["campaign_id"] = "user-campaign"
        rows["asset_id"] = "new-" + rows.asset_id.astype(str)
        assets = rows[["asset_id"]].drop_duplicates().assign(data_lancio=str(rows.data.min()))
        original_assets = restricted["assets"].loc[~restricted["assets"].asset_id.isin(assets.asset_id)]
        scenario_kit = {**restricted, "assets": pd.concat([original_assets, assets], ignore_index=True)}
        predictions, _ = forecast_new_campaign(scenario_kit, model, rows, n_draws=n_draws)
        expected = np.array([r["ctr_pred"] / 100 for r in predictions])
        observed = actual.click.to_numpy() / actual.impression.to_numpy()
        w = actual.impression.to_numpy()
        error = abs(expected - observed) * 100
        errors.extend(error.tolist())
        weights.extend(w.tolist())
        folds.append(
            {
                "held_out_adset": str(adset),
                "training_cutoff": model.cutoff,
                "training_adsets": sorted(
                    restricted["history"]
                    .loc[restricted["history"].data <= model.cutoff, "adset_id"]
                    .unique()
                    .tolist()
                ),
                "validation_rows": len(actual),
                "all_rows_cold_start": all(r["cold_start"] for r in predictions),
                "ctr_weighted_mae_pp": float(np.average(error, weights=w)),
                "cpm_mae_eur": float(
                    np.mean(abs(actual.cpm.to_numpy() - np.array([r["cpm_pred"] for r in predictions])))
                ),
                "forecast_hash": policy_key(predictions),
            }
        )
    return {
        "source_type": "simulated_kit",
        "certified": False,
        "validation_rows": len(validation),
        "model_recipe": "glm_binomial_fixed_no_validation_selection",
        "folds": folds,
        "ctr_weighted_mae_pp": float(np.average(errors, weights=weights)),
        "agents_evaluated": False,
        "age_accuracy": None,
        "limitations": [
            "Synthetic kit outcomes do not establish real marketing accuracy",
            "Entire adset removed; other adsets of the same brand can remain in training",
            "Fixed GLM baseline, not the validation-selected production candidate",
            "New asset IDs and user-adset path reproduce missing delivery history",
            "No test of content sensitivity or added predictive value of LLM responses",
        ],
    }
