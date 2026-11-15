"""Stage 2 of persona generation: an LLM writes a persona card from a statistical skeleton.

The skeleton (``persona_model``) is turned into plain Italian facts. The writer may add concrete, ordinary detail
(name, city, job, routine, how the person relates to the category and reacts to ads) but may not change a fact.
A deterministic validator checks every card against the skeleton; cards that fail are regenerated, and after the
last attempt replaced by a template card labelled ``source: "template"``. Cards are cached per skeleton so the same
person sees every creative. Nothing here is a measurement: a card is a hypothesis about how such a person could be.
"""

import json
import re
import time
from collections import Counter

import httpx
from pydantic import ValidationError

from .agents import policy_key
from .audience import stable_seed
from .cloud import CloudRuntimeError
from .performance import add_usage, stage_metrics
from .schemas import PersonaCard

PERSONA_PROMPT_VERSION = "persona-writer-v3"
BATCH_SIZE = 8
MAX_ATTEMPTS = 3
USED_LIMIT = 60
SAMPLE_LIMIT = 40

VERTICAL_LABELS = {
    "pet_ecommerce": "cibo e accessori per animali domestici",
    "beauty_skincare": "skincare e bellezza",
    "abbigliamento": "abbigliamento e moda",
}
COUNTRY_NAMES = {"IT": "Italia", "ES": "Spagna", "FR": "Francia", "DE": "Germania"}

SYSTEM_PROMPT = """Scrivi le schede di persone reali e ordinarie che vivono in {country}, partendo SOLO dai fatti forniti per ciascuna.
Non cambiare nessun fatto (età, genere, nucleo, figli, animale, lavoro, zona, dispositivo, piattaforme). Non dire l'età in cifre dentro i testi.
Aggiungi dettagli concreti e verosimili, mai da caricatura: nome e cognome comuni per età e luogo, città coerente con la zona, mestiere o occupazione concreti,
routine tipo, cosa compra davvero nella categoria, cosa guarda su Instagram o Facebook, come reagisce di solito alle pubblicità (cosa lo fa fermare,
cosa lo infastidisce), un paio di abitudini o contraddizioni normali. Scrivi in terza persona, in italiano semplice. Usa una o due frasi brevi per campo, senza ripetere gli stessi fatti.
Non inventare salute, religione, politica, orientamento, origine etnica, né marchi o negozi reali, né prezzi o importi nei testi.
Le persone di una stessa richiesta devono essere molto diverse tra loro: nomi, mestieri e aperture delle schede non si ripetono, e non riutilizzare quelli già usati.
budget_eur_month è quanto spende al mese solo per i prodotti di questa categoria: di solito poche decine di euro, mai più di qualche centinaio.
Non nominare le piattaforme che la persona non usa e non scrivere cifre di denaro nei testi.
Rispondi solo con il JSON dello schema, con una scheda per ogni persona (ref P1, P2, ...)."""

