"""Audience spec v2: observed marginals (Eurostat) plus explicitly labelled assumptions.

Observed: the age mix of social-network users (resident population x social-network use) and the share
of people who bought online in the last 12 months, per country and age band. Everything else stays a
declared assumption: the seven behavioural traits are still Beta(2,2) draws, with one small declared
effect of online shopping on trust and purchase need. Nothing here is measured on campaign recipients.
"""

import json
from datetime import date
from pathlib import Path

import httpx
import numpy as np

from .audience import band_sizes, stable_seed
from .schemas import AGES

EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
MARGINALS_PATH = Path(__file__).parent / "specs" / "marginals.json"
AGE_TO_EUROSTAT = {
    "18-24": "Y16_24",
    "25-34": "Y25_34",
    "35-44": "Y35_44",
    "45-54": "Y45_54",
    "55-64": "Y55_64",
    "65+": "Y65_74",
}
SKIPPED_DIMENSIONS = {"freq", "indic_is", "unit", "sex", "statinfo"}
TRAITS = [
    "category_affinity",
    "budget_sensitivity",
    "purchase_need",
    "brand_familiarity",
    "advertising_literacy",
    "trust",
    "repeat_tolerance",
]
# Declared assumption, not an estimate: online shoppers are slightly more trusting and ready to buy.
ASSUMED_SHOPPER_EFFECT = {"trust": 0.08, "purchase_need": 0.08}
CAVEATS = [
    "Il mix per età è quello degli utenti di social network residenti, non il pubblico effettivo della campagna.",
    "Eurostat riporta 16-24 anni per la fascia 18-24 e 65-74 anni per la fascia 65+.",
    "I sette tratti comportamentali restano ipotesi Beta(2,2); l'effetto dell'acquisto online è dichiarato, non stimato.",
]


def parse_jsonstat(data, order=None):
    """Flat JSON-stat values -> {(category codes...): value}. Fixed filter dimensions are dropped."""
    ids, sizes = data["id"], data["size"]
    categories = {d: list(data["dimension"][d]["category"]["index"]) for d in ids}
    keep = [d for d in ids if d not in SKIPPED_DIMENSIONS]
    names = list(order) if order else keep
    cells = {}
    for flat, value in data["value"].items():
        remainder, coords = int(flat), {}
        for dim, size in zip(reversed(ids), reversed(sizes), strict=True):
            remainder, position = divmod(remainder, size)
            coords[dim] = categories[dim][position]
        cells[tuple(coords[n] for n in names)] = value
    return cells


def _get(http, dataset, params):
    response = http.get(f"{EUROSTAT}/{dataset}", params=params)
    response.raise_for_status()
    return response.json()


def _latest_complete(cells, geo, codes):
    periods = sorted({k[2] for k in cells if k[0] == geo}, reverse=True)
    for period in periods:
        if all(cells.get((geo, code, period)) is not None for code in codes):
            return period, {code: cells[(geo, code, period)] for code in codes}
    raise ValueError(f"Nessun periodo completo per {geo}")


def _band_of(code):
    if code == "Y_OPEN":
        return "65+"
    age = int(code[1:])
    return (
        AGES[0]
        if age <= 24
        else AGES[1]
        if age <= 34
        else AGES[2]
        if age <= 44
        else (AGES[3] if age <= 54 else AGES[4] if age <= 64 else AGES[5])
    )


