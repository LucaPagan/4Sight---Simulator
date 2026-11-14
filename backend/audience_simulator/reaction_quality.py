"""Checks on the substance of generated reactions: repetition, grounding, invented claims, consistency.

All checks are lexical or rule based and descriptive. They flag reactions for review; they do not prove or
disprove that a reaction resembles a real person. ``human_validated`` stays False until the blind rubric
(``export_rubric`` / ``score_rubric``) has been filled in by people.
"""

import csv
import hashlib
import io
import re

import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import cohen_kappa_score
from sklearn.metrics.pairwise import cosine_similarity

STOPWORDS = set(
    "che non per una uno con come sono più della delle dello degli dalla nella sulla questo questa "
    "mentre anche forse magari però perché quando molto poco ancora ogni tutti tutto fare sembra "
    "potrebbe vorrei avrei sarei essere stato fatto quindi invece prima dopo senza sopra sotto "
    "mio mia miei mie suo sua loro cosa cose altro altra solo già sempre mai ecco dove".split()
)
CONCEPTS = {
    "price": r"prezz|cost[oa]\b|€|euro|economic|\bcara\b|\bcaro\b",
    "wait": r"aspett|rimand|più tardi|prima di decidere|in seguito|non ora",
    "trust_proof": r"recension|opinion|testimon|prove\b|garanz|certific|fiduc|dermatolog",
    "scarcity": r"scars|ultim[ie]\b|limitat|urgen|scadenz|sconto|offert|promo",
    "ingredients": r"ingredient|acido|\battiv|formula|\binci\b|composizion",
    "relevance_need": r"mi serve|ne ho bisogno|routine|ho già|uso già",
}
PRICE = re.compile(CONCEPTS["price"], re.I)
THRESHOLDS = {
    "min_records": 6,
    "cluster_share": 0.5,
    "lexical_similarity": 0.8,
    "brief_limit_share": 0.5,
    "grounded_share_min": 0.7,
    "invented_share_max": 0.05,
    "inconsistent_share_max": 0.10,
}
DIMENSIONS = ("groundedness", "coherence", "usefulness")


def _tokens(text):
    return [t for t in re.findall(r"\w+", str(text).casefold()) if len(t) >= 5 and t not in STOPWORDS]


def _stem(token):
    return token[:6]


def _creative_text(record):
    creative = record["input"]["creative"]
    keys = (
        "headline",
        "primary_text",
        "offer",
        "price_text",
        "cta",
        "landing_page_summary",
        "visual_description",
    )
    return " ".join(str(creative.get(k) or "") for k in keys)


def references_creative(record):
    """True when the reaction reuses content words of the creative. Cited evidence alone is not grounding."""
    seen = {_stem(t) for t in _tokens(_creative_text(record))}
    return any(_stem(t) in seen for t in _tokens(record["evaluation"]["conditional_reaction"]))


def _normalize_number(text):
    return format(float(text.replace(",", ".")), "g")


def _numbers(text):
    return [_normalize_number(n) for n in re.findall(r"\d+(?:[.,]\d+)?", str(text))]


def invented_numbers(record):
    """Numbers in the reaction that appear nowhere in the creative, campaign or age band."""
    payload = record["input"]
    known = set(_numbers(_creative_text(record)))
    for value in payload["campaign"].values():
        known.update(_numbers(value))
    known.update(_numbers(payload["profile"].get("age_band", "")))
    return sorted({n for n in _numbers(record["evaluation"]["conditional_reaction"]) if n not in known})


def profile_inconsistencies(record):
    e, profile = record["evaluation"], record["input"]["profile"]
    codes = []
    if e["conditional_action"] == "consider_click" and e["interest"] <= 1:
        codes.append("consider_click_with_low_interest")
    if e["conditional_action"] == "not_interested" and e["interest"] >= 3:
        codes.append("not_interested_with_high_interest")
    if (
        e["conditional_action"] == "not_interested"
        and profile.get("purchase_need", 0) >= 0.9
        and profile.get("category_affinity", 0) >= 0.9
        and e["clarity"] >= 3
        and e["credibility"] >= 3
    ):
        codes.append("not_interested_despite_need_clarity_and_credibility")
    return codes


def _concepts(text):
    return frozenset(name for name, pattern in CONCEPTS.items() if re.search(pattern, text, re.I))


def _cluster_size(n, edges):
    """Size of the largest connected group of near-identical reactions (union-find)."""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in edges:
        parent[find(i)] = find(j)
    sizes: dict[int, int] = {}
    for i in range(n):
        sizes[find(i)] = sizes.get(find(i), 0) + 1
    return max(sizes.values(), default=0)


def _repetition(reactions):
    n = len(reactions)
    counts: dict[frozenset, int] = {}
    for signature in (_concepts(r) for r in reactions):
        if signature:
            counts[signature] = counts.get(signature, 0) + 1
    concept = max(counts.values(), default=0) / n
    lexical = 1 / n
    if n >= 2:
        matrix = CountVectorizer(binary=True).fit_transform(
            [" ".join(_tokens(r)) or "vuoto" for r in reactions]
        )
        sims = cosine_similarity(matrix)
        edges = [
            (i, j)
            for i in range(n)
            for j in range(i + 1, n)
            if sims[i, j] >= THRESHOLDS["lexical_similarity"]
        ]
        lexical = _cluster_size(n, edges) / n
    return {
        "concept_largest_cluster_share": concept,
        "lexical_largest_cluster_share": lexical,
        "largest_cluster_share": max(concept, lexical),
    }


