"""Stage 1 of persona generation: statistical skeletons conditioned on the Meta-style targeting.

Pipeline (all deterministic given the seed):
1. A large pool of people is sampled from a base population (age mix and online shopping from Eurostat when
   available). Attributes are drawn conditionally (age -> urbanicity -> household -> children -> pets ...) and the
   seven legacy behavioural traits through a Gaussian copula with declared correlations.
2. Every person gets a *reach weight*: how likely Meta would be to deliver the ad to them given age, gender,
   placements, devices and detailed targeting terms. Terms act on the attributes listed in
   ``meta_catalog.DETAILED_TERMS[...]["match"]``; a person's relative reach is match[value] / base_rate[value], so
   the reached population reproduces the declared precision (leakage) instead of being a perfect audience.
3. The panel is drawn per age band by systematic weighted resampling over the pool, so it looks like the people
   the ad would really reach, not like the advertiser's ideal target. Each person is flagged ``in_ideal_target``.

Every conditional table below is a declared assumption (``persona-skeleton-v1``), not a measurement. Only the age
mix of social-network users and online shopping come from Eurostat. Nothing here is validated against delivery.
"""

from typing import Any

import numpy as np
from scipy.stats import beta as beta_dist
from scipy.stats import norm

from .audience import stable_seed
from .meta_catalog import DETAILED_TERMS, MOBILE_ONLY_SURFACES, PERSONA_ATTRIBUTES, PLACEMENTS
from .schemas import AGES, CampaignBrief, TargetingSpec
from .targeting import merge_constraints, read_intent

PROFILE_VERSION = "profiles-v3-targeted"
ASSUMPTION_ID = "persona-skeleton-v1"
METHOD = "importance_resampling_v1"
POOL_PER_BAND = 4000
# Advantage+ audience: share of the detailed-targeting restriction that Meta is assumed to relax.
ADVANTAGE_AUDIENCE_WIDENING = 0.35
AUDIENCE_NETWORK_REACH = 0.5

AGE_RANGES = [(18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 74)]
TRAITS = [
    "category_affinity",
    "budget_sensitivity",
    "purchase_need",
    "brand_familiarity",
    "advertising_literacy",
    "trust",
    "repeat_tolerance",
]
ASSUMED_SHOPPER_EFFECT = {"trust": 0.08, "purchase_need": 0.08}

HOUSEHOLDS = PERSONA_ATTRIBUTES["household"]["values"]  # alone, couple, family, shared
PETS = PERSONA_ATTRIBUTES["pet_species"]["values"]  # dog, cat, other, none
RELATIONSHIPS = PERSONA_ATTRIBUTES["relationship_status"]["values"]  # single, partnered, married
URBANICITIES = PERSONA_ATTRIBUTES["urbanicity"]["values"]  # urban, suburban, rural
SKINCARE = PERSONA_ATTRIBUTES["skincare_routine"]["values"]  # none, basic, extended
OCCUPATIONS = ["student", "employed", "self_employed", "retired", "not_working"]
INCOMES = ["low", "mid", "high"]

