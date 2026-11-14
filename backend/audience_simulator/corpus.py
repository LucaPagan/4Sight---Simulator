"""Comparable real-campaign corpus: stimuli and outcomes live in separate fields, splits are by campaign.

Inputs (``ComparableCampaign.inputs``) never contain impressions, clicks or spend, so nothing observed
can reach an agent prompt. Selection, ordering and splitting never read outcomes.
"""

import hashlib
import itertools
import json
import math
import re
from typing import Literal

import httpx
import pandas as pd
from pydantic import Field, model_validator
from scipy.stats import norm

from .schemas import StrictModel

UPWORTHY_URL = "https://osf.io/download/3vqmp/"
UPWORTHY_FILE = "upworthy-archive-exploratory-packages-03.12.2020.csv"
UPWORTHY_SHA256 = "8368313b060f4015a0c6fb34e6d788163cee29554144aba9390b14922eb9d8ce"
UPWORTHY_LICENSE = "CC BY 4.0 (OSF project jd64p); cite Matias, Munger, Le Quere, Ebersole 2021, Sci Data"
MIN_IMPRESSIONS = 500
MAX_ARMS = 4
# Upworthy authors: tests from 2013-06-25 to 2014-01-10 are likely to have randomization problems.
RANDOMIZATION_START = pd.Timestamp("2013-06-25")
RANDOMIZATION_END = pd.Timestamp("2014-01-11")
MIN_RESOLVED_TEST_PAIRS = 69  # docs/PROMISE.md: exact binomial, 65% vs 50%, alpha 0.05, power 0.8


class CorpusDomain(StrictModel):
    kind: Literal["news_headline", "paid_social"]
    platform: str
    country: str
    language: str
    objective: str
    placement: str


class Stimulus(StrictModel):
    id: str
    headline: str | None = None
    primary_text: str = ""


class Observation(StrictModel):
    impressions: int = Field(gt=0)
    clicks: int = Field(ge=0)
    spend_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def clicks_fit_impressions(self):
        if self.clicks > self.impressions:
            raise ValueError("clic superiori alle impression")
        return self


class ComparableCampaign(StrictModel):
    campaign_id: str
    source: str
    domain: CorpusDomain
    date_from: str | None = None
    date_to: str | None = None
    stimuli: list[Stimulus] = Field(min_length=2)
    observations: dict[str, Observation]
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def observations_match_stimuli(self):
        if set(self.observations) != {s.id for s in self.stimuli}:
            raise ValueError("esiti e creatività non corrispondono")
        return self

    def inputs(self) -> dict:
        """Everything an agent may see. Outcomes are deliberately absent."""
        return {
            "campaign_id": self.campaign_id,
            "domain": self.domain.model_dump(),
            "date_from": self.date_from,
            "date_to": self.date_to,
            "stimuli": [s.model_dump() for s in self.stimuli],
        }

    def pairs(self) -> list[tuple[str, str]]:
        return list(itertools.combinations(sorted(s.id for s in self.stimuli), 2))

    def resolved_pairs(self) -> list[dict]:
        """Pairs whose observed CTR difference has a 95% Newcombe interval excluding zero."""
        result = []
        for a, b in self.pairs():
            oa, ob = self.observations[a], self.observations[b]
            low, high = newcombe_interval(oa.clicks, oa.impressions, ob.clicks, ob.impressions)
            if low > 0 or high < 0:
                result.append({"pair": (a, b), "higher": a if low > 0 else b, "interval_pp": [low, high]})
        return result


def _wilson(clicks, n):
    z = norm.ppf(0.975)
    p = clicks / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    width = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return center - width, center + width


def newcombe_interval(clicks_a, n_a, clicks_b, n_b):
    """95% Newcombe interval for CTR(a) - CTR(b), in percentage points; safe with zero clicks."""
    pa, pb = clicks_a / n_a, clicks_b / n_b
    la, ua = _wilson(clicks_a, n_a)
    lb, ub = _wilson(clicks_b, n_b)
    return (
        100 * (pa - pb - math.hypot(pa - la, ub - pb)),
        100 * (pa - pb + math.hypot(ua - pa, pb - lb)),
    )


def _digest(*parts) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def _normalized(text) -> str:
    return " ".join(re.findall(r"\w+", str(text).casefold()))


def _count(value, what):
    number = float(value)
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError(f"Conteggio non valido: {what}")
    return int(number)


def _require(frame, columns):
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"colonne mancanti: {missing}")


