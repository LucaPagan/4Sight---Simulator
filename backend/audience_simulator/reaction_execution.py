"""Bounded reaction calls; only the coordinator touches storage and progress."""

import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import httpx

from .cloud import CloudRuntimeError
from .performance import add_usage, stage_metrics
from .reactions import decide


def run_reaction_plan(
    repo,
    client,
    plan,
    digest,
    *,
    concurrency=1,
    max_attempts=3,
    max_evaluations=5000,
    performance=None,
    progress=None,
    canceled=lambda: False,
    stop_on_invalid=True,
):
    if not 1 <= concurrency <= 4:
        raise ValueError("Concorrenza reazioni: scegliere da 1 a 4")
    if client.provider in {"gemini", "cloudflare"}:
        concurrency = 1
    metrics = stage_metrics(performance)
    decisions, failed, retries = {}, [], deque()
    source, pending = iter(plan), {}
    exhausted, stopped, error, calls = False, False, None, 0
    last_tick = time.monotonic()

    def notify():
        nonlocal last_tick
        now = time.monotonic()
        metrics["seconds"] += now - last_tick
        last_tick = now
        if progress:
            progress(decisions, metrics)

    def call(item, attempt):
        try:
            record = decide(client, item["input"], attempt=attempt)
            return record, None, record
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return None, exc, getattr(exc, "generation_metrics", {})

    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="reaction") as executor:
        while True:
            if canceled():
                stopped = True
            while not stopped and len(pending) < concurrency and (retries or not exhausted):
                if canceled():
                    stopped = True
                    break
                if retries:
                    item, attempt = retries.popleft()
                else:
                    item = next(source, None)
                    if item is None:
                        exhausted = True
                        break
                    attempt = 0
                    cached = repo.get_decision(item["key"])
                    if cached:
                        decisions[item["key"]] = cached["result"]
                        metrics["cache_hits"] += 1
                        notify()
                        continue
                if calls >= max_evaluations:
                    error = ValueError(
                        "Limite valutazioni raggiunto. Riprendi per completare le reazioni mancanti."
                    )
                    stopped = True
                    break
                calls += 1
                metrics["calls"] += 1
                metrics["attempts"] += 1
                pending[executor.submit(call, item, attempt)] = (item, attempt)
            if not pending:
                break
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                item, attempt = pending.pop(future)
                record, exc, usage = future.result()
                add_usage(metrics, usage)
                if exc is None:
                    repo.save_decision(item["key"], {"digest": digest, "result": record})
                    decisions[item["key"]] = record
                else:
                    metrics["errors"] += 1
                    if isinstance(exc, (CloudRuntimeError, httpx.ConnectError)):
                        error = error or exc
                        stopped = True
                    else:
                        metrics["rejected"] += 1
                        if not stopped and attempt + 1 < max_attempts:
                            retries.append((item, attempt + 1))
                        else:
                            failed.append(item["key"])
                            if stop_on_invalid:
                                error = error or ValueError(
                                    f"Reazione {item['agent_id']}/{item['creative_id']}: {type(exc).__name__}"
                                )
                                stopped = True
                notify()
    notify()
    return {
        "decisions": {item["key"]: decisions[item["key"]] for item in plan if item["key"] in decisions},
        "performance": metrics,
        "failed": failed,
        "error": error,
        "canceled": canceled(),
    }