# --- Declared assumptions (rows: age band; columns: values in the order of the lists above) -------------------
URBANICITY_BY_BAND = np.array(
    [
        [0.50, 0.30, 0.20],
        [0.48, 0.34, 0.18],
        [0.40, 0.38, 0.22],
        [0.38, 0.38, 0.24],
        [0.36, 0.38, 0.26],
        [0.36, 0.36, 0.28],
    ]
)
HOUSEHOLD_BY_BAND = np.array(
    [
        [0.08, 0.07, 0.05, 0.80],
        [0.20, 0.25, 0.17, 0.38],
        [0.17, 0.20, 0.50, 0.13],
        [0.15, 0.22, 0.50, 0.13],
        [0.20, 0.38, 0.30, 0.12],
        [0.30, 0.50, 0.10, 0.10],
    ]
)
HOUSEHOLD_URBAN_MULT = np.array([[1.3, 1.0, 0.9, 1.1], [1.0, 1.0, 1.0, 1.0], [0.7, 1.0, 1.15, 0.95]])
# P(has children | household, band). Family households always have children; shared ones never (declared).
CHILDREN_BY_HOUSEHOLD = {
    "alone": [0.0, 0.04, 0.10, 0.30, 0.55, 0.70],
    "couple": [0.0, 0.04, 0.08, 0.35, 0.65, 0.80],
    "family": [1.0] * 6,
    "shared": [0.0] * 6,
}
# P(partnered | couple household, band); the rest are married.
COUPLE_PARTNERED = [0.85, 0.70, 0.45, 0.30, 0.20, 0.12]
SHARED_SINGLE = [0.78, 0.65, 0.55, 0.50, 0.50, 0.50]
PET_PROBABILITY = np.array([0.36, 0.45, 0.62, 0.50])  # by household
PET_URBAN_MULT = np.array([0.9, 1.0, 1.2])
SPECIES_BASE = np.array([0.46, 0.44, 0.10])  # dog, cat, other
SPECIES_URBAN_MULT = np.array([[0.85, 1.1, 1.0], [1.0, 1.0, 1.0], [1.3, 0.9, 1.0]])
SPECIES_HOUSEHOLD_MULT = np.array([[0.9, 1.15, 1.0], [1.0, 1.0, 1.0], [1.2, 0.95, 1.0], [1.0, 1.0, 1.0]])
SKINCARE_WOMEN = np.array(
    [[0.08, 0.47, 0.45], [0.08, 0.47, 0.45], [0.10, 0.45, 0.45], [0.10, 0.45, 0.45], [0.2, 0.5, 0.3]]
    + [[0.2, 0.5, 0.3]]
)
SKINCARE_MEN = np.array(
    [[0.40, 0.45, 0.15], [0.40, 0.45, 0.15], [0.50, 0.38, 0.12], [0.50, 0.38, 0.12], [0.6, 0.32, 0.08]]
    + [[0.6, 0.32, 0.08]]
)
FITNESS_BY_BAND = np.array([0.60, 0.55, 0.45, 0.40, 0.32, 0.25])
FITNESS_MALE_BONUS = 0.05
OCCUPATION_BY_BAND = np.array(
    [
        [0.60, 0.28, 0.02, 0.00, 0.10],
        [0.08, 0.68, 0.10, 0.00, 0.14],
        [0.01, 0.72, 0.12, 0.00, 0.15],
        [0.00, 0.70, 0.12, 0.03, 0.15],
        [0.00, 0.50, 0.10, 0.28, 0.12],
        [0.00, 0.03, 0.02, 0.92, 0.03],
    ]
)
INCOME_BY_OCCUPATION = np.array(
    [
        [0.80, 0.17, 0.03],
        [0.22, 0.53, 0.25],
        [0.25, 0.40, 0.35],
        [0.35, 0.50, 0.15],
        [0.70, 0.27, 0.03],
    ]
)
INSTAGRAM_BY_BAND = np.array([0.85, 0.80, 0.62, 0.42, 0.28, 0.15])
FACEBOOK_BY_BAND = np.array([0.55, 0.70, 0.80, 0.80, 0.72, 0.60])
IOS_BY_BAND = np.array([0.45, 0.40, 0.33, 0.28, 0.25, 0.22])
DESKTOP_BY_BAND = np.array([0.35, 0.50, 0.50, 0.45, 0.40, 0.30])
SOCIAL_MINUTES_MEDIAN = np.array([95.0, 80.0, 60.0, 45.0, 40.0, 35.0])
# Latent correlations between the legacy traits (same order as TRAITS).
TRAIT_CORRELATIONS = {
    (0, 2): 0.45,
    (0, 3): 0.35,
    (1, 2): -0.10,
    (2, 3): 0.15,
    (3, 5): 0.30,
    (4, 5): -0.40,
    (4, 6): -0.25,
    (5, 6): 0.20,
}
CAVEATS = [
    "Solo il mix per età (utenti di social network) e l'acquisto online derivano da dati Eurostat.",
    "Nuclei, figli, animali, reddito, occupazione, uso di Instagram/Facebook e dispositivi sono ipotesi dichiarate "
    "(persona-skeleton-v1), non misure sul pubblico della campagna.",
    "Il targeting dettagliato agisce tramite probabilità di corrispondenza dichiarate come ipotesi.",
]
PROVENANCE = {
    "age_band": "observed_distribution",
    "online_shopper": "observed_distribution",
    **dict.fromkeys(
        [
            "age",
            "gender",
            "urbanicity",
            "household",
            "has_children",
            "relationship_status",
            "pet_species",
            "skincare_routine",
            "fitness_active",
            "occupation",
            "income_band",
            "uses_instagram",
            "uses_facebook",
            "device_os",
            "desktop_user",
            "social_minutes_per_day",
            *TRAITS,
        ],
        "assumption",
    ),
}
CATEGORICAL = [
    "gender",
    "urbanicity",
    "household",
    "has_children",
    "relationship_status",
    "pet_species",
    "skincare_routine",
    "fitness_active",
    "occupation",
    "income_band",
    "device_os",
    "uses_instagram",
    "uses_facebook",
    "desktop_user",
    "online_shopper",
]
COVERAGE_ATTRIBUTES = [
    "gender",
    "urbanicity",
    "household",
    "pet_species",
    "relationship_status",
    "skincare_routine",
    "income_band",
    "occupation",
]