def build_upworthy_campaigns(frame, min_impressions=MIN_IMPRESSIONS, max_arms=MAX_ARMS):
    """One campaign per Upworthy test; arms are packages whose headline text is the stimulus."""
    _require(frame, ["created_at", "clickability_test_id", "headline", "impressions", "clicks"])
    created = pd.to_datetime(frame.created_at, errors="coerce", format="ISO8601")
    if "problem" not in frame and created.isna().any():
        raise ValueError("data di creazione non valida: impossibile applicare la finestra di randomizzazione")
    excluded = dict.fromkeys(
        ["randomization_problem", "too_few_distinct_arms", "too_many_arms", "low_impressions"], 0
    )
    campaigns = []
    for test_id, group in frame.groupby("clickability_test_id", sort=True):
        for column in ("impressions", "clicks"):
            for value in group[column]:
                _count(value, column)
        if "problem" in group:
            flagged = (group["problem"].astype(float) > 0).any()
        else:
            dates = created.loc[group.index]
            flagged = bool(((dates >= RANDOMIZATION_START) & (dates < RANDOMIZATION_END)).any())
        if flagged:
            excluded["randomization_problem"] += 1
            continue
        group = group.assign(norm=group.headline.map(lambda h: _normalized(h) if isinstance(h, str) else ""))
        counts = group["norm"].value_counts()
        group = group.loc[(group["norm"] != "") & group["norm"].map(counts).eq(1)]
        if len(group) < 2:
            excluded["too_few_distinct_arms"] += 1
            continue
        if len(group) > max_arms:
            excluded["too_many_arms"] += 1
            continue
        if (group.impressions.astype(float) < min_impressions).any():
            excluded["low_impressions"] += 1
            continue
        stimuli, observations = [], {}
        for row in group.itertuples():
            arm = _digest("upworthy", test_id, row.norm)[:12]
            stimuli.append(Stimulus(id=arm, headline=row.headline.strip()))
            observations[arm] = Observation(
                impressions=_count(row.impressions, "impressions"), clicks=_count(row.clicks, "clicks")
            )
        stimuli.sort(key=lambda s: s.id)
        days = pd.to_datetime(group.created_at, errors="coerce", format="ISO8601").dropna()
        campaigns.append(
            ComparableCampaign(
                campaign_id=f"upworthy:{test_id}",
                source="upworthy_exploratory",
                domain=CorpusDomain(
                    kind="news_headline",
                    platform="upworthy_web",
                    country="US",
                    language="en",
                    objective="click_through",
                    placement="unknown",
                ),
                date_from=str(days.min().date()) if len(days) else None,
                date_to=str(days.max().date()) if len(days) else None,
                stimuli=stimuli,
                observations=observations,
                limitations=[
                    "Titoli di news, non annunci a pagamento: dominio diverso dall'ecommerce.",
                    "Le immagini (eyecatcher) variano tra i pacchetti e non sono disponibili: "
                    "la differenza di CTR non è attribuibile al solo titolo.",
                    "Pubblico USA 2013-2015; le fonti pubbliche possono essere note al modello.",
                ],
            )
        )
    return campaigns, {"campaigns": len(campaigns), "excluded": excluded}


def build_gwwc_campaigns(frame, max_arms=8):
    """Paid Facebook ad copy variants from the GWWC export; an experiment is one (campaign, ad)."""
    _require(frame, ["Campaign name", "Ad name", "Text", "Impressions", "Link clicks"])
    excluded = dict.fromkeys(
        ["ambiguous_text", "unknown_clicks", "too_few_distinct_arms", "too_many_arms"], 0
    )
    campaigns = []
    for (campaign, ad), group in frame.groupby(["Campaign name", "Ad name"], sort=True):
        texts = group.Text.tolist()
        if any(not isinstance(t, str) or not t.strip() for t in texts) or len(texts) != len(set(texts)):
            excluded["ambiguous_text"] += 1
            continue
        if group["Link clicks"].isna().any():
            excluded["unknown_clicks"] += 1
            continue
        if len(group) < 2:
            excluded["too_few_distinct_arms"] += 1
            continue
        if len(group) > max_arms:
            excluded["too_many_arms"] += 1
            continue
        stimuli, observations = [], {}
        for _, row in group.iterrows():
            arm = _digest("gwwc", campaign, ad, row["Text"])[:12]
            spend = row.get("Amount spent (USD)")
            stimuli.append(Stimulus(id=arm, primary_text=row["Text"]))
            observations[arm] = Observation(
                impressions=_count(row["Impressions"], "impressions"),
                clicks=_count(row["Link clicks"], "clicks"),
                spend_usd=None if spend is None or pd.isna(spend) else float(spend),
            )
        stimuli.sort(key=lambda s: s.id)
        campaigns.append(
            ComparableCampaign(
                campaign_id=f"gwwc:{_digest('gwwc', campaign, ad)[:12]}",
                source="gwwc_giving_guide_2021",
                domain=CorpusDomain(
                    kind="paid_social",
                    platform="facebook",
                    country="unknown_in_public_export",
                    language="en",
                    objective="lead_generation",
                    placement="unknown",
                ),
                date_from=_first(group, "Reporting starts"),
                date_to=_first(group, "Reporting ends"),
                stimuli=stimuli,
                observations=observations,
                limitations=[
                    "Una sola campagna di beneficenza: poche unità indipendenti, non ecommerce.",
                    "Distribuzione ottimizzata da Meta: il pubblico raggiunto può differire tra testi.",
                    "Video e targeting completo non osservati.",
                ],
            )
        )
    return campaigns, {"campaigns": len(campaigns), "excluded": excluded}


