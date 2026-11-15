"""Gemini Free Tier adapter. No automatic model, billing or provider fallback."""

import fcntl
import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4

import httpx

from .agents import evaluation_schema, validate_evaluation
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, model_view

GEMINI_MODELS = {
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite · velocità",
    "gemini-3.8-flash": "Gemini 3.8 Flash · qualità da confrontare",
}
CLOUD_PROMPT_VERSION = f"{PROMPT_VERSION}-gemini-interactions-2026-05-20"


def credentials_path(root, provider="gemini"):
    if provider not in {"gemini", "cloudflare"}:
        raise ValueError("Provider credenziali non consentito")
    return Path(root) / (
        "runtime-credentials.json" if provider == "gemini" else "cloudflare-credentials.json"
    )


def read_credentials(root, provider="gemini"):
    path = credentials_path(root, provider)
    if not path.exists():
        return {"api_key": "", "free_tier_confirmed": False}
    return json.loads(path.read_text())


def save_credentials(
    root, key, free_tier_confirmed, requests_per_minute=10, provider="gemini", account_id=""
):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = credentials_path(root, provider)
    temporary = root / f".{provider}-credentials.{uuid4().hex}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(
                {
                    "api_key": key,
                    "free_tier_confirmed": free_tier_confirmed,
                    "requests_per_minute": requests_per_minute,
                    "account_id": account_id,
                },
                stream,
            )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class CloudRuntimeError(ValueError):
    pass


class CloudQuotaError(CloudRuntimeError):
    def __init__(self, retry_after_seconds=None, provider="Gemini", detail=""):
        self.retry_after_seconds = retry_after_seconds
        wait = (
            f" Riprova tra circa {max(1, round(retry_after_seconds / 60))} minuti."
            if retry_after_seconds
            else ""
        )
        super().__init__(
            f"Quota {provider} esaurita o limite temporaneo: controlla la console del provider e riprendi più tardi.{wait} Le policy salvate restano disponibili; nessun fallback a pagamento."
            + (f" Messaggio del provider: {detail}" if detail else "")
        )


RETRY_DELAYS = (4, 12)  # seconds before the second and third attempt of a generation hit by a passing failure
TRANSIENT_STATUS = {500, 502, 503, 504}


def provider_message(response, limit=220):
    """The provider's own error text, shortened. Never contains the request (so no key and no prompt)."""
    try:
        data = response.json()
    except ValueError:
        return ""
    error = data.get("error") or (data.get("errors") or [{}])[0]
    text = error.get("message", "") if isinstance(error, dict) else str(error)
    return " ".join(text.split())[:limit]


def retry_seconds(text):
    """«Please retry in 38m5s» -> 2285. None when the provider gives no wait."""
    match = re.search(r"retry in\s+(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", text or "", re.I)
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (float(g) if g else 0.0 for g in match.groups())
    total = hours * 3600 + minutes * 60 + seconds
    return total if 0 < total < 86401 else None


def post_with_retry(http, url, body, sleep=time.sleep):
    """POST that survives a passing overload or timeout. Quota and auth errors are returned at once for ``_check``."""
    for delay in (*RETRY_DELAYS, None):
        try:
            response = http.post(url, json=body)
        except httpx.TimeoutException:
            if delay is None:
                raise CloudRuntimeError(
                    "Il provider non ha risposto in tempo per tre volte. Riprendi la run tra qualche minuto."
                ) from None
            sleep(delay)
            continue
        if response.status_code in TRANSIENT_STATUS and delay is not None:
            sleep(delay)
            continue
        return response
    raise AssertionError("unreachable")


class CloudRateLimiter:
    def __init__(self, requests_per_minute, path=None):
        self.interval = 60 / max(1, requests_per_minute)
        self.next_request = 0.0
        self.rate_limit_path = Path(path) if path else None

    def pace(self):
        if self.rate_limit_path is not None:
            self.rate_limit_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.rate_limit_path, os.O_RDWR | os.O_CREAT, 0o600)
            with os.fdopen(fd, "r+") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                last = float(stream.read() or "0")
                delay = max(0, last + self.interval - time.time())
                if delay:
                    time.sleep(min(delay, self.interval))
                stream.seek(0)
                stream.truncate()
                stream.write(str(time.time()))
                stream.flush()
            return delay
        delay = max(0, self.next_request - time.monotonic())
        if delay:
            time.sleep(delay)
        self.next_request = time.monotonic() + self.interval
        return delay


