from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

AGES = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
VERTICALS = ["beauty_skincare", "pet_ecommerce", "abbigliamento"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Creative(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    headline: str = Field(min_length=1, max_length=250)
    primary_text: str = Field(min_length=1, max_length=4000)
    visual_description: str = Field(default="", max_length=2000)
    cta: str = Field(default="Scopri di più", max_length=100)
    lever: Literal["scarcity", "urgency", "black_friday", "value"] = "value"
    format: Literal["immagine", "video", "carosello"] = "immagine"
    claim_verified: bool = False
    offer: str = Field(default="", max_length=300)
    price_text: str = Field(default="", max_length=200)
    landing_page_summary: str = Field(default="", max_length=1000)


PlacementId = Literal[
    "instagram_feed",
    "instagram_stories",
    "instagram_reels",
    "instagram_explore",
    "instagram_profile_feed",
    "facebook_feed",
    "facebook_stories",
    "facebook_reels",
    "facebook_marketplace",
    "facebook_right_column",
    "audience_network",
    "messenger_inbox",
]
REGIONS_MAX = 30


class AudienceConstraint(StrictModel):
    """The advertiser's intent on a person attribute: the person's value must (or must not) be in ``values``."""

    attribute: str = Field(min_length=1, max_length=60)
    values: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(min_length=1, max_length=6)
    negate: bool = False

    @model_validator(mode="after")
    def known_attribute(self):
        from .meta_catalog import PERSONA_ATTRIBUTES

        spec = PERSONA_ATTRIBUTES.get(self.attribute)
        if spec is None:
            raise ValueError(f"Attributo del pubblico sconosciuto: {self.attribute}")
        unknown = [v for v in self.values if v not in spec["values"]]
        if unknown:
            raise ValueError(f"Valori non validi per {self.attribute}: {', '.join(unknown)}")
        return self


class DetailedTerm(StrictModel):
    """One Meta detailed-targeting term. include = OR group, narrow = AND with the include group, exclude = NOT."""

    id: str = Field(min_length=1, max_length=80)
    mode: Literal["include", "narrow", "exclude"] = "include"

    @model_validator(mode="after")
    def known_term(self):
        from .meta_catalog import DETAILED_TERMS

        if self.id not in DETAILED_TERMS:
            raise ValueError(f"Termine di targeting sconosciuto: {self.id}")
        return self


class CustomAudience(StrictModel):
    """Custom, lookalike or page-fan audience. Only described: its composition is a declared assumption."""

    kind: Literal["custom", "lookalike", "page_fans"]
    description: str = Field(min_length=1, max_length=300)
    lookalike_percent: int | None = Field(default=None, ge=1, le=10)


class FrequencyCap(StrictModel):
    max_impressions: int = Field(ge=1, le=50)
    days: int = Field(default=7, ge=1, le=30)


class TargetingSpec(StrictModel):
    """Everything Ads Manager lets you set for an ad set, plus the advertiser's intent in plain language."""

    # Intent: what the advertiser wants, independent of what Meta can target.
    audience_intent: str = Field(default="", max_length=1000)
    constraints: list[AudienceConstraint] = Field(default_factory=list, max_length=12)
    # Location and people.
    regions: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(
        default_factory=list, max_length=REGIONS_MAX
    )
    urbanicity: Literal["any", "urban", "suburban", "rural"] = "any"
    age_min: int = Field(default=18, ge=18, le=65)
    age_max: int = Field(default=65, ge=18, le=65)
    gender: Literal["all", "women", "men"] = "all"
    languages: list[Annotated[str, Field(min_length=2, max_length=10)]] = Field(
        default_factory=list, max_length=10
    )
    # Detailed targeting and saved audiences.
    detailed: list[DetailedTerm] = Field(default_factory=list, max_length=50)
    custom_audiences: list[CustomAudience] = Field(default_factory=list, max_length=5)
    advantage_audience: bool = False
    # Placements and devices.
    advantage_placements: bool = True
    placements: list[PlacementId] = Field(default_factory=list, max_length=12)
    device_platforms: list[Literal["ios", "android", "desktop"]] = Field(default_factory=list, max_length=3)
    wifi_only: bool = False
    # Schedule (lifetime budgets only on the real platform; kept here as audience availability).
    hours: list[Annotated[int, Field(ge=0, le=23)]] = Field(default_factory=list, max_length=24)
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(default_factory=list, max_length=7)
    # Optimisation and delivery.
    optimization_goal: Literal[
        "link_clicks", "landing_page_views", "conversions", "reach", "impressions", "leads"
    ] = "link_clicks"
    bid_strategy: Literal["lowest_cost", "cost_cap", "bid_cap", "roas_goal"] = "lowest_cost"
    bid_amount_eur: float | None = Field(default=None, ge=0, le=100000)
    frequency_cap: FrequencyCap | None = None

    @model_validator(mode="after")
    def coherent(self):
        if self.age_min > self.age_max:
            raise ValueError("Età minima maggiore dell'età massima")
        if len(set(self.placements)) != len(self.placements):
            raise ValueError("Placement duplicati")
        if self.bid_strategy in {"cost_cap", "bid_cap", "roas_goal"} and self.bid_amount_eur is None:
            raise ValueError("Questa strategia di offerta richiede un importo")
        return self


class TargetingNote(StrictModel):
    code: str
    severity: Literal["info", "warning", "blocking"]
    message: str


class ProxySuggestion(StrictModel):
    attribute: str
    values: list[str]
    meta_direct: bool
    suggested_terms: list[str]
    selected_terms: list[str]
    expected_precision: float | None = Field(default=None, ge=0, le=1)
    precision_evidence: Literal["assumption"] = "assumption"


class ConstraintReach(StrictModel):
    attribute: str
    values: list[str]
    negate: bool
    share_in_reached: float = Field(ge=0, le=1)
    share_in_base: float = Field(ge=0, le=1)


class PanelAudit(StrictModel):
    size: int
    duplicates: int
    min_distance: float | None
    mean_distance: float | None
    band_counts: dict[str, int]
    reach_effective_ratio: float = Field(ge=0, le=1)
    missing_values: list[str]
    status: Literal["ok", "warning"]
    warnings: list[str]


class ReachSummary(StrictModel):
    """Who the simulated ad would reach, from the sampled pool. Probabilities derive from declared assumptions."""

    method: Literal["importance_resampling_v1"]
    evidence: Literal["assumption"] = "assumption"
    pool_size: int
    age_shares: list[float] = Field(min_length=6, max_length=6)
    constraints: list[ConstraintReach]
    ideal_share_in_reached: float | None = Field(default=None, ge=0, le=1)
    ideal_share_in_base: float | None = Field(default=None, ge=0, le=1)
    lift: float | None = None
    unmodelled_terms: list[str]
    audit: PanelAudit


class TargetingReport(StrictModel):
    """How a TargetingSpec is read: the intent as constraints, how Meta could reach it, and what is lost."""

    constraints: list[AudienceConstraint]
    unrecognized_intent: str
    proxies: list[ProxySuggestion]
    notes: list[TargetingNote]
    placements: list[PlacementId]
    applied_to_population: bool
    reading: Literal["rules_v1"] = "rules_v1"
    reach: ReachSummary | None = None


class TargetingAnalyzeRequest(StrictModel):
    country: Literal["IT", "ES", "FR", "DE"] = "IT"
    vertical: Literal["beauty_skincare", "pet_ecommerce", "abbigliamento"] = "pet_ecommerce"
    device: Literal["mobile", "desktop"] = "mobile"
    targeting: TargetingSpec


class CampaignBrief(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    brand: str = Field(min_length=1, max_length=150)
    product_description: str = Field(min_length=3, max_length=3000)
    vertical: Literal["beauty_skincare", "pet_ecommerce", "abbigliamento"]
    objective: Literal["vendite", "traffico"] = "vendite"
    platform: Literal["meta"] = "meta"
    country: Literal["IT", "ES", "FR", "DE"] = "IT"
    date_from: date = date(2026, 11, 16)
    date_to: date = date(2026, 11, 30)
    daily_adset_budget_eur: float = Field(default=150, ge=0, le=100000)
    creatives: list[Creative] = Field(default_factory=list, max_length=4)
    population_size: int = Field(default=120, ge=30, le=1000)
    seed: int = Field(default=42, ge=0, le=2147483647)
    age_shares: list[float] = Field(default_factory=lambda: [1 / 6] * 6, min_length=6, max_length=6)
    age_effects: list[float] = Field(
        default_factory=lambda: [-0.2, -0.1, 0.0, 0.05, 0.2, 0.05], min_length=6, max_length=6
    )
    sensitivity_profile: Literal["conservative", "central", "exploratory"] = "central"
    prior_strength: float = Field(default=1.0, ge=0, le=2)
    placement: Literal["instagram_feed", "facebook_feed", "instagram_stories"] = "instagram_feed"
    browsing_task: Literal["casual_scrolling", "product_research", "comparison_shopping"] = "casual_scrolling"
    device: Literal["mobile", "desktop"] = "mobile"
    price_eur: float | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=2000)
    targeting: TargetingSpec | None = None

    @model_validator(mode="after")
    def check_scenario(self):
        if not 0 <= (self.date_to - self.date_from).days <= 30:
            raise ValueError("Periodo richiesto: da 1 a 31 giorni")
        if any(x < 0 for x in self.age_shares) or abs(sum(self.age_shares) - 1) > 1e-8:
            raise ValueError("Le sei quote devono essere non negative e sommare a uno")
        if any(abs(x) > 3 for x in self.age_effects):
            raise ValueError("Effetti età limitati a ±3 log-odds")
        if len({c.id for c in self.creatives}) != len(self.creatives):
            raise ValueError("ID creatività duplicati")
        return self


class PersonaCard(StrictModel):
    """What the persona writer returns for one person. The ``echo_*`` fields repeat the facts so a mismatch is caught."""

    ref: str = Field(min_length=1, max_length=8)
    name: str = Field(min_length=3, max_length=60)
    city: str = Field(min_length=2, max_length=60)
    job: str = Field(min_length=2, max_length=80)
    bio: str = Field(min_length=40, max_length=450)
    daily_routine: str = Field(min_length=20, max_length=350)
    category_relationship: str = Field(min_length=20, max_length=350)
    social_habits: str = Field(min_length=20, max_length=350)
    ad_reaction_style: str = Field(min_length=20, max_length=350)
    pain_points: list[Annotated[str, Field(min_length=3, max_length=140)]] = Field(min_length=1, max_length=3)
    quirks: list[Annotated[str, Field(min_length=3, max_length=140)]] = Field(min_length=1, max_length=2)
    budget_eur_month: int = Field(ge=0, le=5000)
    echo_age: int = Field(ge=18, le=99)
    echo_gender: Literal["women", "men"]
    echo_household: Literal["alone", "couple", "family", "shared"]
    echo_has_children: Literal["yes", "no"]
    echo_pet_species: Literal["dog", "cat", "other", "none"]
    echo_device_os: Literal["ios", "android"]


class AgentEvaluation(StrictModel):
    clarity: int = Field(ge=0, le=4)
    interest: int = Field(ge=0, le=4)
    credibility: int = Field(ge=0, le=4)
    friction: int = Field(ge=0, le=4)
    conditional_action: Literal["consider_click", "defer", "not_interested"]
    frictions: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=8
    )
    evidence: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(min_length=1, max_length=8)
    unknowns: list[str] = Field(default_factory=list, max_length=6)
    conditional_reaction: str = Field(min_length=1, max_length=400)


class AgentDecision(StrictModel):
    """A persona's reaction to an ad as seen: what they noticed and how often they would skip, stop, engage, click.

    The four ``*_per_100`` fields answer «out of 100 times this ad appears to you in this situation»; the validator
    normalises them to 100. They are the model's hypothesis about this person, not measured behaviour."""

    first_impression: str = Field(min_length=5, max_length=220)
    detail_cited: str = Field(max_length=140)
    read_beyond_glance: bool
    reaction_after_stopping: str = Field(max_length=260)
    skip_per_100: int = Field(ge=0, le=100)
    stop_per_100: int = Field(ge=0, le=100)
    engage_per_100: int = Field(ge=0, le=100)
    click_per_100: int = Field(ge=0, le=100)
    action_if_engaged: Literal["like", "save", "share", "comment", "hide", "report", "none"]
    post_click_intent: Literal["buy", "browse", "bounce", "not_applicable"]
    frictions: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(max_length=4)
    evidence: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(min_length=1, max_length=4)
    unknowns: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(max_length=3)
    # Whether the ad itself is broken for this person, independent of how much the topic interests them.
    ad_problem: Literal["none", "confusing", "nonsense", "offensive", "off_topic"] = "none"


class CreativeAudit(StrictModel):
    """One neutral reading of a creative (not a persona): does it make sense, fit the product, hold together.

    Scores are 1 (broken) to 5 (fine), except ``hostility`` where 1 is none and 5 is openly hostile or offensive."""

    comprehensible: int = Field(ge=1, le=5)
    on_product: int = Field(ge=1, le=5)
    internally_consistent: int = Field(ge=1, le=5)
    hostility: int = Field(ge=1, le=5)
    problems: list[Literal["nonsense", "off_topic", "contradictory", "offensive", "spam", "unreadable"]] = Field(
        max_length=4
    )
    summary: str = Field(min_length=3, max_length=240)


class RuntimeSelection(StrictModel):
    provider: Literal["ollama", "gemini", "cloudflare"] = "ollama"
    model: str | None = Field(default=None, max_length=100)


class ReactionRequest(RuntimeSelection):
    slots: list[Literal["first", "repeat", "saturated"]] = Field(default=["first"], min_length=1)
    limit: int | None = Field(default=None, ge=1, le=2000)


class CounterfactualRequest(RuntimeSelection):
    n_pairs: int = Field(default=12, ge=4, le=60)


class PreflightRequest(RuntimeSelection):
    scenario_id: str
    mode: Literal["history_forecast", "agent_native"] = "history_forecast"
    slots: list[Literal["first", "repeat", "saturated"]] = Field(
        default=["first", "repeat", "saturated"], min_length=1
    )


class RuntimeCredentials(StrictModel):
    provider: Literal["gemini", "cloudflare"] = "gemini"
    api_key: SecretStr | None = None
    account_id: str | None = Field(default=None, max_length=32, pattern=r"^[a-fA-F0-9]{32}$")
    free_tier_confirmed: bool
    requests_per_minute: int = Field(default=10, ge=1, le=60)

    @model_validator(mode="after")
    def key_format(self):
        key = self.api_key.get_secret_value() if self.api_key is not None else ""
        if key and (not 20 <= len(key) <= 256 or any(c.isspace() for c in key)):
            raise ValueError("Formato della chiave API non valido")
        return self


class SimulationRequest(RuntimeSelection):
    scenario_id: str
    idempotency_key: str = Field(min_length=1, max_length=120)
    mode: Literal["history_forecast", "agent_native"] = "history_forecast"
    slots: list[Literal["first", "repeat", "saturated"]] = Field(
        default=["first", "repeat", "saturated"], min_length=1
    )


class ComparisonRequest(StrictModel):
    run_id: str


class ExportRequest(StrictModel):
    run_id: str
    kind: Literal["aggregate", "age", "report"] = "aggregate"
    allow_preliminary: bool = False