def _categorical(rng, probs):
    probs = np.asarray(probs, float)
    probs = probs / probs.sum(axis=1, keepdims=True)
    index = (rng.random(len(probs))[:, None] > probs.cumsum(axis=1)).sum(axis=1)
    return np.minimum(index, probs.shape[1] - 1)


def _pick(values, index):
    return np.asarray(values)[index]


def trait_correlation_matrix():
    matrix = np.eye(len(TRAITS))
    for (i, j), value in TRAIT_CORRELATIONS.items():
        matrix[i, j] = matrix[j, i] = value
    return matrix


def sample_pool(rng, spec, vertical, per_band=POOL_PER_BAND):
    """The base population: columns of numpy arrays, equal sample size per age band."""
    band = np.repeat(np.arange(len(AGES)), per_band)
    n = band.size
    low = np.array([a for a, _ in AGE_RANGES])
    high = np.array([b for _, b in AGE_RANGES])
    age = low[band] + np.floor(rng.random(n) * (high[band] - low[band] + 1)).astype(int)
    woman = rng.random(n) < 0.5
    urban = _categorical(rng, URBANICITY_BY_BAND[band])
    household = _categorical(rng, HOUSEHOLD_BY_BAND[band] * HOUSEHOLD_URBAN_MULT[urban])
    household_name = _pick(HOUSEHOLDS, household)
    children_p = np.zeros(n)
    for index, name in enumerate(HOUSEHOLDS):
        mask = household == index
        children_p[mask] = np.asarray(CHILDREN_BY_HOUSEHOLD[name])[band[mask]]
    has_children = rng.random(n) < children_p
    relationship = np.zeros(n, dtype=int)  # single
    draw = rng.random(n)
    alone, couple, family, shared = (household == i for i in range(4))
    relationship[alone] = np.where(draw[alone] < 0.78, 0, np.where(draw[alone] < 0.88, 1, 2))
    partnered_p = np.asarray(COUPLE_PARTNERED)[band[couple]]
    relationship[couple] = np.where(draw[couple] < partnered_p, 1, 2)
    relationship[family] = np.where(draw[family] < 0.06, 0, np.where(draw[family] < 0.30, 1, 2))
    single_p = np.asarray(SHARED_SINGLE)[band[shared]]
    rest = (draw[shared] - single_p) / (1 - single_p)
    relationship[shared] = np.where(draw[shared] < single_p, 0, np.where(rest < 0.85, 1, 2))
    has_pet = rng.random(n) < np.minimum(0.95, PET_PROBABILITY[household] * PET_URBAN_MULT[urban])
    species = _categorical(rng, SPECIES_BASE * SPECIES_URBAN_MULT[urban] * SPECIES_HOUSEHOLD_MULT[household])
    pet = np.where(has_pet, _pick(PETS[:3], species), "none")
    skin_probs = np.where(woman[:, None], SKINCARE_WOMEN[band], SKINCARE_MEN[band])
    skincare = _pick(SKINCARE, _categorical(rng, skin_probs))
    fitness = rng.random(n) < FITNESS_BY_BAND[band] + np.where(woman, 0.0, FITNESS_MALE_BONUS)
    occupation = _categorical(rng, OCCUPATION_BY_BAND[band])
    income = _categorical(rng, INCOME_BY_OCCUPATION[occupation])
    ig = rng.random(n) < INSTAGRAM_BY_BAND[band]
    fb = rng.random(n) < FACEBOOK_BY_BAND[band]
    neither = ~(ig | fb)  # everyone in the pool is a social-network user
    prefer_ig = rng.random(n) < INSTAGRAM_BY_BAND[band] / (INSTAGRAM_BY_BAND[band] + FACEBOOK_BY_BAND[band])
    ig, fb = ig | (neither & prefer_ig), fb | (neither & ~prefer_ig)
    ios = rng.random(n) < IOS_BY_BAND[band]
    desktop = rng.random(n) < DESKTOP_BY_BAND[band]
    minutes = np.maximum(5, np.rint(SOCIAL_MINUTES_MEDIAN[band] * np.exp(rng.normal(0, 0.5, n)))).astype(int)
    shopper = rng.random(n) < np.array([spec["online_purchase_rate"][b] for b in AGES])[band]
    pool: dict[str, Any] = {
        "band": band,
        "age": age,
        "gender": np.where(woman, "women", "men"),
        "urbanicity": _pick(URBANICITIES, urban),
        "household": household_name,
        "has_children": np.where(has_children, "yes", "no"),
        "relationship_status": _pick(RELATIONSHIPS, relationship),
        "pet_species": pet,
        "skincare_routine": skincare,
        "fitness_active": np.where(fitness, "yes", "no"),
        "occupation": _pick(OCCUPATIONS, occupation),
        "income_band": _pick(INCOMES, income),
        "uses_instagram": ig,
        "uses_facebook": fb,
        "device_os": np.where(ios, "ios", "android"),
        "desktop_user": desktop,
        "social_minutes_per_day": minutes,
        "online_shopper": shopper,
    }
    pool.update(_sample_traits(rng, pool, vertical))
    return pool


