"""Read a TargetingSpec: intent -> constraints, constraints -> Meta proxies, and what the proxies lose.

Rule based and deterministic (``rules_v1``): a small Italian lexicon recognises common phrases and says what it
did not understand instead of guessing. An LLM reader can replace the lexicon later without changing the
report shape. Nothing here samples people; the report only states how the intent will be interpreted.
"""

import re

from .meta_catalog import (
    DETAILED_TERMS,
    MOBILE_ONLY_SURFACES,
    PERSONA_ATTRIBUTES,
    PLACEMENTS,
    SUGGESTED_PROXIES,
)
from .schemas import (
    AudienceConstraint,
    ProxySuggestion,
    ReachSummary,
    TargetingAnalyzeRequest,
    TargetingNote,
    TargetingReport,
    TargetingSpec,
)

# (pattern, attribute, values, negate). Matched spans are removed so the remainder can be reported.
LEXICON = [
    (
        r"\b(?:chi\s+)?(?:ha|hanno|possiede|possiedono)\s+(?:un|uno|dei|due|tre)?\s*cane\b|\bproprietari\s+di\s+cani\b|\bcon\s+(?:un\s+)?cane\b|\bdog\s+owners?\b",
        "pet_species",
        ["dog"],
        False,
    ),
    (
        r"\b(?:chi\s+)?(?:ha|hanno|possiede|possiedono)\s+(?:un|uno|dei|due|tre)?\s*gatt[oi]\b|\bproprietari\s+di\s+gatti\b|\bcon\s+(?:un\s+)?gatto\b",
        "pet_species",
        ["cat"],
        False,
    ),
    (r"\b(?:senza|non\s+hanno|non\s+ha)\s+(?:animali|cani|gatti)\b", "pet_species", ["none"], False),
    (
        r"\bvive(?:ndo|\s+|nti\s+)?\s*da\s+sol[oae]\b|\bvivono\s+da\s+sol[ie]\b|\bche\s+vivono?\s+soli\b|\bsingle\s+che\s+vivono\s+da\s+sol[oi]\b",
        "household",
        ["alone"],
        False,
    ),
    (r"\bvive(?:\s+in)?\s+(?:coppia|con\s+(?:il|la)\s+partner)\b|\bcoppie\b", "household", ["couple"], False),
    (r"\bfamigli[ae]\b", "household", ["family"], False),
    (r"\b(?:ha|hanno)\s+figli\b|\bgenitori\b|\bmamme\b|\bpapà\b|\bbambini\b", "has_children", ["yes"], False),
    (r"\bsenza\s+figli\b|\bnon\s+ha\s+figli\b", "has_children", ["no"], False),
    (r"\bsingle\b", "relationship_status", ["single"], False),
    (r"\bsposat[oie]\b", "relationship_status", ["married"], False),
    (r"\bin\s+città\b|\bzona\s+urbana\b|\bcittadin[oie]\b", "urbanicity", ["urban"], False),
    (r"\bcampagna\b|\bzona\s+rurale\b", "urbanicity", ["rural"], False),
    (r"\bpratica\s+sport\b|\bsportiv[oie]\b|\bfitness\b", "fitness_active", ["yes"], False),
    (
        r"\broutine\s+(?:di\s+)?(?:skincare|cura\s+della\s+pelle)\b|\bappassionat[oie]\s+di\s+skincare\b",
        "skincare_routine",
        ["extended"],
        False,
    ),
]
AGE_RANGE = re.compile(r"\b(\d{2})\s*(?:-|–|a|e)\s*(\d{2})\s*anni\b", re.I)
UNDER = re.compile(r"\b(?:under|sotto\s+i)\s*(\d{2})\b", re.I)
OVER = re.compile(r"\b(?:over|sopra\s+i)\s*(\d{2})\b", re.I)
GENDER = [(re.compile(r"\bdonn[ae]\b", re.I), "women"), (re.compile(r"\buomin[oi]\b", re.I), "men")]
CONNECTORS = re.compile(
    r"\b(?:e|ed|che|chi|di|il|la|le|i|gli|un|uno|una|persone|utenti|target|pubblico|sia|anche)\b|[,.;:]", re.I
)


