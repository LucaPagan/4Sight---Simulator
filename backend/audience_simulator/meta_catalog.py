"""What Meta Ads Manager lets an advertiser pick, and how each pick relates to a person's real attributes.

Two layers matter. The advertiser has an *intent* ("people who own a dog and live alone") expressed on
person attributes. Meta only offers *proxies* (interests, behaviours, demographics) and delivers to everyone
the proxy matches, so the people reached are not the people intended. ``match`` below states, for each proxy,
how likely a person reached through it has each attribute value. These numbers are declared assumptions, not
measurements: every consumer must label them ``assumption`` and never present them as observed.
"""

from typing import Any

PLACEMENTS: dict[str, dict[str, Any]] = {
    "instagram_feed": {"platform": "instagram", "surface": "feed", "label": "Instagram Feed"},
    "instagram_stories": {"platform": "instagram", "surface": "stories", "label": "Instagram Stories"},
    "instagram_reels": {"platform": "instagram", "surface": "reels", "label": "Instagram Reels"},
    "instagram_explore": {"platform": "instagram", "surface": "explore", "label": "Instagram Explore"},
    "instagram_profile_feed": {
        "platform": "instagram",
        "surface": "feed",
        "label": "Feed del profilo Instagram",
    },
    "facebook_feed": {"platform": "facebook", "surface": "feed", "label": "Facebook Feed"},
    "facebook_stories": {"platform": "facebook", "surface": "stories", "label": "Facebook Stories"},
    "facebook_reels": {"platform": "facebook", "surface": "reels", "label": "Facebook Reels"},
    "facebook_marketplace": {
        "platform": "facebook",
        "surface": "marketplace",
        "label": "Facebook Marketplace",
    },
    "facebook_right_column": {
        "platform": "facebook",
        "surface": "right_column",
        "label": "Colonna destra di Facebook",
        "desktop_only": True,
    },
    "audience_network": {"platform": "audience_network", "surface": "in_app", "label": "Audience Network"},
    "messenger_inbox": {"platform": "messenger", "surface": "inbox", "label": "Posta in arrivo di Messenger"},
}
# Surfaces that only exist full-screen on a phone.
MOBILE_ONLY_SURFACES = {"stories", "reels"}

# Person attributes the advertiser can constrain. ``meta_direct`` is True when Meta exposes the attribute as a
# targeting option; otherwise it can only be approximated through proxies.
PERSONA_ATTRIBUTES: dict[str, dict[str, Any]] = {
    "household": {
        "values": ["alone", "couple", "family", "shared"],
        "label": "Composizione del nucleo",
        "meta_direct": False,
    },
    "has_children": {"values": ["yes", "no"], "label": "Ha figli", "meta_direct": True},
    "pet_species": {
        "values": ["dog", "cat", "other", "none"],
        "label": "Animale domestico",
        "meta_direct": False,
    },
    "relationship_status": {
        "values": ["single", "partnered", "married"],
        "label": "Stato civile",
        "meta_direct": True,
    },
    "urbanicity": {"values": ["urban", "suburban", "rural"], "label": "Zona", "meta_direct": False},
    "skincare_routine": {
        "values": ["none", "basic", "extended"],
        "label": "Routine di cura della pelle",
        "meta_direct": False,
    },
    "fitness_active": {"values": ["yes", "no"], "label": "Pratica sport", "meta_direct": False},
}

# Meta-style detailed targeting terms. ``match`` maps attribute -> value -> P(person reached has the value).
# Assumptions: wide bands on purpose; they will be refined when real delivery data exists.
DETAILED_TERMS: dict[str, dict[str, Any]] = {
    "interest:dogs": {
        "kind": "interest",
        "label": "Interesse: Cani",
        "match": {"pet_species": {"dog": 0.55, "cat": 0.08, "other": 0.04, "none": 0.33}},
    },
    "interest:cats": {
        "kind": "interest",
        "label": "Interesse: Gatti",
        "match": {"pet_species": {"cat": 0.55, "dog": 0.08, "other": 0.04, "none": 0.33}},
    },
    "interest:pet_food": {
        "kind": "interest",
        "label": "Interesse: Alimenti per animali",
        "match": {"pet_species": {"dog": 0.4, "cat": 0.35, "other": 0.05, "none": 0.2}},
    },
    "interest:pets": {
        "kind": "interest",
        "label": "Interesse: Animali domestici",
        "match": {"pet_species": {"dog": 0.35, "cat": 0.3, "other": 0.05, "none": 0.3}},
    },
    "interest:skincare": {
        "kind": "interest",
        "label": "Interesse: Cura della pelle",
        "match": {"skincare_routine": {"none": 0.2, "basic": 0.45, "extended": 0.35}},
    },
    "interest:beauty": {
        "kind": "interest",
        "label": "Interesse: Bellezza",
        "match": {"skincare_routine": {"none": 0.25, "basic": 0.45, "extended": 0.3}},
    },
    "interest:fitness": {
        "kind": "interest",
        "label": "Interesse: Fitness e benessere",
        "match": {"fitness_active": {"yes": 0.7, "no": 0.3}},
    },
    "interest:fashion": {"kind": "interest", "label": "Interesse: Moda", "match": {}},
    "interest:online_shopping": {"kind": "interest", "label": "Interesse: Shopping online", "match": {}},
    "interest:travel": {"kind": "interest", "label": "Interesse: Viaggi", "match": {}},
    "behavior:engaged_shoppers": {
        "kind": "behavior",
        "label": "Comportamento: Acquirenti coinvolti",
        "match": {},
    },
    "behavior:frequent_travelers": {
        "kind": "behavior",
        "label": "Comportamento: Viaggiatori frequenti",
        "match": {},
    },
    "demographic:single": {
        "kind": "demographic",
        "label": "Demografia: Single",
        "match": {
            "relationship_status": {"single": 0.85, "partnered": 0.1, "married": 0.05},
            "household": {"alone": 0.4, "couple": 0.05, "family": 0.2, "shared": 0.35},
        },
    },
    "demographic:parents": {
        "kind": "demographic",
        "label": "Demografia: Genitori",
        "match": {"has_children": {"yes": 0.9, "no": 0.1}, "household": {"family": 0.85, "alone": 0.05}},
    },
    "demographic:married": {
        "kind": "demographic",
        "label": "Demografia: Sposati",
        "match": {"relationship_status": {"married": 0.9, "partnered": 0.1}},
    },
}

# Proxy terms worth suggesting when an attribute has no direct Meta option.
SUGGESTED_PROXIES = {
    ("pet_species", "dog"): ["interest:dogs", "interest:pet_food", "interest:pets"],
    ("pet_species", "cat"): ["interest:cats", "interest:pet_food", "interest:pets"],
    ("household", "alone"): ["demographic:single"],
    ("household", "family"): ["demographic:parents"],
    ("has_children", "yes"): ["demographic:parents"],
    ("relationship_status", "single"): ["demographic:single"],
    ("relationship_status", "married"): ["demographic:married"],
    ("skincare_routine", "extended"): ["interest:skincare", "interest:beauty"],
    ("fitness_active", "yes"): ["interest:fitness"],
}