def _relevance(pool, vertical):
    """How naturally the vertical fits each person, in latent standard deviations (declared assumption)."""
    n = pool["age"].size
    if vertical == "pet_ecommerce":
        table = {"dog": 1.0, "cat": 1.0, "other": 0.5, "none": -0.9}
        return np.array([table[v] for v in pool["pet_species"]])
    if vertical == "beauty_skincare":
        table = {"extended": 0.9, "basic": 0.2, "none": -0.8}
        return np.array([table[v] for v in pool["skincare_routine"]])
    return np.where(
        pool["income_band"] == "high", 0.2, np.where(pool["income_band"] == "low", -0.2, 0.0)
    ) + np.zeros(n)


def _sample_traits(rng, pool, vertical):
    n = pool["age"].size
    chol = np.linalg.cholesky(trait_correlation_matrix())
    z = rng.standard_normal((n, len(TRAITS))) @ chol.T
    band, relevance = pool["band"], _relevance(pool, vertical)
    income = pool["income_band"]
    z[:, 0] += relevance
    z[:, 2] += 0.5 * relevance
    z[:, 1] += np.where(income == "low", 0.7, np.where(income == "high", -0.7, 0.0)) + np.where(
        band == 0, 0.3, 0.0
    )
    z[:, 4] += np.where(band <= 1, 0.3, np.where(band == 5, -0.5, 0.0)) + np.where(
        pool["online_shopper"], 0.2, 0.0
    )
    z[:, 6] += np.where(band == 0, -0.2, np.where(band >= 4, 0.2, 0.0))
    values = beta_dist.ppf(np.clip(norm.cdf(z), 1e-6, 1 - 1e-6), 2, 2)
    traits = {name: values[:, i] for i, name in enumerate(TRAITS)}
    for trait, effect in ASSUMED_SHOPPER_EFFECT.items():
        traits[trait] = np.clip(traits[trait] + np.where(pool["online_shopper"], effect, -effect), 0, 1)
    return traits


def base_rates(pool, base_weight):
    """Share of each value of the attributes the targeting terms refer to, in the unfiltered base population."""
    rates = {}
    total = base_weight.sum()
    for attribute, spec in PERSONA_ATTRIBUTES.items():
        rates[attribute] = {v: float(base_weight[pool[attribute] == v].sum() / total) for v in spec["values"]}
    return rates


def term_reach(term_id, pool, base):
    """Relative reach in [0, 1] of one detailed term for each person, or None when the term is not modelled."""
    match = DETAILED_TERMS[term_id]["match"]
    if not match:
        return None
    ratio = np.ones(pool["age"].size)
    for attribute, distribution in match.items():
        values = PERSONA_ATTRIBUTES[attribute]["values"]
        lookup = {v: distribution.get(v, 0.0) / max(base[attribute][v], 1e-9) for v in values}
        ratio = ratio * np.array([lookup[v] for v in pool[attribute]])
    top = ratio.max()
    return ratio / top if top > 0 else ratio