def read_intent(text):
    """Recognise lexicon phrases. Returns (constraints, age_range|None, gender|None, unrecognised remainder)."""
    remaining = text or ""
    constraints, seen = [], set()
    for pattern, attribute, values, negate in LEXICON:
        if re.search(pattern, remaining, re.I):
            key = (attribute, tuple(values), negate)
            if key not in seen:
                seen.add(key)
                constraints.append(AudienceConstraint(attribute=attribute, values=values, negate=negate))
            remaining = re.sub(pattern, " ", remaining, flags=re.I)
    age = None
    if match := AGE_RANGE.search(remaining):
        age = (int(match.group(1)), int(match.group(2)))
        remaining = AGE_RANGE.sub(" ", remaining)
    elif match := UNDER.search(remaining):
        age = (18, int(match.group(1)))
        remaining = UNDER.sub(" ", remaining)
    elif match := OVER.search(remaining):
        age = (int(match.group(1)), 65)
        remaining = OVER.sub(" ", remaining)
    gender = None
    for pattern, value in GENDER:
        if pattern.search(remaining):
            gender = value
            remaining = pattern.sub(" ", remaining)
    leftover = " ".join(CONNECTORS.sub(" ", remaining).split())
    return constraints, age, gender, leftover


def merge_constraints(explicit, from_text):
    merged = list(explicit)
    known = {(c.attribute, tuple(c.values), c.negate) for c in merged}
    merged.extend(c for c in from_text if (c.attribute, tuple(c.values), c.negate) not in known)
    return merged


def _precision(constraint, selected_terms):
    """P(person reached satisfies the constraint) when reached through the selected terms, assuming terms are
    independent signals and the person is delivered if any 'include' term matches. Assumption, not a measurement."""
    if constraint.negate:
        return None
    probabilities = []
    for term in selected_terms:
        match = DETAILED_TERMS[term]["match"].get(constraint.attribute)
        if match:
            probabilities.append(sum(match.get(v, 0.0) for v in constraint.values))
    return round(max(probabilities), 2) if probabilities else None


