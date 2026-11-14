"""Expire logs and unused policy cache; preserve replay inputs and active jobs."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from .repository import tables


def cleanup(service, apply=False, now=None):
    cutoff = (now or datetime.now(UTC)) - timedelta(days=30)
    with service.repo.connection() as conn:
        runs = conn.execute(select(tables["simulation_runs"].c.payload)).scalars().all()
        policies = conn.execute(select(tables["agent_evaluations"])).mappings().all()
    referenced = set()
    protected = any(r["completion_status"] != "complete" for r in runs)
    for run in runs:
        if run["completion_status"] == "complete":
            result = service.store.read_json(run["result_key"])
            if "policy_snapshot" not in result:
                protected = True
            referenced.update(p["key"] for p in result.get("policy_snapshot", []))
    expired = []
    if not protected:
        for policy in policies:
            created = policy["created_at"].replace(tzinfo=UTC)
            if created < cutoff and policy["id"] not in referenced:
                expired.append(policy["id"])
    logs = [
        p
        for p in service.store.root.rglob("*.log")
        if p.is_file() and not p.is_symlink() and datetime.fromtimestamp(p.stat().st_mtime, UTC) < cutoff
    ]
    if apply:
        with service.repo.transaction():
            if expired:
                with service.repo.connection() as conn:
                    conn.execute(
                        delete(tables["agent_evaluations"]).where(
                            tables["agent_evaluations"].c.id.in_(expired)
                        )
                    )
            for path in logs:
                path.unlink()
    return {
        "dry_run": not apply,
        "expired_policies": len(expired),
        "expired_logs": len(logs),
        "cache_protected_for_incomplete_runs": protected,
        "retention_days": 30,
    }
