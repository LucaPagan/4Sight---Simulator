"""Registry of the domains and configurations a benchmark has actually verified.

The registry is deliberately empty: a domain is added only after a frozen held-out
benchmark (see docs/PROMISE.md) has passed for that exact prompt version and model.
"""

from typing import Literal

from pydantic import model_validator

from .schemas import CampaignBrief, StrictModel

LANGUAGES = {"IT": "it", "ES": "es", "FR": "fr", "DE": "de"}


class Domain(StrictModel):
    vertical: str
    country: str
    objective: str
    placement: str
    language: str

    @classmethod
    def from_brief(cls, brief: CampaignBrief) -> "Domain":
        return cls(
            vertical=brief.vertical,
            country=brief.country,
            objective=brief.objective,
            placement=brief.placement,
            language=LANGUAGES[brief.country],
        )


class VerifiedConfig(StrictModel):
    prompt_version: str
    model: str
    benchmark_id: str


class DomainEntry(StrictModel):
    domain: Domain
    verified_for: list[VerifiedConfig]

    @model_validator(mode="after")
    def needs_a_configuration(self):
        if not self.verified_for:
            raise ValueError("Un dominio verificato richiede almeno una configurazione con benchmark")
        return self


class DomainAssessment(StrictModel):
    status: Literal["verified", "out_of_domain", "unverified_configuration"]
    reason: str
    benchmark_id: str | None = None

    @property
    def verified(self) -> bool:
        return self.status == "verified"


VERIFIED_DOMAINS: tuple[DomainEntry, ...] = ()


def assess_domain(
    domain: Domain,
    prompt_version: str | None,
    model: str | None,
    registry: tuple[DomainEntry, ...] | None = None,
) -> DomainAssessment:
    entries = VERIFIED_DOMAINS if registry is None else registry
    if not entries:
        return DomainAssessment(
            status="out_of_domain", reason="Nessun benchmark indipendente ha ancora verificato un dominio."
        )
    matches = [e for e in entries if e.domain == domain]
    if not matches:
        return DomainAssessment(
            status="out_of_domain",
            reason="Settore, paese, obiettivo, placement o lingua non coincidono con un dominio verificato.",
        )
    for entry in matches:
        for verified in entry.verified_for:
            if (verified.prompt_version, verified.model) == (prompt_version, model):
                return DomainAssessment(
                    status="verified",
                    reason="Dominio e configurazione verificati.",
                    benchmark_id=verified.benchmark_id,
                )
    return DomainAssessment(
        status="unverified_configuration",
        reason="Dominio noto, ma prompt o modello non coincidono con quelli verificati: ripetere il benchmark.",
    )
