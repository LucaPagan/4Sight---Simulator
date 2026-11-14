"""Optional, resumable LLM ablation. Outcomes never enter a consumer prompt."""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.special import expit
from sklearn.preprocessing import StandardScaler

from .agents import PROMPT_VERSION, evaluation_plan, policy_key
from .audience import generate_population
from .forecasting import build_features
from .schemas import AGES, CampaignBrief, Creative

SCORES = ["clarity", "interest", "credibility", "friction"]


def metrics(rows, probabilities):
    p = np.clip(np.asarray(probabilities), 1e-9, 1 - 1e-9)
    observed = rows.click.to_numpy() / rows.impression.to_numpy()
    n = rows.impression.to_numpy()
    logloss = -np.sum(n * (observed * np.log(p) + (1 - observed) * np.log1p(-p))) / n.sum()
    saturated = np.clip(observed, 1e-9, 1 - 1e-9)
    deviance = 2 * np.sum(
        n * (observed * np.log(saturated / p) + (1 - observed) * np.log((1 - saturated) / (1 - p)))
    )
    return {
        "binomial_deviance": float(deviance),
        "weighted_ctr_mae_pp": float(np.average(abs(observed - p) * 100, weights=n)),
        "binomial_logloss": float(logloss),
    }


def compare_ablation(rows, candidates):
    results = {name: metrics(rows, values) for name, values in candidates.items()}
    baseline = results["baseline"]
    for name, result in results.items():
        result["promotion_gate"] = (
            name != "baseline"
            and result["binomial_deviance"] <= baseline["binomial_deviance"] * 0.98
            and result["weighted_ctr_mae_pp"] <= baseline["weighted_ctr_mae_pp"] * 1.02
        )
    return results


def run_ablation(service, client=None):
    client = client or service.client()
    runtime = client.status()
    if not runtime["ready"]:
        raise ValueError("Ollama non pronto per l'ablation")
    kit = service.ensure_kit()
    descriptors = {"llm_without_persona": {}, "individual_panel": {}}
    attempts = 0
    required = len(kit["assets"]) * 121
    for _, asset in kit["assets"].iterrows():
        brief = CampaignBrief(
            name="Ablation",
            brand=str(asset.asset_id).split("-")[0],
            product_description=f"{asset.headline}. {asset.testo_principale}",
            vertical=asset.vertical,
            date_from="2026-11-16",
            date_to="2026-11-16",
            creatives=[
                Creative(
                    id=asset.asset_id,
                    headline=asset.headline,
                    primary_text=asset.testo_principale,
                    visual_description=asset.descrizione_visual,
                    lever=asset.leva,
                    format=asset.formato,
                )
            ],
        )
        profiles = generate_population(brief)
        neutral = {"agent_id": "no-persona", "category_context": brief.product_description}
        work = evaluation_plan(brief, [neutral, *profiles], runtime["digest"])
        evaluations = []
        for item in work:
            cached = service.repo.get_policy(item["key"])
            if cached is None:
                if attempts >= service.cfg.max_evaluations:
                    return {
                        "status": "partial",
                        "required_policies": required,
                        "new_attempts": attempts,
                        "message": "Rieseguire ablation per usare la cache e completare le mancanti",
                    }
                attempts += 1
                response = client.evaluate(item["input"])
                service.repo.save_policy(
                    policy_key(item["input"]),
                    {
                        "input": item["input"],
                        "response": response["evaluation"],
                        "digest": runtime["digest"],
                        "metrics": {k: v for k, v in response.items() if k != "evaluation"},
                    },
                )
                cached = service.repo.get_policy(item["key"])
            evaluations.append(cached["response"])
        descriptors["llm_without_persona"][asset.asset_id] = [evaluations[0][k] for k in SCORES]
        panel = evaluations[1:]
        descriptors["individual_panel"][asset.asset_id] = [
            float(np.mean([e[k] for e, p in zip(panel, profiles) if p["age_band"] == band]))
            for band in AGES
            for k in SCORES
        ]
    history = kit["history"]
    train = history.loc[history.data <= "2026-11-01"]
    parts = []
    for day, ids in train.groupby("data", sort=True).groups.items():
        previous = (pd.Timestamp(day) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if (history.data <= previous).any():
            values = build_features(kit, train.loc[ids], previous)
            values.index = ids
            parts.append(values)
    features = pd.concat(parts).sort_index()
    train = train.loc[features.index]
    validation = history.loc[(history.data >= "2026-11-02") & (history.data <= "2026-11-15")]
    model = service.get_models()
    train_base = model.preprocessor.transform(features)
    val_base = model.preprocessor.transform(build_features(kit, validation, "2026-11-01"))
    predictions = {"baseline": model.predict(kit, validation)[0]}
    for name, values in descriptors.items():
        scaler = StandardScaler()
        a = scaler.fit_transform(np.array([values[x] for x in train.asset_id]))
        b = scaler.transform(np.array([values[x] for x in validation.asset_id]))
        x = sm.add_constant(np.column_stack([train_base, a]), has_constant="add")
        fit = sm.GLM(
            np.column_stack([train.click, train.impression - train.click]), x, family=sm.families.Binomial()
        ).fit_regularized(alpha=1.0, L1_wt=0.0, maxiter=250)
        predictions[name] = expit(
            sm.add_constant(np.column_stack([val_base, b]), has_constant="add") @ fit.params
        )
    report = {
        "status": "complete",
        "dataset_hash": service.import_dataset(service.cfg.data_dir)["id"],
        "model_digest": runtime["digest"],
        "prompt_version": PROMPT_VERSION,
        "training_cutoff": "2026-11-01",
        "validation_rows": len(validation),
        "metrics": compare_ablation(validation, predictions),
        "required_policies": required,
        "new_attempts": attempts,
        "promoted": False,
        "warning": "Confronto sperimentale su validation già usata nella selezione della baseline; nessun test futuro o demografico. Nessuna promozione automatica.",
    }
    service.store.write_json("validation/ablation.json", report)
    service.repo.create("validation_runs", report)
    return report
