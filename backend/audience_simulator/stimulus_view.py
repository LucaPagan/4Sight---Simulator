"""What a person actually sees of an ad, and the situation in which they see it.

An ad is never read in full: in a feed the viewer gets the picture, the first words of the caption and a button, and
only reads on if something stops them. ``glance`` is what is visible at a first look for each placement; ``if_you_stop``
is what a person reads after stopping; ``if_you_click`` is the landing page and is only known after a click. The
situation (moment of the day, activity, mood, how many times the ad was already seen) is derived deterministically
from the seed and the person, and does not depend on the creative, so creatives are compared on the same person in the
same moment. All weights below are declared assumptions.
"""

import numpy as np

from .audience import stable_seed
from .meta_catalog import MOBILE_ONLY_SURFACES, PLACEMENTS

# How many characters of the caption are visible before "…altro" (declared assumptions per surface).
CAPTION_CHARS = {
    "feed": 125,
    "reels": 70,
    "in_app": 90,
    "inbox": 60,
    "stories": 0,
    "explore": 0,
    "marketplace": 0,
    "right_column": 0,
}
# Relative share of impressions per placement (declared assumption), used to pick where a person sees the ad.
PLACEMENT_WEIGHTS = {
    "instagram_feed": 0.24,
    "instagram_stories": 0.14,
    "instagram_reels": 0.14,
    "instagram_explore": 0.04,
    "instagram_profile_feed": 0.02,
    "facebook_feed": 0.2,
    "facebook_stories": 0.05,
    "facebook_reels": 0.06,
    "facebook_marketplace": 0.03,
    "facebook_right_column": 0.02,
    "audience_network": 0.04,
    "messenger_inbox": 0.02,
}
SLOTS = ("first", "repeat", "saturated")
FREQUENCY = {
    "first": "È la prima volta che vedi questo annuncio.",
    "repeat": "Hai già visto questo annuncio un paio di volte negli ultimi giorni.",
    "saturated": "Hai già visto questo annuncio molte volte negli ultimi giorni (più di quattro).",
}
REGIMES = {
    "ordinary": "",
    "black_week": "È la settimana prima del Black Friday: ci sono molte offerte in giro.",
    "black_friday": "Oggi è il Black Friday.",
    "post_black_friday": "È il giorno dopo il Black Friday.",
    "cyber_monday": "Oggi è il Cyber Monday.",
}
TASKS = {
    "casual_scrolling": "Stai scorrendo senza uno scopo preciso.",
    "product_research": "Stai cercando un prodotto di cui hai bisogno.",
    "comparison_shopping": "Stai confrontando prodotti e prezzi prima di comprare.",
}
MOMENTS = [
    ("morning", "al mattino"),
    ("lunch", "all'ora di pranzo"),
    ("afternoon", "nel pomeriggio"),
    ("evening", "la sera dopo cena"),
    ("night", "a tarda sera, prima di dormire"),
]
MOMENT_WEIGHTS = {
    "default": [0.15, 0.22, 0.13, 0.35, 0.15],
    "retired": [0.30, 0.15, 0.30, 0.20, 0.05],
    "student": [0.12, 0.20, 0.18, 0.30, 0.20],
}
ACTIVITIES = {
    "morning": {"urban": "sei sul bus o in metro", "other": "stai bevendo il caffè"},
    "lunch": {"urban": "sei in pausa pranzo", "other": "sei in pausa pranzo"},
    "afternoon": {"urban": "hai un momento libero", "other": "hai un momento libero"},
    "evening": {"urban": "sei sul divano", "other": "sei sul divano"},
    "night": {"urban": "sei a letto", "other": "sei a letto"},
}
MOODS = ["tranquillo", "stanco", "annoiato", "di fretta", "di buon umore"]
MOOD_WEIGHTS = [0.3, 0.2, 0.2, 0.15, 0.15]
FALLBACK_VISUAL = "(nessuna descrizione dell'immagine disponibile: non inventarla)"


def _truncate(text, limit):
    text = " ".join(text.split())
    if limit == 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "… altro"