def _assess(records):
    n = len(records)
    reactions = [r["evaluation"]["conditional_reaction"] for r in records]
    price_missing = all(
        r["input"]["campaign"].get("price_eur") is None and not r["input"]["creative"].get("price_text")
        for r in records
    )
    price_share = sum(bool(PRICE.search(t)) for t in reactions) / n
    grounded = sum(references_creative(r) for r in records) / n
    invented = sum(bool(invented_numbers(r)) for r in records) / n
    inconsistent = sum(bool(profile_inconsistencies(r)) for r in records) / n
    repetition = _repetition(reactions)
    flags = []
    if n >= THRESHOLDS["min_records"]:
        if price_missing and price_share >= THRESHOLDS["brief_limit_share"]:
            flags.append("brief_limit_dominates")
        if repetition["largest_cluster_share"] >= THRESHOLDS["cluster_share"]:
            flags.append("conceptual_repetition")
        if grounded < THRESHOLDS["grounded_share_min"]:
            flags.append("weak_grounding")
        if invented > THRESHOLDS["invented_share_max"]:
            flags.append("invented_numbers")
        if inconsistent > THRESHOLDS["inconsistent_share_max"]:
            flags.append("inconsistent_action")
    return {
        "reactions": n,
        "brief_limit": {"price_missing": price_missing, "share_mentioning_price": price_share},
        "repetition": repetition,
        "grounded_share": grounded,
        "invented_numbers_share": invented,
        "inconsistent_action_share": inconsistent,
        "flags": flags,
    }


def assess_panel(records):
    """records: policy snapshot items {key, input, evaluation}. Flags are for review, not verdicts."""
    if not records:
        raise ValueError("Nessuna reazione da valutare")
    result = _assess(records)
    creatives = sorted({r["input"]["creative"]["id"] for r in records})
    result["by_creative"] = {
        cid: _assess([r for r in records if r["input"]["creative"]["id"] == cid]) for cid in creatives
    }
    result["thresholds"] = THRESHOLDS
    result["human_validated"] = False
    result["warning"] = (
        "Controlli lessicali e regole sulle risposte del modello. Segnalano reazioni da rivedere; "
        "non dimostrano né escludono somiglianza con persone reali."
    )
    return result


def _blind_id(seed, key):
    return hashlib.sha256(f"{seed}|{key}".encode()).hexdigest()[:10]


def export_rubric(records, n=60, seed=0):
    """Fixed blind sample for human raters. The blind-id to record map is returned apart from the CSV."""
    chosen = sorted(records, key=lambda r: _blind_id(seed, r["key"]))[:n]
    out = io.StringIO()
    columns = ["blind_id", "creative", "profile", "reaction", *DIMENSIONS]
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    key = {}
    for record in chosen:
        blind = _blind_id(seed, record["key"])
        creative, profile = record["input"]["creative"], record["input"]["profile"]
        key[blind] = record["key"]
        writer.writerow(
            {
                "blind_id": blind,
                "creative": " | ".join(
                    str(creative.get(k))
                    for k in ("headline", "primary_text", "offer", "price_text")
                    if creative.get(k)
                ),
                "profile": f"età {profile.get('age_band')}; bisogno {profile.get('purchase_need', 0):.2f}; "
                f"affinità {profile.get('category_affinity', 0):.2f}; "
                f"sensibilità al prezzo {profile.get('budget_sensitivity', 0):.2f}",
                "reaction": record["evaluation"]["conditional_reaction"],
            }
        )
    return {
        "csv": out.getvalue(),
        "key": key,
        "rubric": {
            "groundedness": "0 = non riguarda l'annuncio, 1 = in parte, 2 = riguarda chiaramente il contenuto",
            "coherence": "0 = incoerente col profilo, 1 = plausibile, 2 = coerente col profilo",
            "usefulness": "0 = generica o ripetitiva, 1 = utile in parte, 2 = utile per decidere",
        },
    }


def _mean(values):
    return float(np.mean(values)) if values else None


def score_rubric(ratings_by_rater, key, records):
    by_key = {r["key"]: r for r in records}
    by_rater = {
        rater: {row["blind_id"]: {d: int(row[d]) for d in DIMENSIONS} for row in rows}
        for rater, rows in ratings_by_rater.items()
    }
    pooled = {d: [v[d] for rows in by_rater.values() for v in rows.values()] for d in DIMENSIONS}
    agreement = None
    if len(by_rater) >= 2:
        first, second = list(by_rater.values())[:2]
        common = sorted(set(first) & set(second))
        agreement = {}
        for d in DIMENSIONS:
            a, b = [first[i][d] for i in common], [second[i][d] for i in common]
            kappa = None if len(set(a) | set(b)) < 2 else float(cohen_kappa_score(a, b, weights="linear"))
            agreement[d] = {"weighted_kappa": kappa, "items": len(common)}
    grounded, ungrounded = [], []
    for rows in by_rater.values():
        for blind, values in rows.items():
            (grounded if references_creative(by_key[key[blind]]) else ungrounded).append(
                values["groundedness"]
            )
    return {
        "raters": len(by_rater),
        "items": len({b for rows in by_rater.values() for b in rows}),
        "mean": {d: _mean(v) for d, v in pooled.items()},
        "agreement": agreement,
        "automated_vs_human": {
            "grounded_mean_groundedness": _mean(grounded),
            "ungrounded_flag_mean_groundedness": _mean(ungrounded),
        },
    }