SENSITIVE = re.compile(
    r"\b(malatt\w+|depressi\w+|cancro|tumor\w+|diabet\w+|disabil\w+|"
    r"cattolic\w+|musulman\w+|ebre[oaie]\b|religios\w+|chiesa|preghier\w+|parrocchi\w+|"
    r"gay|lesbic\w+|omosessual\w+|eterosessual\w+|bisessual\w+|transgender|politic\w+)\b",
    re.I,
)
BRANDS = re.compile(
    r"\b(nike|adidas|zara|h&m|hm|amazon|zalando|sephora|apple|samsung|monge|royal canin|purina|pedigree|"
    r"eukanuba|acana|lidl|esselunga|coop|conad|ikea|decathlon|arcaplanet|maxi zoo|zooplus|nivea|garnier|"
    r"l'oreal|loreal|vichy|la roche|kiko|tiktok|netflix|google|youtube|whatsapp|shein|vinted)\b",
    re.I,
)
PRICE = re.compile(r"\d[\d.,]*\s?(?:€|euro\b|eur\b)|€\s?\d", re.I)
NEGATION = re.compile(r"\b(non|senza|nessun\w*|né|mai|niente)\b", re.I)
PET_WORDS = {
    "dog": re.compile(r"\b(cane|cani|cagnolin\w*|cucciol\w*)\b", re.I),
    "cat": re.compile(r"\b(gatt\w+|micio|mici)\b", re.I),
    "other": re.compile(
        r"\b(criceto|coniglio|conigli|pesciolin\w*|tartarugh?\w*|uccellin\w*|pappagall\w*|canarin\w*|furetto|cavi[ae])\b",
        re.I,
    ),
}
CHILD_WORDS = re.compile(r"\b(figli\w*|bambin\w*|bimb\w*)\b", re.I)
ALONE_FORBIDDEN = re.compile(r"\b(coinquilin\w*|vivo con|viviamo|convivo|convivenza|conviven\w*)\b", re.I)
NOT_ALONE_FORBIDDEN = re.compile(r"\bviv\w+ da sol[oa]\b", re.I)
AGE_IN_TEXT = re.compile(r"(?<!da )(?<!per )(?<!circa )\b(\d{2})\s+anni\b", re.I)
STUDENT = re.compile(r"student|universit|scuol|dottorand|laure|master", re.I)
RETIRED = re.compile(r"pension|\bex\b", re.I)
NOT_WORKING_WORDS = re.compile(r"\bstudent\w*|pension\w*|\bex\b", re.I)
BUDGET_CAP = {"low": 250, "mid": 800, "high": 3000}
TEXT_FIELDS = ("bio", "daily_routine", "category_relationship", "social_habits", "ad_reaction_style")

SKELETON_NOISE = {
    "agent_id",
    "population_weight",
    "seed",
    "provenance",
    "assumption_id",
    "evidence_level",
    "profile_version",
    "spec_id",
    "in_ideal_target",
    "category_context",
}


def skeleton_view(profile):
    """Stable content of a skeleton: what defines the person, without bookkeeping, traits rounded."""
    return {
        k: round(v, 1) if isinstance(v, float) else v for k, v in profile.items() if k not in SKELETON_NOISE
    }


def _level(value, low, high, low_text, high_text):
    return high_text if value >= high else low_text if value <= low else None