def stimulus(creative, placement, device, brand):
    """Split a creative into what is visible at a glance, what is read after stopping and what only follows a click."""
    info = PLACEMENTS[placement]
    surface = info["surface"]
    visual = creative.get("visual_description") or FALLBACK_VISUAL
    caption = creative.get("primary_text", "")
    seen_caption = _truncate(caption, CAPTION_CHARS[surface])
    glance = {
        "inserzionista": f"Sponsorizzato · {brand}",
        "formato": "video" if surface == "reels" else creative.get("format", "immagine"),
        "visual": visual,
    }
    headline = creative.get("headline", "")
    if surface == "stories":
        glance["testo_sul_fotogramma"] = headline
    elif surface in {"marketplace", "right_column"}:
        glance["titolo"] = headline
        if creative.get("price_text"):
            glance["prezzo"] = creative["price_text"]
    else:
        if seen_caption:
            glance["testo"] = seen_caption
        if (info["platform"] == "facebook" and surface == "feed") or surface in {"in_app", "inbox"}:
            glance["titolo"] = headline
    if surface not in {"explore", "right_column", "marketplace"}:
        glance["pulsante"] = creative.get("cta", "")
    read = {}
    if "titolo" not in glance and creative.get("headline"):
        read["titolo"] = creative["headline"]
    if caption and (not seen_caption or seen_caption != " ".join(caption.split())):
        read["testo_completo"] = " ".join(caption.split())
    if creative.get("offer"):
        read["offerta"] = creative["offer"]
    if creative.get("price_text") and "prezzo" not in glance:
        read["prezzo"] = creative["price_text"]
    click = {}
    if creative.get("landing_page_summary"):
        click["pagina_di_destinazione"] = creative["landing_page_summary"]
    return {
        "dove": f"{info['label']} da {'smartphone' if device == 'mobile' else 'computer'}",
        "al_primo_sguardo": glance,
        "se_ti_fermi_e_leggi": read,
        "dopo_il_click": click,
    }


def exposure_placement(profile, brief):
    """The placement where this person sees the ad: from the delivered placements they can actually be reached on."""
    from .persona_model import delivered_placements

    targeting = brief.targeting
    if targeting is None:
        return brief.placement
    options = [
        p
        for p in delivered_placements(targeting, brief.device)
        if (PLACEMENTS[p]["platform"] == "instagram" and profile["uses_instagram"])
        or (PLACEMENTS[p]["platform"] in {"facebook", "messenger"} and profile["uses_facebook"])
        or PLACEMENTS[p]["platform"] == "audience_network"
    ]
    if not options:
        raise ValueError("Nessun placement raggiungibile per questa persona")
    weights = np.array([PLACEMENT_WEIGHTS[p] for p in options])
    rng = np.random.default_rng(stable_seed(brief.seed, profile["agent_id"], "placement"))
    return options[int(rng.choice(len(options), p=weights / weights.sum()))]


def situation(profile, brief, slot, regime):
    """Moment, activity, mood and frequency memory. Independent of the creative: same person, same moment."""
    rng = np.random.default_rng(stable_seed(brief.seed, profile["agent_id"], slot, regime, "situation"))
    key = (
        "retired"
        if profile.get("occupation") == "retired"
        else "student"
        if profile.get("occupation") == "student"
        else "default"
    )
    moment, moment_text = MOMENTS[int(rng.choice(len(MOMENTS), p=MOMENT_WEIGHTS[key]))]
    mood = MOODS[int(rng.choice(len(MOODS), p=MOOD_WEIGHTS))]
    urban = "urban" if profile.get("urbanicity") == "urban" else "other"
    familiarity = profile.get("brand_familiarity", 0.0)
    known = (
        "Conosci già questa marca."
        if familiarity >= 0.66
        else "Hai sentito nominare questa marca."
        if familiarity >= 0.33
        else "Non conosci questa marca."
    )
    return {
        "momento": moment_text,
        "attivita": ACTIVITIES[moment][urban],
        "umore": mood,
        "scopo": TASKS[brief.browsing_task],
        "frequenza": FREQUENCY[slot],
        "marca": known,
        "periodo": REGIMES.get(regime, ""),
        "moment_code": moment,
    }


def placement_is_mobile_only(placement):
    return PLACEMENTS[placement]["surface"] in MOBILE_ONLY_SURFACES
