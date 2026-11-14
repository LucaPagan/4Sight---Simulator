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
    population_size: Literal[120] = 120
    seed: int = Field(default=42, ge=0, le=2147483647)
    age_shares: list[float] = Field(default_factory=lambda: [1 / 6] * 6, min_length=6, max_length=6)
    age_effects: list[float] = Field(
        default_factory=lambda: [-0.2, -0.1, 0.0, 0.05, 0.2, 0.05], min_length=6, max_length=6
    )
    sensitivity_profile: Literal["conservative", "central", "exploratory"] = "central"
    prior_strength: float = Field(default=1.0, ge=0, le=2)
    placement: Literal["instagram_feed", "facebook_feed", "instagram_stories"] = "instagram_feed"
    browsing_task: Literal["casual_scrolling", "product_research", "comparison_shopping"] = "casual_scrolling"
    price_eur: float | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=2000)

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


class RuntimeSelection(StrictModel):
    provider: Literal["ollama", "gemini", "cloudflare"] = "ollama"
    model: str | None = Field(default=None, max_length=100)


class PreflightRequest(RuntimeSelection):
    scenario_id: str


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


class ComparisonRequest(StrictModel):
    run_id: str


class ExportRequest(StrictModel):
    run_id: str
    kind: Literal["aggregate", "age", "report"] = "aggregate"
    allow_preliminary: bool = False