def describe_profile(profile):
    """The skeleton as plain Italian facts. No numbers except age and minutes; traits become tendencies."""
    woman = profile["gender"] == "women"
    facts = [f"Ha {profile['age']} anni, è {'una donna' if woman else 'un uomo'}."]
    zone = {
        "urban": "in una città",
        "suburban": "in un'area periferica o di provincia",
        "rural": "in campagna",
    }
    where = zone[profile["urbanicity"]] + (f" ({profile['region']})" if profile.get("region") else "")
    household = profile["household"]
    facts.append(
        {
            "alone": f"Vive da {'sola' if woman else 'solo'} {where}.",
            "couple": f"Vive in coppia, senza figli in casa, {where}.",
            "family": f"Vive con la famiglia e con figli {where}.",
            "shared": f"Vive in una casa condivisa (coinquilini o genitori) {where}.",
        }[household]
    )
    if profile["has_children"] == "yes" and household != "family":
        facts.append("Ha figli che non vivono con lei." if woman else "Ha figli che non vivono con lui.")
    if profile["has_children"] == "no":
        facts.append("Non ha figli.")
    facts.append(
        {
            "single": "È single.",
            "partnered": "Ha una relazione stabile.",
            "married": "È sposata." if woman else "È sposato.",
        }[profile["relationship_status"]]
    )
    facts.append(
        {
            "dog": "Ha un cane.",
            "cat": "Ha un gatto.",
            "other": "Ha un piccolo animale domestico che non è né un cane né un gatto.",
            "none": "Non ha animali domestici.",
        }[profile["pet_species"]]
    )
    facts.append(
        {
            "student": "Studia.",
            "employed": "Lavora come dipendente.",
            "self_employed": "Lavora in proprio.",
            "retired": "È in pensione.",
            "not_working": "Al momento non ha un lavoro.",
        }[profile["occupation"]]
    )
    facts.append(
        {
            "low": "Il suo reddito è basso.",
            "mid": "Il suo reddito è nella media.",
            "high": "Il suo reddito è alto.",
        }[profile["income_band"]]
    )
    facts.append(
        {
            "none": "Non ha una routine di cura della pelle.",
            "basic": "Ha una routine di cura della pelle essenziale.",
            "extended": "Ha una routine di cura della pelle curata e articolata.",
        }[profile["skincare_routine"]]
    )
    facts.append(
        "Fa sport con regolarità." if profile["fitness_active"] == "yes" else "Non fa sport con regolarità."
    )
    platforms = [
        n
        for n, used in (("Instagram", profile["uses_instagram"]), ("Facebook", profile["uses_facebook"]))
        if used
    ]
    device = "un iPhone" if profile["device_os"] == "ios" else "uno smartphone Android"
    facts.append(
        f"Usa {' e '.join(platforms)} da {device}, circa {profile['social_minutes_per_day']} minuti al giorno"
        + (" e a volte dal computer." if profile["desktop_user"] else ".")
    )
    unused = [
        n
        for n, on in (("Instagram", profile["uses_instagram"]), ("Facebook", profile["uses_facebook"]))
        if not on
    ]
    if unused:
        facts.append(f"Non usa {unused[0]}.")
    tendencies = [
        _level(
            profile["budget_sensitivity"],
            0.3,
            0.7,
            "bada poco al prezzo",
            "è molto attenta al prezzo" if woman else "è molto attento al prezzo",
        ),
        _level(
            profile["advertising_literacy"],
            0.3,
            0.7,
            "si lascia prendere dalle pubblicità",
            "riconosce al volo le pubblicità",
        ),
        _level(profile["trust"], 0.3, 0.7, "diffida degli annunci", "si fida facilmente degli annunci"),
        _level(
            profile["repeat_tolerance"],
            0.3,
            0.7,
            "si infastidisce se rivede la stessa pubblicità",
            "non si fa problemi a rivedere la stessa pubblicità",
        ),
        _level(
            profile["category_affinity"],
            0.3,
            0.7,
            "la categoria dell'annuncio la interessa poco"
            if woman
            else "la categoria dell'annuncio lo interessa poco",
            "la categoria dell'annuncio la interessa molto"
            if woman
            else "la categoria dell'annuncio lo interessa molto",
        ),
        _level(
            profile["purchase_need"],
            0.3,
            0.7,
            "al momento non ha bisogno di comprare nulla in questa categoria",
            "ha bisogno di comprare in questa categoria",
        ),
        "compra online con regolarità" if profile["online_shopper"] else "compra raramente online",
    ]
    tendencies = [t for t in tendencies if t]
    if tendencies:
        facts.append("Tendenze: " + "; ".join(tendencies) + ".")
    return facts


CLAUSE = re.compile(r"[.;!?\n,:]|\s(?:ma|però|mentre|anche se)\s", re.I)
ECHO_FIELDS = {
    "echo_age": "age",
    "echo_gender": "gender",
    "echo_household": "household",
    "echo_has_children": "has_children",
    "echo_pet_species": "pet_species",
    "echo_device_os": "device_os",
}
# A fact the card leaves out is not a contradiction: the facts reach the reaction prompt anyway (``card["facts"]``).
# An omission blocks a card only where the attribute is what the category is about.
OMISSIONS = {"animale_mancante", "figli_mancanti", "piattaforma_mancante"}
CENTRAL = {"pet_ecommerce": {"animale_mancante"}}


def _find(text, pattern):
    """The first clause where ``pattern`` appears without a negation in the same clause, or None.

    «Instagram non lo usa» and «non usa Instagram» are both negated; «non esce mai, ma ha un cane» is not."""
    for clause in CLAUSE.split(text):
        if pattern.search(clause) and not NEGATION.search(clause):
            return clause.strip()
    return None


def _mentions(text, pattern):
    return _find(text, pattern) is not None


