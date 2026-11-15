"""Shared counters for native stages; seconds include unsuccessful calls and pacing."""


def stage_metrics(previous=None):
    return {
        **dict.fromkeys(
            (
                "calls",
                "accepted",
                "attempts",
                "rejected",
                "corrections",
                "errors",
                "cache_hits",
                "fallback",
                "tokens",
                "prompt_tokens",
            ),
            0,
        ),
        "seconds": 0.0,
        "pacing_seconds": 0.0,
        **(previous or {}),
    }


def add_usage(metrics, result):
    for key in ("tokens", "prompt_tokens", "pacing_seconds"):
        metrics[key] += result.get(key, 0) or 0