def analyze_targeting(
    request: TargetingAnalyzeRequest, *, applied_to_population=False, reach: ReachSummary | None = None
) -> TargetingReport:
    spec: TargetingSpec = request.targeting
    from_text, age, gender, leftover = read_intent(spec.audience_intent)
    constraints = merge_constraints(spec.constraints, from_text)
    notes = []

    def note(code, severity, message):
        notes.append(TargetingNote(code=code, severity=severity, message=message))

    if age and (spec.age_min, spec.age_max) == (18, 65):
        note(
            "age_from_intent",
            "info",
            f"Dal testo: età {age[0]}-{age[1]}. Imposta età minima e massima per applicarla.",
        )
    if gender and spec.gender == "all":
        note("gender_from_intent", "info", "Dal testo: genere indicato. Imposta il genere per applicarlo.")
    if leftover:
        note(
            "intent_not_understood",
            "warning",
            f"Parti del testo non riconosciute: «{leftover}». Aggiungile come vincoli.",
        )

    included = [t.id for t in spec.detailed if t.mode in {"include", "narrow"}]
    proxies = []
    for constraint in constraints:
        catalog = PERSONA_ATTRIBUTES[constraint.attribute]
        suggested = sorted(
            {
                term
                for value in constraint.values
                for term in SUGGESTED_PROXIES.get((constraint.attribute, value), [])
            }
        )
        selected = [t for t in included if constraint.attribute in DETAILED_TERMS[t]["match"]]
        precision = _precision(constraint, selected)
        proxies.append(
            ProxySuggestion(
                attribute=constraint.attribute,
                values=constraint.values,
                meta_direct=catalog["meta_direct"],
                suggested_terms=suggested,
                selected_terms=selected,
                expected_precision=precision,
            )
        )
        label = catalog["label"]
        if not catalog["meta_direct"]:
            note(
                "not_targetable",
                "warning",
                f"«{label}» non è un'opzione di Ads Manager: si raggiunge solo con proxy"
                + (f" ({', '.join(DETAILED_TERMS[t]['label'] for t in suggested)})" if suggested else "")
                + ", che includono anche chi non ha l'attributo.",
            )
        if not selected and not constraint.negate:
            note(
                "no_proxy_selected",
                "info",
                f"Nessun termine di targeting dettagliato copre «{label}»: nella simulazione il pubblico "
                "consegnato non è filtrato su questo vincolo, solo il bersaglio ideale lo è.",
            )
        elif precision is not None and precision < 0.6:
            note(
                "low_precision",
                "warning",
                f"Con i termini scelti, solo circa il {round(precision * 100)}% di chi vedrebbe l'annuncio ha "
                f"«{label}» (ipotesi, non misura).",
            )

    placements = list(spec.placements) if not spec.advantage_placements else []
    surfaces = {PLACEMENTS[p]["surface"] for p in placements}
    if request.device == "desktop" and surfaces & MOBILE_ONLY_SURFACES:
        note(
            "placement_device",
            "warning",
            "Stories e Reels sono solo mobile: con device desktop non verrebbero consegnati.",
        )
    if (
        "desktop" in spec.device_platforms
        and placements
        and all(PLACEMENTS[p]["surface"] in MOBILE_ONLY_SURFACES for p in placements)
    ):
        note(
            "placement_device",
            "warning",
            "Con i soli placement scelti il desktop non riceverebbe l'annuncio.",
        )
    if not spec.advantage_placements and not spec.placements:
        note("no_placement", "blocking", "Placement manuali selezionati ma nessun placement scelto.")
    if spec.advantage_audience:
        note(
            "advantage_audience",
            "info",
            "Advantage+ audience può raggiungere persone fuori dal targeting: il pubblico consegnato sarà più ampio.",
        )
    if spec.custom_audiences:
        note(
            "custom_audience_assumed",
            "info",
            "I pubblici personalizzati, lookalike e dei fan sono solo descritti: la loro composizione è un'ipotesi.",
        )
    if spec.bid_strategy == "roas_goal":
        note(
            "bid_roas",
            "info",
            "L'offerta ROAS non è modellata: la simulazione non stima il ritorno sulla spesa.",
        )
    if not applied_to_population:
        note(
            "not_applied",
            "info",
            "Il targeting è registrato e interpretato, ma il pannello di persone non è ancora campionato su di esso.",
        )
    if reach is not None:
        _reach_notes(note, reach, constraints, spec)
    return TargetingReport(
        constraints=constraints,
        unrecognized_intent=leftover,
        proxies=proxies,
        notes=notes,
        placements=placements,
        applied_to_population=applied_to_population,
        reach=reach,
    )


def _reach_notes(note, reach, constraints, spec):
    """Notes that need the sampled pool: how much of the delivered audience is the ideal target, and what was ignored."""
    if reach.ideal_share_in_reached is not None and constraints:
        share, base = reach.ideal_share_in_reached, reach.ideal_share_in_base or 0.0
        severity = "warning" if share < 0.5 else "info"
        note(
            "ideal_share",
            severity,
            f"Stima: circa il {round(share * 100)}% di chi vedrebbe l'annuncio rientra nel target ideale "
            f"(nella popolazione di partenza il {round(base * 100)}%). Ipotesi, non misura.",
        )
    if reach.unmodelled_terms:
        note(
            "term_not_modelled",
            "info",
            "Termini di targeting senza effetto modellato sulle persone: "
            + ", ".join(reach.unmodelled_terms)
            + ".",
        )
    ignored = [
        label
        for label, active in (
            ("regioni (solo etichetta, nessuna distribuzione regionale)", bool(spec.regions)),
            ("lingue", bool(spec.languages)),
            ("solo Wi-Fi", spec.wifi_only),
            ("orari", bool(spec.hours)),
            ("giorni della settimana", bool(spec.weekdays)),
            ("cap di frequenza", spec.frequency_cap is not None),
            ("pubblici personalizzati e lookalike", bool(spec.custom_audiences)),
        )
        if active
    ]
    if ignored:
        note(
            "setting_not_modelled",
            "info",
            "Impostazioni registrate ma senza effetto sul pubblico simulato: " + ", ".join(ignored) + ".",
        )
    for warning in reach.audit.warnings:
        note("panel_audit", "warning", f"Controllo del pannello: {warning}.")