def card_problems(card, profile, forbidden=(), details=None):
    """Everything found when comparing the card with its skeleton, contradictions and omissions alike.

    ``details`` (a dict) receives the offending clause for the problems that have one."""
    problems = []
    details = {} if details is None else details

    def flag(code, clause=None):
        problems.append(code)
        if clause:
            details.setdefault(code, clause[:160])

    for field, source in ECHO_FIELDS.items():
        if getattr(card, field) != profile[source]:
            problems.append(f"fatto_cambiato:{field}")
    text = " ".join(
        [card.job, card.city, *(getattr(card, f) for f in TEXT_FIELDS), *card.pain_points, *card.quirks]
    )
    if any(int(m.group(1)) != profile["age"] for m in AGE_IN_TEXT.finditer(text)):
        problems.append("eta_incoerente")
    for code, pattern in (
        ("attributo_sensibile", SENSITIVE),
        ("marchio_reale", BRANDS),
        ("prezzo_nel_testo", PRICE),
    ):
        match = pattern.search(text)
        if match:
            flag(code, match.group(0))
    if any(re.search(rf"\b{re.escape(b)}\b", text, re.I) for b in forbidden if b):
        flag("marchio_reale")
    species = profile["pet_species"]
    for kind, pattern in PET_WORDS.items():
        clause = _find(text, pattern)
        if kind == species and not clause:
            flag("animale_mancante")
        if kind != species and clause:
            flag("animale_incoerente", clause)
    household = profile["household"]
    if household == "alone" and _mentions(text, ALONE_FORBIDDEN):
        flag("nucleo_incoerente", _find(text, ALONE_FORBIDDEN))
    if household != "alone" and NOT_ALONE_FORBIDDEN.search(text):
        flag("nucleo_incoerente", NOT_ALONE_FORBIDDEN.search(text).group(0))
    children = _find(text, CHILD_WORDS)
    if profile["has_children"] == "yes" and not children:
        flag("figli_mancanti")
    if profile["has_children"] == "no" and children:
        flag("figli_incoerenti", children)
    for platform, used in (("instagram", profile["uses_instagram"]), ("facebook", profile["uses_facebook"])):
        pattern = re.compile(platform, re.I)
        if not used and _mentions(text, pattern):
            flag(f"piattaforma_non_usata:{platform}", _find(text, pattern))
        if (
            used
            and not pattern.search(card.social_habits)
            and not (profile["uses_instagram"] and profile["uses_facebook"])
        ):
            problems.append(f"piattaforma_mancante:{platform}")
    occupation = profile["occupation"]
    if occupation == "student" and not STUDENT.search(card.job + " " + card.bio):
        problems.append("occupazione_incoerente")
    if occupation == "retired" and not RETIRED.search(card.job + " " + card.bio):
        problems.append("occupazione_incoerente")
    if occupation in {"employed", "self_employed"} and NOT_WORKING_WORDS.search(card.job):
        problems.append("occupazione_incoerente")
    if card.budget_eur_month > BUDGET_CAP[profile["income_band"]]:
        problems.append("budget_incoerente")
    return sorted(set(problems))


def _blocking(problem, vertical):
    code = problem.split(":")[0]
    return code not in OMISSIONS or code in CENTRAL.get(vertical, ())


def validate_card(card, profile, forbidden=(), vertical=None, details=None):
    """What makes the card unacceptable (empty list = acceptable): contradictions, and omissions central to the category."""
    return [p for p in card_problems(card, profile, forbidden, details) if _blocking(p, vertical)]


def card_omissions(card, profile, vertical=None):
    """Facts the card does not mention and that do not block it. Reported, never hidden."""
    return [p for p in card_problems(card, profile) if not _blocking(p, vertical)]


def _tokens(text):
    return set(re.findall(r"\w{4,}", text.casefold()))


def _opening(text):
    return " ".join(re.findall(r"\w+", text.casefold())[:3])


def duplicate_problem(card, accepted):
    """A card too close to one already accepted: same first name, same opening, or near-identical biography."""
    first = card.name.split()[0].casefold()
    tokens = _tokens(card.bio)
    for other in accepted:
        if other["name"].split()[0].casefold() == first:
            return "nome_duplicato"
        if _opening(other["bio"]) == _opening(card.bio):
            return "apertura_duplicata"
        union = tokens | _tokens(other["bio"])
        if union and len(tokens & _tokens(other["bio"])) / len(union) > 0.55:
            return "bio_simile"
    return None


