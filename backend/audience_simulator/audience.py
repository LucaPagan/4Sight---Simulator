import hashlib

import numpy as np
from scipy.special import expit, logit

from .schemas import AGES, CampaignBrief


def stable_seed(*parts):
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def generate_population(brief: CampaignBrief):
    from . import audience_spec

    context = {
        "beauty_skincare": "routine e familiarità skincare ipotetiche",
        "pet_ecommerce": "animale e necessità ipotetici, non osservati",
        "abbigliamento": "stile e necessità di taglia ipotetici",
    }[brief.vertical]
    marginals = audience_spec.load_marginals()
    if marginals is not None and brief.country in marginals["countries"]:
        spec = audience_spec.build_spec(marginals, brief.country)
        shares = brief.age_shares if "age_shares" in brief.model_fields_set else None
        return audience_spec.generate_profiles_v2(
            brief.seed,
            brief.vertical,
            brief.brand,
            spec,
            brief.population_size,
            shares,
            f"{context}; età e acquisti online da dati Eurostat, tratti ipotetici",
        )
    return generate_profiles(
        brief.seed, brief.vertical, brief.brand, brief.age_shares, context, brief.population_size
    )


def band_sizes(size):
    """Split the panel across the six age bands as evenly as possible (120 -> 20 each)."""
    base, extra = divmod(size, len(AGES))
    return [base + (1 if s < extra else 0) for s in range(len(AGES))]


def generate_profiles(seed, vertical, brand, age_shares, category_context, size=120):
    rng = np.random.default_rng(stable_seed(seed, vertical, brand))
    profiles = []
    sizes = band_sizes(size)
    for s, band in enumerate(AGES):
        for j in range(sizes[s]):
            traits = rng.beta(2, 2, 7)
            profiles.append(
                {
                    "agent_id": f"synthetic-{s + 1}-{j + 1:03d}",
                    "age_band": band,
                    "population_weight": age_shares[s] / sizes[s],
                    **dict(
                        zip(
                            [
                                "category_affinity",
                                "budget_sensitivity",
                                "purchase_need",
                                "brand_familiarity",
                                "advertising_literacy",
                                "trust",
                                "repeat_tolerance",
                            ],
                            map(float, traits),
                        )
                    ),
                    "category_context": category_context,
                    "profile_version": "profiles-v1",
                    "assumption_id": "weak-beta-traits-v1",
                    "seed": seed,
                    "evidence_level": "modeled_assumption",
                }
            )
    return profiles


def reconcile_age_ctr(p_base, q, delta):
    q, delta = np.asarray(q, float), np.asarray(delta, float)
    if (
        q.shape != delta.shape
        or q.shape[-1] < 1
        or not np.isfinite(q).all()
        or not np.isfinite(delta).all()
        or (q < 0).any()
        or not np.allclose(q.sum(axis=-1), 1, atol=1e-12)
    ):
        raise ValueError("Quote e delta non validi")
    p = np.asarray(p_base, float)
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Probabilità baseline non valida")
    midpoint = logit(np.clip(p, 1e-15, 1 - 1e-15))
    lower = midpoint - np.max(np.where(q > 0, delta, -np.inf), axis=-1)
    upper = midpoint - np.min(np.where(q > 0, delta, np.inf), axis=-1)
    for _ in range(64):
        b = (lower + upper) / 2
        weighted = (q * expit(np.expand_dims(b, -1) + delta)).sum(axis=-1)
        lower = np.where(weighted < p, b, lower)
        upper = np.where(weighted >= p, b, upper)
    result = expit(np.expand_dims((lower + upper) / 2, -1) + delta)
    return np.where(np.expand_dims(p == 0, -1), 0, np.where(np.expand_dims(p == 1, -1), 1, result))


def age_predictions(
    draws, seed=42, shares=None, effects=None, strength=1.0, scenario="central", signal_effects=None
):
    rng = np.random.default_rng(seed)
    p = draws["p"]
    d, n = p.shape
    shares = np.asarray(shares if shares is not None else [1 / 6] * 6, float)
    effects = np.asarray(effects if effects is not None else [-0.2, -0.1, 0, 0.05, 0.2, 0.05], float)
    if np.any(shares < 0) or not np.isclose(shares.sum(), 1):
        raise ValueError("Quote non valide")
    q = np.zeros((d, 6))
    active = shares > 0
    q[:, active] = rng.dirichlet(shares[active] * 60, size=d)
    sigma = {"conservative": 0.15, "central": 0.35, "exploratory": 0.7}[scenario]
    # Common draws across creatives preserve paired age comparisons; all effects remain assumptions.
    common = rng.normal(0, sigma, (d, 6))
    output = []
    for i in range(n):
        mu = effects + (signal_effects[i] if signal_effects is not None else np.zeros(6))
        delta = strength * (common + mu)
        ps = reconcile_age_ctr(p[:, i], q, delta)
        impr = draws["impressions"][:, i, None] * q
        clicks = impr * ps
        spend = draws["spend"][:, i, None] * q
        total_i = float(draws["impressions"][:, i].mean())
        records = []
        for s, band in enumerate(AGES):
            ei, ec = float(impr[:, s].mean()), float(clicks[:, s].mean())
            records.append(
                {
                    "age_band": band,
                    "impression_share": ei / total_i if total_i else float(q[:, s].mean()),
                    "expected_impressions": ei,
                    "clicks_estimate": ec,
                    "expected_spend": float(spend[:, s].mean()),
                    "ctr_estimate": 100 * ec / ei if ei else float(ps[:, s].mean() * 100),
                    "ctr_range": np.quantile(ps[:, s] * 100, [0.05, 0.95]).tolist(),
                    "cpm_pred": None,
                    "evidence_level": "modeled_assumption",
                    "audience_mode": "theory_based",
                    "confidence_status": "unvalidated",
                    "age_sensitivity": strength,
                    "scenario_id": scenario,
                    "prior_version": "age-priors-v1",
                    "assumptions": [
                        "weak_age_logodds_prior",
                        "impression_share_assumed",
                        "age_neutral_cost_v1",
                    ],
                    "not_reached_in_scenario": not bool(shares[s]),
                    "reason": "Scenario condizionale a prior, creatività e contesto; non accuratezza demografica misurata.",
                }
            )
        output.append(records)
    return output