def fetch_marginals(countries, transport=None, today=None, since="2021"):
    """Read the three Eurostat tables for the given countries; nothing is guessed or filled in."""
    population_codes = [f"Y{a}" for a in range(18, 100)] + ["Y_OPEN"]
    survey_codes = [AGE_TO_EUROSTAT[b] for b in AGES]
    result = {
        "version": "eurostat-v1",
        "retrieved": today or date.today().isoformat(),
        "sources": {
            "population": {"dataset": "demo_pjan", "unit": "NR", "note": "popolazione al 1 gennaio, 18+"},
            "social": {"dataset": "isoc_ci_ac_i", "indicator": "I_IUSNET", "unit": "PC_IND"},
            "shopping": {"dataset": "isoc_ec_ib20", "indicator": "I_BLT12", "unit": "PC_IND"},
        },
        "countries": {},
    }
    with httpx.Client(timeout=60, transport=transport) as http:
        population = parse_jsonstat(
            _get(
                http,
                "demo_pjan",
                [("format", "JSON"), ("lang", "EN"), ("freq", "A"), ("unit", "NR"), ("sex", "T")]
                + [("geo", c) for c in countries]
                + [("age", a) for a in population_codes]
                + [("sinceTimePeriod", since)],
            ),
            order=("geo", "age", "time"),
        )
        survey = {}
        for name, dataset, indicator in (
            ("social", "isoc_ci_ac_i", "I_IUSNET"),
            ("shopping", "isoc_ec_ib20", "I_BLT12"),
        ):
            survey[name] = parse_jsonstat(
                _get(
                    http,
                    dataset,
                    [("format", "JSON"), ("lang", "EN"), ("indic_is", indicator), ("unit", "PC_IND")]
                    + [("geo", c) for c in countries]
                    + [("ind_type", t) for t in survey_codes]
                    + [("sinceTimePeriod", since)],
                ),
                order=("geo", "ind_type", "time"),
            )
    for geo in countries:
        population_period, counts = _latest_complete(population, geo, population_codes)
        by_band = dict.fromkeys(AGES, 0)
        for code, value in counts.items():
            by_band[_band_of(code)] += value
        periods = {"population": population_period}
        series = {}
        for name in ("social", "shopping"):
            period, values = _latest_complete(survey[name], geo, survey_codes)
            periods[name] = period
            series[name] = {band: values[AGE_TO_EUROSTAT[band]] for band in AGES}
        result["countries"][geo] = {
            "population_18plus_by_band": by_band,
            "social_network_use_pct": series["social"],
            "online_purchase_12m_pct": series["shopping"],
            "periods": periods,
        }
    return result


def load_marginals():
    if not MARGINALS_PATH.is_file():
        return None
    return json.loads(MARGINALS_PATH.read_text())


def build_spec(marginals, country):
    data = marginals["countries"][country]
    social, shopping = data["social_network_use_pct"], data["online_purchase_12m_pct"]
    population = data["population_18plus_by_band"]
    for series in (social, shopping):
        if set(series) != set(AGES) or any(not 0 <= v <= 100 for v in series.values()):
            raise ValueError("Marginali non valide: serve ogni fascia con percentuali tra 0 e 100")
    if set(population) != set(AGES) or any(v < 0 for v in population.values()):
        raise ValueError("Popolazione per fascia non valida")
    weighted = np.array([population[b] * social[b] / 100 for b in AGES], float)
    if weighted.sum() <= 0:
        raise ValueError("Pubblico social nullo")
    return {
        "spec_id": f"{marginals['version']}:{country}",
        "country": country,
        "age_shares": [float(x) for x in weighted / weighted.sum()],
        "online_purchase_rate": {b: shopping[b] / 100 for b in AGES},
        "periods": data.get("periods", {}),
        "retrieved": marginals.get("retrieved"),
        "caveats": CAVEATS,
    }


def generate_profiles_v2(seed, vertical, brand, spec, size=120, age_shares=None, category_context=""):
    rng = np.random.default_rng(stable_seed(seed, vertical, brand, "profiles-v2", spec["spec_id"]))
    shares = list(age_shares) if age_shares is not None else spec["age_shares"]
    sizes = band_sizes(size)
    profiles = []
    for s, band in enumerate(AGES):
        for j in range(sizes[s]):
            traits = dict(zip(TRAITS, map(float, rng.beta(2, 2, len(TRAITS))), strict=True))
            shopper = bool(rng.random() < spec["online_purchase_rate"][band])
            for trait, effect in ASSUMED_SHOPPER_EFFECT.items():
                traits[trait] = float(np.clip(traits[trait] + (effect if shopper else -effect), 0, 1))
            profiles.append(
                {
                    "agent_id": f"synthetic-{s + 1}-{j + 1:03d}",
                    "age_band": band,
                    "population_weight": shares[s] / sizes[s],
                    **traits,
                    "online_shopper": shopper,
                    "category_context": category_context,
                    "profile_version": "profiles-v2",
                    "spec_id": spec["spec_id"],
                    "assumption_id": "beta-traits-v1+online-shopper-effect-v1",
                    "provenance": {
                        "age_band": "observed_distribution",
                        "online_shopper": "observed_distribution",
                        **dict.fromkeys(TRAITS, "assumption"),
                    },
                    "seed": seed,
                    "evidence_level": "partially_observed_marginals",
                }
            )
    return profiles