def template_card(profile, ordinal):
    """Deterministic fallback with no invented detail. Labelled so nobody mistakes it for a written persona."""
    facts = describe_profile(profile)
    return {
        "ref": f"T{ordinal}",
        "name": f"Persona {ordinal}",
        "city": profile.get("region", "non specificata"),
        "job": {
            "student": "studente",
            "employed": "dipendente",
            "self_employed": "lavoratore autonomo",
            "retired": "pensionato",
            "not_working": "senza lavoro",
        }[profile["occupation"]],
        "bio": " ".join(facts[:4]),
        "daily_routine": "Non descritta.",
        "category_relationship": " ".join(
            f for f in facts if "animal" in f or "cane" in f or "gatto" in f or "pelle" in f
        )
        or "Non descritta.",
        "social_habits": next(f for f in facts if f.startswith("Usa ")),
        "ad_reaction_style": next((f for f in facts if f.startswith("Tendenze")), "Non descritta."),
        "pain_points": [],
        "quirks": [],
        "budget_eur_month": 0,
    }


HINTS = {
    "prezzo_nel_testo": "non scrivere cifre di denaro nei testi",
    "attributo_sensibile": "non parlare di salute, religione, politica o orientamento",
    "marchio_reale": "non nominare marchi o negozi reali",
    "animale_incoerente": "non attribuirle animali diversi da quello indicato nei fatti",
    "animale_mancante": "nomina l'animale indicato nei fatti",
    "nucleo_incoerente": "rispetta con chi vive, come indicato nei fatti",
    "figli_mancanti": "nomina i figli indicati nei fatti",
    "figli_incoerenti": "non attribuirle figli: i fatti dicono che non ne ha",
    "eta_incoerente": "non scrivere l'età nei testi",
    "occupazione_incoerente": "rispetta l'occupazione indicata nei fatti",
    "budget_incoerente": "budget_eur_month deve essere più basso, coerente con il reddito",
    "nome_duplicato": "scegli un nome diverso da quelli già usati",
    "apertura_duplicata": "comincia la bio in modo diverso",
    "bio_simile": "scrivi una bio diversa dalle altre",
    "scheda_mancante": "compila tutti i campi rispettando le lunghezze",
}


def hints_for(problems, details=None):
    """What to tell the model about a rejected card, so the retry is not a blind second draw."""
    out = []
    for problem in problems:
        code = problem.split(":")[0]
        quoted = (details or {}).get(problem)
        if quoted:
            out.append(f"avevi scritto «{quoted}»")
        if code == "fatto_cambiato":
            out.append("ripeti esattamente i fatti nei campi echo")
        elif code == "piattaforma_non_usata":
            out.append("non nominare le piattaforme che non usa")
        elif code == "piattaforma_mancante":
            out.append("in social_habits nomina la piattaforma che usa")
        elif code in HINTS:
            out.append(HINTS[code])
    return list(dict.fromkeys(out))