class GeminiClient:
    provider = "gemini"
    prompt_version = CLOUD_PROMPT_VERSION

    def __init__(
        self,
        api_key,
        model="gemini-3.5-flash-lite",
        free_tier_confirmed=False,
        requests_per_minute=10,
        transport=None,
        rate_limit_path=None,
    ):
        if model not in GEMINI_MODELS:
            raise ValueError("Modello Gemini non consentito")
        self.model = model
        self.configured = bool(api_key)
        self.free_tier_confirmed = free_tier_confirmed
        self.limiter = CloudRateLimiter(requests_per_minute, rate_limit_path)
        self.interval = self.limiter.interval
        self.http = httpx.Client(
            base_url="https://generativelanguage.googleapis.com",
            headers={"x-goog-api-key": api_key, "Api-Revision": "2026-05-20"},
            timeout=120,
            transport=transport,
            trust_env=False,
        )

    def status(self):
        ready = self.configured and self.free_tier_confirmed
        return {
            "provider": self.provider,
            "available": self.configured,
            "ready": ready,
            "selected_model": self.model,
            "digest": f"gemini:{self.model}:interactions-2026-05-20" if ready else None,
            "digest_is_weights_hash": False,
            "prompt_version": self.prompt_version,
            "requests_per_minute": 60 / self.interval,
            "models": [{"name": m, "label": label} for m, label in GEMINI_MODELS.items()],
            "error": None
            if ready
            else "Configura la chiave Gemini e conferma un progetto Free Tier senza billing attivo.",
            "warning": "Il tier di fatturazione non è verificabile dalla chiave. Usa un progetto Google senza billing. Quote e policy dati del provider si applicano.",
        }

    def _check(self, response):
        if response.status_code == 429:
            try:
                retry = float(response.headers.get("retry-after", ""))
                if not 0 < retry < 86401:
                    retry = None
            except ValueError:
                retry = None
            detail = provider_message(response)
            raise CloudQuotaError(retry or retry_seconds(detail), detail=detail)
        if response.status_code in (401, 403):
            raise CloudRuntimeError(
                "Chiave Gemini non valida o progetto non autorizzato. Verifica chiave e permessi in AI Studio."
            )
        if response.is_error:
            detail = provider_message(response)
            raise CloudRuntimeError(
                f"Gemini ha restituito HTTP {response.status_code}. Verifica disponibilità del modello e configurazione; nessun provider alternativo è stato chiamato."
                + (f" Messaggio del provider: {detail}" if detail else "")
            )

    def _text(self, data):
        if data.get("status") != "completed":
            raise ValueError("Risposta Gemini incompleta o bloccata")
        return "".join(
            content.get("text", "")
            for step in data.get("steps", [])
            if step.get("type") == "model_output"
            for content in step.get("content", [])
            if content.get("type") == "text"
        )

    def generate(self, system, user, schema, *, temperature=0.9, seed=None, max_tokens=4096):
        """One schema-constrained generation outside the evaluation flow. ``seed`` is not supported by the API."""
        if not self.status()["ready"]:
            raise CloudRuntimeError(self.status()["error"])
        pacing = self.limiter.pace()
        start = time.monotonic()
        response = post_with_retry(
            self.http,
            "/v1beta/interactions",
            {
                "model": self.model,
                "system_instruction": system,
                "input": user,
                "store": False,
                "stream": False,
                "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
                "generation_config": {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    "thinking_level": "minimal" if self.model.endswith("flash-lite") else "low",
                },
            },
        )
        self._check(response)
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage", {})
        return {
            "raw": self._text(data),
            "seconds": time.monotonic() - start,
            "pacing_seconds": pacing,
            "tokens": usage.get("total_output_tokens", 0),
            "prompt_tokens": usage.get("total_input_tokens", 0),
            "provider": self.provider,
            "model": data.get("model", self.model),
        }

    def evaluate(self, payload):
        if not self.status()["ready"]:
            raise CloudRuntimeError(self.status()["error"])
        pacing = self.limiter.pace()
        start = time.monotonic()
        view = model_view(payload)
        response = self.http.post(
            "/v1beta/interactions",
            json={
                "model": self.model,
                "system_instruction": SYSTEM_PROMPT,
                "input": json.dumps(view, ensure_ascii=False),
                "store": False,
                "stream": False,
                "response_format": {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": evaluation_schema(view),
                },
                "generation_config": {
                    "temperature": 0,
                    "max_output_tokens": 1024,
                    "thinking_level": "minimal" if self.model.endswith("flash-lite") else "low",
                },
            },
        )
        self._check(response)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "completed":
            raise ValueError("Risposta Gemini incompleta o bloccata")
        raw = "".join(
            content.get("text", "")
            for step in data.get("steps", [])
            if step.get("type") == "model_output"
            for content in step.get("content", [])
            if content.get("type") == "text"
        )
        evaluation, normalizations = validate_evaluation(raw, view)
        usage = data.get("usage", {})
        return {
            "evaluation": evaluation,
            "seconds": time.monotonic() - start,
            "pacing_seconds": pacing,
            "tokens": usage.get("total_output_tokens", 0),
            "prompt_tokens": usage.get("total_input_tokens", 0),
            "thinking_tokens": usage.get("total_thought_tokens", 0),
            "thinking_used": bool(usage.get("total_thought_tokens", 0)),
            "prompt_version": self.prompt_version,
            "provider": self.provider,
            "model": data.get("model", self.model),
            "model_version_exposed": False,
            "evidence_normalizations": normalizations,
        }
