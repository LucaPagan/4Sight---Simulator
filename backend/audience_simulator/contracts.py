"""Response contracts; form drafts may be incomplete, published results may not."""

from pydantic import BaseModel, ConfigDict, Field


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class ConsumerProfile(ResponseModel):
    agent_id: str
    age_band: str
    category_affinity: float
    budget_sensitivity: float
    purchase_need: float
    brand_familiarity: float
    population_weight: float
    advertising_literacy: float
    repeat_tolerance: float


class AgePrediction(ResponseModel):
    age_band: str
    impression_share: float
    ctr_estimate: float
    ctr_range: list[float]
    expected_impressions: float
    clicks_estimate: float
    expected_spend: float
    evidence_level: str


class Prediction(ResponseModel):
    ad_id: str
    date: str
    ctr_pred: float
    cpm_pred: float
    ctr_interval: list[float]
    cpm_interval: list[float]
    expected_impressions: float
    expected_clicks: float
    expected_spend: float
    ages: list[AgePrediction]
    cold_start: bool
    confidence_status: str


class StagePerformance(ResponseModel):
    calls: int = Field(default=0, ge=0)
    accepted: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)
    corrections: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    fallback: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    seconds: float = Field(default=0, ge=0)
    pacing_seconds: float = Field(default=0, ge=0)


class NativePerformance(ResponseModel):
    cards: StagePerformance = Field(default_factory=StagePerformance)
    reactions: StagePerformance = Field(default_factory=StagePerformance)
    writer_version: str | None = None
    reaction_prompt_version: str | None = None
    concurrency: int = Field(default=1, ge=1, le=4)


class SimulationRun(ResponseModel):
    id: str
    scenario_id: str
    status: str
    phase: str
    completion_status: str
    progress: int
    completed_policies: int
    required_policies: int
    error: str | None = None
    result_key: str | None = None
    created_at: str | None = None
    model_name: str | None = None
    heartbeat_at: str | None = None
    provider: str = "ollama"
    requested_model: str | None = None
    performance: NativePerformance | None = None


class SimulationResult(ResponseModel):
    completion_status: str
    profiles: list[ConsumerProfile]
    predictions: list[Prediction]