def detailed_reach(pool, spec: TargetingSpec, base):
    reach = np.ones(pool["age"].size)
    included = [
        r for t in spec.detailed if t.mode == "include" and (r := term_reach(t.id, pool, base)) is not None
    ]
    if included:
        reach = reach * (1 - np.prod([1 - r for r in included], axis=0))
    for term in spec.detailed:
        value = term_reach(term.id, pool, base) if term.mode != "include" else None
        if value is None:
            continue
        reach = reach * (value if term.mode == "narrow" else 1 - value)
    if spec.advantage_audience:
        reach = (1 - ADVANTAGE_AUDIENCE_WIDENING) * reach + ADVANTAGE_AUDIENCE_WIDENING
    unmodelled = [t.id for t in spec.detailed if not DETAILED_TERMS[t.id]["match"]]
    return reach, unmodelled


def delivered_placements(spec: TargetingSpec, device):
    chosen = list(PLACEMENTS) if spec.advantage_placements else list(spec.placements)
    kept = []
    for placement in chosen:
        info = PLACEMENTS[placement]
        if device == "desktop" and info["surface"] in MOBILE_ONLY_SURFACES:
            continue
        if device == "mobile" and info.get("desktop_only"):
            continue
        kept.append(placement)
    return kept


def placement_eligibility(pool, placements):
    platforms = {PLACEMENTS[p]["platform"] for p in placements}
    eligible = np.zeros(pool["age"].size)
    if "instagram" in platforms:
        eligible = np.maximum(eligible, pool["uses_instagram"].astype(float))
    if platforms & {"facebook", "messenger"}:
        eligible = np.maximum(eligible, pool["uses_facebook"].astype(float))
    if "audience_network" in platforms:
        eligible = np.maximum(eligible, AUDIENCE_NETWORK_REACH)
    return eligible


def device_eligibility(pool, spec: TargetingSpec):
    if not spec.device_platforms:
        return np.ones(pool["age"].size)
    allowed = np.zeros(pool["age"].size, dtype=bool)
    if "ios" in spec.device_platforms:
        allowed |= pool["device_os"] == "ios"
    if "android" in spec.device_platforms:
        allowed |= pool["device_os"] == "android"
    if "desktop" in spec.device_platforms:
        allowed |= pool["desktop_user"]
    return allowed.astype(float)


def reach_weights(pool, spec: TargetingSpec, base, device):
    placements = delivered_placements(spec, device)
    if not placements:
        raise ValueError("Nessun placement consegnabile con il dispositivo scelto")
    weight = ((pool["age"] >= spec.age_min) & (pool["age"] <= spec.age_max)).astype(float)
    if spec.gender != "all":
        weight = weight * (pool["gender"] == spec.gender)
    if spec.urbanicity != "any":
        weight = weight * (pool["urbanicity"] == spec.urbanicity)
    weight = weight * device_eligibility(pool, spec) * placement_eligibility(pool, placements)
    detail, unmodelled = detailed_reach(pool, spec, base)
    return weight * detail, unmodelled, placements


def satisfied(constraint, pool):
    inside = np.isin(pool[constraint.attribute], constraint.values)
    return ~inside if constraint.negate else inside


def resolved_constraints(spec: TargetingSpec):
    from_text, _, _, _ = read_intent(spec.audience_intent)
    return merge_constraints(spec.constraints, from_text)