def _first(group, column):
    return str(group[column].iloc[0]) if column in group and pd.notna(group[column].iloc[0]) else None


def _inputs_hash(campaigns):
    canonical = json.dumps([c.inputs() for c in campaigns], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def split_campaigns(campaigns, test_fraction=0.3, salt="corpus-split-v1"):
    """Deterministic split by campaign id. Outcomes are never read; test text seen in dev is dropped."""
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction deve essere tra 0 e 1")
    ordered = sorted(campaigns, key=lambda c: c.campaign_id)
    dev, test = [], []
    for campaign in ordered:
        draw = int(_digest(salt, campaign.campaign_id)[:12], 16) / 16**12
        (test if draw < test_fraction else dev).append(campaign)
    seen = {_normalized(t) for c in dev for s in c.stimuli for t in (s.headline, s.primary_text) if t}
    kept, dropped = [], []
    for campaign in test:
        texts = {_normalized(t) for s in campaign.stimuli for t in (s.headline, s.primary_text) if t}
        (dropped if texts & seen else kept).append(campaign)
    observations = json.dumps(
        {c.campaign_id: {k: v.model_dump() for k, v in c.observations.items()} for c in kept},
        sort_keys=True,
    )
    manifest = {
        "salt": salt,
        "test_fraction": test_fraction,
        "dev_campaigns": len(dev),
        "test_campaigns": len(kept),
        "test_pairs": sum(len(c.pairs()) for c in kept),
        "dev_sha256": _inputs_hash(dev),
        "test_sha256": _inputs_hash(kept),
        "test_observations_sha256": hashlib.sha256(observations.encode()).hexdigest(),
        "dropped_for_text_overlap": [c.campaign_id for c in dropped],
    }
    return {"dev": dev, "test": kept, "manifest": manifest}


def fetch_source(name, transport=None):
    """Download a pinned public source; refuse anything whose checksum differs."""
    if name == "upworthy":
        url, expected = UPWORTHY_URL, UPWORTHY_SHA256
    elif name == "gwwc":
        from .retrospective import SOURCE_SHA256, SOURCE_URL

        url, expected = SOURCE_URL, SOURCE_SHA256
    else:
        raise ValueError("Fonte sconosciuta")
    with httpx.Client(timeout=120, transport=transport, follow_redirects=True) as http:
        response = http.get(url)
        response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != expected:
        raise ValueError("Fonte modificata: checksum non corrispondente")
    return response.content


def prepare_corpus(store, upworthy_frame, gwwc_frame=None, test_fraction=0.3):
    """Build, split and persist the corpus. Test outcomes are written apart from test inputs.

    The resolved-pair count is a feasibility check against the pre-registered minimum; it is an
    aggregate and never used to choose prompts, models or thresholds.
    """
    campaigns, upworthy_report = build_upworthy_campaigns(upworthy_frame)
    split = split_campaigns(campaigns, test_fraction)
    dev, test, manifest = split["dev"], split["test"], split["manifest"]
    store.write_json("corpus/dev.json", [c.model_dump(mode="json") for c in dev])
    store.write_json("corpus/test/inputs.json", [c.inputs() for c in test])
    store.write_json(
        "corpus/test/observations.json",
        {c.campaign_id: {k: v.model_dump() for k, v in c.observations.items()} for c in test},
    )
    store.write_json("corpus/split-manifest.json", manifest)
    smoke = None
    if gwwc_frame is not None:
        ad_campaigns, gwwc_report = build_gwwc_campaigns(gwwc_frame)
        store.write_json("corpus/ad-smoke/campaigns.json", [c.model_dump(mode="json") for c in ad_campaigns])
        smoke = {
            "campaigns": len(ad_campaigns),
            "pairs": sum(len(c.pairs()) for c in ad_campaigns),
            "excluded": gwwc_report["excluded"],
            "note": "Una sola campagna di beneficenza: smoke test del dominio pubblicitario, non conta per la potenza.",
        }
    resolved_test = sum(len(c.resolved_pairs()) for c in test)
    return {
        "status": "prepared_no_ai_calls",
        "upworthy": upworthy_report,
        "dev": {"campaigns": len(dev), "pairs": sum(len(c.pairs()) for c in dev)},
        "test": {
            "campaigns": len(test),
            "pairs": manifest["test_pairs"],
            "resolved_pairs": resolved_test,
        },
        "feasibility": {
            "minimum_resolved_test_pairs": MIN_RESOLVED_TEST_PAIRS,
            "meets_minimum": resolved_test >= MIN_RESOLVED_TEST_PAIRS,
        },
        "ad_smoke": smoke,
        "manifest": manifest,
    }