def strip_fences(raw):
    """Some local models wrap the JSON in a Markdown code fence even under a schema constraint."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return text


def batch_schema(count):
    """The schema the model fills. The ``echo_*`` facts are not asked for: the code knows them and writes them."""
    card = PersonaCard.model_json_schema()
    card.pop("title", None)
    card["properties"] = {k: v for k, v in card["properties"].items() if k not in ECHO_FIELDS}
    card["required"] = [k for k in card["required"] if k not in ECHO_FIELDS]
    card["properties"]["ref"] = {"type": "string", "enum": [f"P{i + 1}" for i in range(count)]}
    return {
        "type": "object",
        "properties": {"cards": {"type": "array", "minItems": count, "maxItems": count, "items": card}},
        "required": ["cards"],
        "additionalProperties": False,
    }


def user_prompt(profiles, vertical, used, corrections=None):
    lines = [f"Categoria di riferimento: {VERTICAL_LABELS[vertical]}."]
    if used["names"] or used["jobs"] or used["openings"]:
        lines.append(
            "Già usati, da non riutilizzare. Nomi: "
            + (", ".join(used["names"][-USED_LIMIT:]) or "nessuno")
            + ". Mestieri: "
            + (", ".join(used["jobs"][-USED_LIMIT:]) or "nessuno")
            + ". Aperture delle bio: "
            + (" | ".join(used["openings"][-USED_LIMIT:]) or "nessuna")
            + "."
        )
    lines.append("Persone da scrivere:")
    for index, profile in enumerate(profiles, 1):
        lines.append(f"P{index}\n" + "\n".join(f"- {fact}" for fact in describe_profile(profile)))
        lines.append(
            f"- budget_eur_month: intero tra 0 e {BUDGET_CAP[profile['income_band']]}, solo per questa categoria."
        )
        occupation = {
            "student": "job deve indicare studente; bio coerente con lo studio",
            "retired": "job deve indicare pensionato, eventualmente con il mestiere precedente",
            "employed": "job deve indicare un mestiere da dipendente, non studente o pensionato",
            "self_employed": "job deve indicare un mestiere autonomo, non studente o pensionato",
            "not_working": "job deve indicare che attualmente non lavora",
        }[profile["occupation"]]
        lines.append("- Occupazione: " + occupation + ".")
        previous = (corrections or {}).get(profile["agent_id"]) or ([], {})
        hints = hints_for(*previous)
        if hints:
            lines.append("Correggi rispetto alla versione precedente: " + "; ".join(hints) + ".")
    return "\n".join(lines)


class PersonaWriter:
    def __init__(self, repo, client, digest, vertical, country="IT", brand="", batch_size=None):
        self.repo, self.client, self.digest = repo, client, digest or "unknown-runtime"
        self.vertical, self.country, self.brand = vertical, country, brand
        self.batch_size = batch_size or getattr(client, "card_batch_size", BATCH_SIZE)
        self.system = SYSTEM_PROMPT.format(country=COUNTRY_NAMES.get(country, country))
        self.rejected_samples = []  # the rejected texts, kept for diagnosis only (never stored with the run)
        self.timings = []
        self.performance = stage_metrics()

    def key(self, profile):
        return policy_key(
            {
                "kind": "persona-card",
                "skeleton": skeleton_view(profile),
                "vertical": self.vertical,
                "country": self.country,
                "brand": self.brand,
                "writer": PERSONA_PROMPT_VERSION,
                "system": self.system,
                "provider": self.client.provider,
                "model": self.client.model,
                "digest": self.digest,
            }
        )

    def _call(self, group, used, attempt, corrections=None):
        schema = batch_schema(len(group))
        seed = stable_seed(
            self.vertical, self.country, PERSONA_PROMPT_VERSION, attempt, *(p["agent_id"] for p in group)
        )
        result = self._generate(
            self.system,
            user_prompt(group, self.vertical, used, corrections),
            schema,
            temperature=0.9,
            seed=seed % 2**31,
            max_tokens=700 * len(group) + 200,
        )
        data = json.loads(strip_fences(result["raw"]))
        cards = {}
        refs = {f"P{i + 1}": profile for i, profile in enumerate(group)}
        for item in data["cards"]:
            try:
                profile = refs.get(item.get("ref")) if isinstance(item, dict) else None
                if profile is None:
                    continue
                card = PersonaCard.model_validate(
                    {**item, **{field: profile[source] for field, source in ECHO_FIELDS.items()}}
                )
            except ValidationError:
                continue  # that person is reported as missing and retried
            if card.ref in {f"P{i + 1}" for i in range(len(group))}:
                cards[card.ref] = card
        return cards, result

    def _generate(self, *args, **kwargs):
        start = time.monotonic()
        self.performance["calls"] += 1
        try:
            result = self.client.generate(*args, **kwargs)
            add_usage(self.performance, result)
            self.timings.append(
                {
                    k: result.get(k)
                    for k in ("seconds", "prompt_tokens", "tokens", "prompt_seconds", "output_seconds")
                }
            )
            return result
        finally:
            self.performance["seconds"] += time.monotonic() - start

    def compatible(self, card, profile, accepted=()):
        try:
            if card.get("source") == "template":
                expected = template_card(profile, 0)
                return card.get("writer_key") == self.key(profile) and all(
                    card.get(k) == value for k, value in expected.items() if k not in {"name", "ref"}
                )
            parsed = PersonaCard.model_validate({k: card[k] for k in PersonaCard.model_fields})
            return (
                card.get("writer_key") == self.key(profile)
                and not validate_card(parsed, profile, [self.brand], self.vertical)
                and (card.get("source") == "template" or not duplicate_problem(parsed, accepted))
            )
        except (ValueError, KeyError, TypeError):
            return False

    def _repair(self, profile, previous, problems, attempt):
        fields = ["budget_eur_month"] if problems == ["budget_incoerente"] else ["job", "bio"]
        properties = PersonaCard.model_json_schema()["properties"]
        schema = {
            "type": "object",
            "properties": {k: properties[k] for k in fields},
            "required": fields,
            "additionalProperties": False,
        }
        if fields == ["budget_eur_month"]:
            schema["properties"]["budget_eur_month"]["maximum"] = BUDGET_CAP[profile["income_band"]]
        result = self._generate(
            self.system,
            user_prompt([profile], self.vertical, {"names": [], "jobs": [], "openings": []})
            + "\nCorreggi solo i campi richiesti dello schema. Scheda precedente:\n"
            + json.dumps(previous, ensure_ascii=False),
            schema,
            temperature=0.9,
            seed=stable_seed(profile["agent_id"], PERSONA_PROMPT_VERSION, attempt) % 2**31,
            max_tokens=900,
        )
        patch = json.loads(strip_fences(result["raw"]))
        if not isinstance(patch, dict) or set(patch) != set(fields):
            raise ValueError("Campi della correzione non validi")
        return PersonaCard.model_validate({**previous, **patch}), result

    def write(self, profiles, progress=None, *, performance=None, state=None):
        """Write missing cards. ``state`` and performance can be checkpointed by ``progress(done, total)``."""
        if any("household" not in p for p in profiles):
            raise ValueError(
                "Le schede richiedono un pannello mirato (targeting): profili senza attributi di vita"
            )
        start = time.monotonic()
        self.performance = stage_metrics(performance)
        stats = self.performance
        state = {} if state is None else state
        rejected, omitted = Counter(), Counter()
        cards, pending, accepted = {}, [], []
        written_count = 0
        for profile in profiles:
            key = self.key(profile)
            stored = self.repo.get_card(key)
            if stored and self.compatible(stored["card"], profile, accepted):
                card = stored["card"]
                cards[profile["agent_id"]] = card
                if card["source"] == "llm":
                    accepted.append(card)
            else:
                pending.append((profile, key))
        cached = len(cards)
        stats["cache_hits"] += cached
        used = {"names": [], "jobs": [], "openings": []}
        for card in accepted:
            self._remember(used, card)

        def notify():
            if progress:
                progress(len(cards), len(profiles))

        notify()
        while pending:
            eligible = [(p, k) for p, k in pending if state.get(k, {}).get("attempts", 0) < MAX_ATTEMPTS]
            if not eligible:
                break
            failed = []
            for offset in range(0, len(eligible), self.batch_size):
                group = eligible[offset : offset + self.batch_size]
                # A repair uses one card's schema; full generations retain the existing small batches.
                groups = (
                    [[item] for item in group]
                    if any(state.get(k, {}).get("repair") for _, k in group)
                    else [group]
                )
                for batch in groups:
                    previous = state.get(batch[0][1], {})
                    repair = len(batch) == 1 and previous.get("repair")
                    attempt = max(state.get(k, {}).get("attempts", 0) for _, k in batch)
                    for _, key in batch:
                        state.setdefault(key, {})["attempts"] = state.get(key, {}).get("attempts", 0) + 1
                    stats["attempts"] += len(batch)
                    if repair:
                        stats["corrections"] += 1
                    try:
                        if repair:
                            card, result = self._repair(
                                batch[0][0], previous["card"], previous["problems"], attempt
                            )
                            generated = {"P1": card}
                        else:
                            corrections = {
                                p["agent_id"]: (state.get(k, {}).get("problems", []), {}) for p, k in batch
                            }
                            generated, result = self._call([p for p, _ in batch], used, attempt, corrections)
                        for index, (profile, key) in enumerate(batch, 1):
                            card = generated.get(f"P{index}")
                            problems = (
                                ["scheda_mancante"]
                                if card is None
                                else validate_card(card, profile, [self.brand], self.vertical)
                            )
                            duplicate = duplicate_problem(card, accepted) if card is not None else None
                            if duplicate:
                                problems = sorted(set(problems + [duplicate]))
                            if problems:
                                stats["rejected"] += 1
                                rejected.update(problems)
                                partial = problems in (["budget_incoerente"], ["occupazione_incoerente"])
                                state[key].update(
                                    card=card.model_dump() if card else None,
                                    problems=problems,
                                    repair=partial,
                                )
                                if len(self.rejected_samples) < SAMPLE_LIMIT:
                                    self.rejected_samples.append(
                                        {
                                            "agent_id": profile["agent_id"],
                                            "attempt": attempt,
                                            "problems": problems,
                                            "card": card.model_dump() if card else None,
                                        }
                                    )
                                failed.append((profile, key))
                            else:
                                omitted.update(card_omissions(card, profile, self.vertical))
                                stored = self._store(key, profile, card.model_dump(), "llm", result, attempt)
                                cards[profile["agent_id"]] = stored
                                accepted.append(stored)
                                self._remember(used, stored)
                                written_count += 1
                    except (CloudRuntimeError, httpx.ConnectError):
                        stats["errors"] += 1
                        # Availability failures do not exhaust a person's validation/repair budget.
                        for _, key in batch:
                            state[key]["attempts"] -= 1
                        raise
                    except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
                        stats["errors"] += 1
                        stats["rejected"] += len(batch)
                        rejected[f"risposta_non_valida:{type(exc).__name__}"] += len(batch)
                        for _, key in batch:
                            state[key]["repair"] = False
                        failed.extend(batch)
                    finally:
                        notify()
            exhausted = [
                (p, k)
                for p, k in pending
                if state.get(k, {}).get("attempts", 0) >= MAX_ATTEMPTS and p["agent_id"] not in cards
            ]
            pending = list({k: (p, k) for p, k in failed + exhausted}.values())
        for ordinal, (profile, key) in enumerate(pending, 1):
            cards[profile["agent_id"]] = self._store(
                key, profile, template_card(profile, ordinal), "template", None, MAX_ATTEMPTS
            )
            stats["fallback"] += 1
        notify()
        sources = Counter(c["source"] for c in cards.values())
        report = {
            **stats,
            "writer_version": PERSONA_PROMPT_VERSION,
            "provider": self.client.provider,
            "model": self.client.model,
            "personas": len(profiles),
            "from_cache": cached,
            "written_by_llm": written_count,
            "written": written_count,
            "template_fallback": sources["template"],
            "rejected_reasons": dict(rejected),
            "accepted_with_omissions": dict(omitted),
            "wall_seconds": round(time.monotonic() - start, 2),
            "evidence": "hypothesis",
            "diversity": card_diversity(list(cards.values())),
        }
        return {p["agent_id"]: cards[p["agent_id"]] for p in profiles}, report

    @staticmethod
    def _remember(used, card):
        used["names"].append(card["name"].split()[0])
        used["jobs"].append(card["job"])
        used["openings"].append(_opening(card["bio"]))

    def _store(self, key, profile, card, source, result, attempt):
        stored = {
            **card,
            "source": source,
            "facts": describe_profile(profile),
            "writer_version": PERSONA_PROMPT_VERSION,
            "writer_key": key,
            "provider": self.client.provider,
            "model": self.client.model,
            "digest": self.digest,
            "attempt": attempt,
        }
        self.repo.save_card(
            key, {"kind": "persona-card", "digest": self.digest, "card": stored, "model": self.client.model}
        )
        return stored


def card_diversity(cards):
    """Descriptive diversity of written cards (templates excluded). Not a realism measure."""
    written = [c for c in cards if c["source"] == "llm"]
    if not written:
        return {"written": 0, "distinct_first_names": 0, "distinct_jobs": 0, "distinct_openings": 0}
    return {
        "written": len(written),
        "distinct_first_names": len({c["name"].split()[0].casefold() for c in written}),
        "distinct_jobs": len({c["job"].casefold() for c in written}),
        "distinct_openings": len({_opening(c["bio"]) for c in written}),
    }
