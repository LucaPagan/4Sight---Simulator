"""Recurring Cloudflare Workers Free allowance; never upgrades or selects paid-only models."""

import json
import re
import time

import httpx

from .agents import evaluation_schema, validate_evaluation
from .cloud import (
    CloudQuotaError,
    CloudRateLimiter,
    CloudRuntimeError,
    post_with_retry,
    provider_message,
)
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, model_view

CLOUDFLARE_MODELS = {
    "@cf/google/gemma-4-26b-a4b-it": "Gemma 4 26B A4B · bilanciato",
    "@cf/zai-org/glm-4.7-flash": "GLM 4.7 Flash · confronto",
}
NEURON_RATES = {
    "@cf/google/gemma-4-26b-a4b-it": (9091, 27273),
    "@cf/zai-org/glm-4.7-flash": (5500, 36400),
}


class CloudflareClient:
    provider = "cloudflare"
    prompt_version = f"{PROMPT_VERSION}-cloudflare-chat-v1"

    def __init__(
        self,
        api_key,
        account_id,
        model="@cf/google/gemma-4-26b-a4b-it",
        free_tier_confirmed=False,
        requests_per_minute=30,
        transport=None,
        rate_limit_path=None,
    ):
        if model not in CLOUDFLARE_MODELS:
            raise ValueError("Modello Cloudflare non consentito")
        if account_id and not re.fullmatch(r"[a-fA-F0-9]{32}", account_id):
            raise ValueError("Account ID Cloudflare non valido: attesi 32 caratteri esadecimali")
        self.model, self.account_id = model, account_id
        self.configured = bool(api_key and account_id)
        self.free_tier_confirmed = free_tier_confirmed
        self.limiter = CloudRateLimiter(requests_per_minute, rate_limit_path)
        self.interval = self.limiter.interval
        self.http = httpx.Client(
            base_url="https://api.cloudflare.com",
            headers={"Authorization": f"Bearer {api_key}"},
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
            "digest": f"cloudflare:{self.model}:chat-v1" if ready else None,
            "digest_is_weights_hash": False,
            "prompt_version": self.prompt_version,
            "requests_per_minute": 60 / self.interval,
            "daily_free_neurons": 10000,
            "models": [{"name": m, "label": label} for m, label in CLOUDFLARE_MODELS.items()],
            "error": None
            if ready
            else "Configura token e Account ID Cloudflare e conferma il piano Workers Free.",
            "warning": "10.000 Neurons/giorno condivisi nell’account. Sul piano Free le chiamate oltre quota falliscono; sul piano Paid gli extra possono essere fatturati. Nessuna promessa di uso illimitato.",
        }

    def _check(self, response):
        if response.status_code in (429, 402):
            raise CloudQuotaError(provider="Cloudflare", detail=provider_message(response))
        if response.status_code in (401, 403):
            raise CloudRuntimeError(
                "Token Cloudflare o permessi Workers AI non validi. Verifica anche Account ID e piano Free."
            )
        if response.is_error:
            detail = provider_message(response)
            raise CloudRuntimeError(
                f"Cloudflare ha restituito HTTP {response.status_code}. Verifica modello, quota e configurazione; nessun fallback è stato chiamato."
                + (f" Messaggio del provider: {detail}" if detail else "")
            )

    def generate(self, system, user, schema, *, temperature=0.9, seed=None, max_tokens=4096):
        """One schema-constrained generation outside the evaluation flow (persona cards and similar)."""
        if not self.status()["ready"]:
            raise CloudRuntimeError(self.status()["error"])
        pacing = self.limiter.pace()
        start = time.monotonic()
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            "stream": False,
            "store": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "structured_output", "schema": schema, "strict": True},
            },
        }
        if seed is not None:
            body["seed"] = seed
        response = post_with_retry(
            self.http, f"/client/v4/accounts/{self.account_id}/ai/v1/chat/completions", body
        )
        self._check(response)
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("Risposta Cloudflare incompleta o bloccata")
        raw = choice["message"]["content"]
        usage = data.get("usage", {})
        return {
            "raw": raw if isinstance(raw, str) else json.dumps(raw),
            "seconds": time.monotonic() - start,
            "pacing_seconds": pacing,
            "tokens": usage.get("completion_tokens") or 0,
            "prompt_tokens": usage.get("prompt_tokens") or 0,
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
            f"/client/v4/accounts/{self.account_id}/ai/v1/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(view, ensure_ascii=False)},
                ],
                "temperature": 0,
                "seed": 42,
                "max_completion_tokens": 1024,
                "stream": False,
                "store": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "consumer_evaluation",
                        "schema": evaluation_schema(view),
                        "strict": True,
                    },
                },
            },
        )
        self._check(response)
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("Risposta Cloudflare incompleta o bloccata")
        raw = choice["message"]["content"]
        evaluation, normalizations = validate_evaluation(
            raw if isinstance(raw, str) else json.dumps(raw), view
        )
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        rate_in, rate_out = NEURON_RATES[self.model]
        estimate = (
            (prompt_tokens * rate_in + output_tokens * rate_out) / 1e6
            if prompt_tokens is not None and output_tokens is not None
            else None
        )
        return {
            "evaluation": evaluation,
            "seconds": time.monotonic() - start,
            "pacing_seconds": pacing,
            "tokens": output_tokens or 0,
            "prompt_tokens": prompt_tokens or 0,
            "prompt_version": self.prompt_version,
            "provider": self.provider,
            "model": data.get("model", self.model),
            "model_version_exposed": False,
            "system_fingerprint": data.get("system_fingerprint"),
            "thinking_used": bool(usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)),
            "estimated_neurons": estimate,
            "neuron_estimate_note": "Stima dai token e dalle tariffe pubblicate, non lettura del consumo totale dell’account.",
            "evidence_normalizations": normalizations,
        }