def _split(size, parts):
    base, extra = divmod(size, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def _systematic(rng, order, weights, count):
    """Weighted selection without replacement over a sorted order: low-variance and implicitly stratified."""
    cumulative = np.cumsum(weights[order])
    points = (rng.random() + np.arange(count)) * cumulative[-1] / count
    chosen = list(
        dict.fromkeys(order[np.minimum(np.searchsorted(cumulative, points), len(order) - 1)].tolist())
    )
    remaining = weights.copy()
    remaining[chosen] = 0
    while len(chosen) < count and remaining.sum() > 0:
        extra = int(rng.choice(len(weights), p=remaining / remaining.sum()))
        chosen.append(extra)
        remaining[extra] = 0
    return chosen


def select_panel(rng, pool, weights, base_weight, size):
    """Per-band allocation (equal across reached bands) and the reach share of every band."""
    band_weight = np.array([weights[pool["band"] == b].sum() for b in range(len(AGES))])
    total = band_weight.sum()
    if total <= 0:
        raise ValueError("Il targeting esclude l'intera popolazione simulata")
    shares = band_weight / total
    active = [b for b in range(len(AGES)) if band_weight[b] > 0]
    sizes = dict(zip(active, _split(size, len(active)), strict=True))
    key = np.lexsort(
        (
            pool["age"],
            np.unique(pool["gender"], return_inverse=True)[1],
            np.unique(pool["urbanicity"], return_inverse=True)[1],
            np.unique(pool["pet_species"], return_inverse=True)[1],
            np.unique(pool["household"], return_inverse=True)[1],
        )
    )
    chosen = []
    for band in active:
        order = key[(pool["band"][key] == band) & (weights[key] > 0)]
        chosen.extend((band, i) for i in _systematic(rng, order, weights, sizes[band]))
    return chosen, shares, sizes


def gower_matrix(columns):
    numeric = [columns[k] for k in ("age", "social_minutes_per_day", *TRAITS)]
    total = np.zeros((len(numeric[0]), len(numeric[0])))
    for values in numeric:
        values = np.asarray(values, float)
        span = float(values.max() - values.min()) or 1.0
        total += np.abs(values[:, None] - values[None, :]) / span
    for name in CATEGORICAL:
        values = np.asarray(columns[name])
        total += values[:, None] != values[None, :]
    return total / (len(numeric) + len(CATEGORICAL))


def audit_panel(panel, pool, weights, shares):
    n = len(panel["age"])
    distance = gower_matrix(panel)
    off = distance[~np.eye(n, dtype=bool)]
    duplicates = int(((distance == 0).sum() - n) // 2)
    reached = weights / weights.sum()
    missing = []
    for attribute in COVERAGE_ATTRIBUTES:
        present = set(np.unique(panel[attribute]))
        for value in np.unique(pool[attribute]):
            if reached[pool[attribute] == value].sum() >= 0.10 and value not in present:
                missing.append(f"{attribute}={value}")
    effective = float(weights.sum() ** 2 / (len(weights) * (weights**2).sum()))
    warnings = []
    if duplicates:
        warnings.append(f"{duplicates} coppie di persone identiche")
    if off.size and float(off.min()) < 0.02:
        warnings.append("persone quasi identiche (distanza minima sotto 0,02)")
    if missing:
        warnings.append("valori frequenti assenti dal pannello: " + ", ".join(missing))
    if effective < 0.05:
        warnings.append("il targeting concentra la consegna su una piccola parte della popolazione")
    return {
        "size": n,
        "duplicates": duplicates,
        "min_distance": round(float(off.min()), 4) if off.size else None,
        "mean_distance": round(float(off.mean()), 4) if off.size else None,
        "band_counts": {band: int((np.asarray(panel["band"]) == i).sum()) for i, band in enumerate(AGES)},
        "reach_effective_ratio": round(effective, 4),
        "missing_values": missing,
        "status": "warning" if warnings else "ok",
        "warnings": warnings,
    }


def _reach_summary(pool, weights, base_weight, constraints, shares, unmodelled, audit):
    reached = weights / weights.sum()
    base = base_weight / base_weight.sum()
    per_constraint = []
    ideal_reached = np.ones(len(weights), dtype=bool)
    for constraint in constraints:
        hit = satisfied(constraint, pool)
        ideal_reached &= hit
        per_constraint.append(
            {
                "attribute": constraint.attribute,
                "values": list(constraint.values),
                "negate": constraint.negate,
                "share_in_reached": round(float(reached[hit].sum()), 4),
                "share_in_base": round(float(base[hit].sum()), 4),
            }
        )
    ideal_share = float(reached[ideal_reached].sum()) if constraints else None
    base_ideal = float(base[ideal_reached].sum()) if constraints else None
    return {
        "method": METHOD,
        "pool_size": int(len(weights)),
        "age_shares": [round(float(s), 6) for s in shares],
        "constraints": per_constraint,
        "ideal_share_in_reached": None if ideal_share is None else round(ideal_share, 4),
        "ideal_share_in_base": None if base_ideal is None else round(base_ideal, 4),
        "lift": round(ideal_share / base_ideal, 3) if base_ideal else None,
        "unmodelled_terms": unmodelled,
        "audit": audit,
    }


def population_spec(brief: CampaignBrief):
    from . import audience_spec

    marginals = audience_spec.load_marginals()
    if marginals is not None and brief.country in marginals["countries"]:
        spec = audience_spec.build_spec(marginals, brief.country)
        observed = True
    else:
        spec = {
            "spec_id": "fallback-uniform",
            "age_shares": list(brief.age_shares),
            "online_purchase_rate": dict.fromkeys(AGES, 0.75),
        }
        observed = False
    shares = list(brief.age_shares) if "age_shares" in brief.model_fields_set else spec["age_shares"]
    return spec, shares, observed


def generate_targeted_population(brief: CampaignBrief, pool_per_band=POOL_PER_BAND):
    """Panel of persona skeletons for ``brief.targeting`` plus the reach summary. Returns (profiles, reach)."""
    targeting = brief.targeting or TargetingSpec()
    spec, shares, observed = population_spec(brief)
    seed_parts = (brief.seed, brief.vertical, brief.brand, spec["spec_id"], pool_per_band)
    pool = sample_pool(
        np.random.default_rng(stable_seed(*seed_parts, "pool-v1")), spec, brief.vertical, pool_per_band
    )
    base_weight = np.asarray(shares, float)[pool["band"]] / pool_per_band
    rates = base_rates(pool, base_weight)
    reach, unmodelled, _ = reach_weights(pool, targeting, rates, brief.device)
    weights = base_weight * reach
    select_rng = np.random.default_rng(stable_seed(*seed_parts, "select-v1"))
    chosen, band_shares, sizes = select_panel(select_rng, pool, weights, base_weight, brief.population_size)
    constraints = resolved_constraints(targeting)
    ideal = np.ones(len(weights), dtype=bool)
    for constraint in constraints:
        ideal &= satisfied(constraint, pool)
    indices = np.array([i for _, i in chosen])
    columns = {name: np.asarray(values)[indices] for name, values in pool.items()}
    audit = audit_panel(columns, pool, weights, band_shares)
    context = {
        "beauty_skincare": "routine e familiarità skincare ipotetiche",
        "pet_ecommerce": "animale e necessità ipotetici, non osservati",
        "abbigliamento": "stile e necessità di taglia ipotetici",
    }[brief.vertical]
    suffix = "età e acquisti online da dati Eurostat" if observed else "marginali non disponibili, ipotesi"
    counters = dict.fromkeys(range(len(AGES)), 0)
    profiles = []
    for position, (band, index) in enumerate(chosen):
        counters[band] += 1
        profile = {
            "agent_id": f"synthetic-{band + 1}-{counters[band]:03d}",
            "age_band": AGES[band],
            "population_weight": float(band_shares[band] / sizes[band]),
            "age": int(pool["age"][index]),
            "gender": str(pool["gender"][index]),
            "urbanicity": str(pool["urbanicity"][index]),
            "household": str(pool["household"][index]),
            "has_children": str(pool["has_children"][index]),
            "relationship_status": str(pool["relationship_status"][index]),
            "pet_species": str(pool["pet_species"][index]),
            "skincare_routine": str(pool["skincare_routine"][index]),
            "fitness_active": str(pool["fitness_active"][index]),
            "occupation": str(pool["occupation"][index]),
            "income_band": str(pool["income_band"][index]),
            "uses_instagram": bool(pool["uses_instagram"][index]),
            "uses_facebook": bool(pool["uses_facebook"][index]),
            "device_os": str(pool["device_os"][index]),
            "desktop_user": bool(pool["desktop_user"][index]),
            "social_minutes_per_day": int(pool["social_minutes_per_day"][index]),
            **{t: float(pool[t][index]) for t in TRAITS},
            "online_shopper": bool(pool["online_shopper"][index]),
            "category_context": f"{context}; {suffix}, attributi e tratti ipotetici",
            "profile_version": PROFILE_VERSION,
            "spec_id": spec["spec_id"],
            "assumption_id": ASSUMPTION_ID,
            "provenance": dict(PROVENANCE),
            "seed": brief.seed,
            "evidence_level": "partially_observed_marginals" if observed else "modeled_assumption",
            "in_ideal_target": bool(ideal[index]) if constraints else True,
        }
        if targeting.regions:
            profile["region"] = targeting.regions[position % len(targeting.regions)]
        profiles.append(profile)
    reach_summary = _reach_summary(pool, weights, base_weight, constraints, band_shares, unmodelled, audit)
    return profiles, reach_summary
