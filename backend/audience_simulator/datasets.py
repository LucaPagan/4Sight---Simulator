"""Immutable CSV ingestion and an audit that separates raw anomalies from invalid structure."""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

FILES = {
    "history": "storico_giornaliero.csv",
    "future": "da_prevedere.csv",
    "calendar": "calendario.csv",
    "budgets": "budget_giornaliero.csv",
    "ads": "annunci.csv",
    "adsets": "adset.csv",
    "campaigns": "campagne.csv",
    "advertisers": "inserzionisti.csv",
    "cpm_market": "cpm_storici.csv",
    "weekly_market": "benchmark_mercato_settimanale_2025.csv",
}
ASSETS = [f"asset_creativi/asset_{v}.csv" for v in ["beauty_skincare", "pet_ecommerce", "abbigliamento"]]
KEYS = {
    "history": ["data", "ad_id"],
    "future": ["data", "ad_id"],
    "calendar": ["data"],
    "budgets": ["data", "adset_id"],
    "ads": ["ad_id"],
    "adsets": ["adset_id"],
    "campaigns": ["campaign_id"],
    "advertisers": ["inserzionista_id"],
    "assets": ["asset_id"],
}
CONTEXT = [
    "data",
    "piattaforma",
    "vertical",
    "campaign_id",
    "adset_id",
    "ad_id",
    "asset_id",
    "leva",
    "formato",
    "budget_giornaliero_adset",
]
REQUIRED = {
    "history": CONTEXT + ["click", "impression", "spesa", "ctr", "cpm", "cpc", "copertura", "frequenza"],
    "future": CONTEXT,
    "calendar": ["data", "periodo", "evento", "weekend"],
    "budgets": ["data", "adset_id", "budget_giornaliero_eur", "periodo"],
    "ads": ["ad_id", "adset_id", "campaign_id", "asset_id", "data_lancio", "data_fine"],
    "adsets": ["adset_id", "campaign_id", "pubblico"],
    "campaigns": ["campaign_id", "inserzionista_id", "vertical", "piattaforma", "obiettivo"],
    "advertisers": ["inserzionista_id", "nome", "vertical"],
    "assets": [
        "asset_id",
        "vertical",
        "leva",
        "formato",
        "headline",
        "testo_principale",
        "call_to_action",
        "descrizione_visual",
        "data_lancio",
        "data_fine",
    ],
    "cpm_market": ["piattaforma", "paese", "mese", "obiettivo", "cpm_mediano", "cpm_q1", "cpm_q3"],
    "weekly_market": ["settimana_dal", "vertical", "piattaforma", "paese", "indice_ctr", "indice_cpm"],
}


def load_dataset(root: Path, validate: bool = False) -> dict:
    root = Path(root)
    if validate:
        result = audit_dataset(root)
        if result["errors"]:
            raise ValueError("; ".join(result["errors"]))
    tables = {key: pd.read_csv(root / name, encoding="utf-8-sig") for key, name in FILES.items()}
    tables["assets"] = pd.concat(
        [pd.read_csv(root / f, encoding="utf-8-sig") for f in ASSETS], ignore_index=True
    )
    tables["future"]["row_index"] = np.arange(len(tables["future"]))
    return tables


def audit_dataset(root: Path) -> dict:
    root = Path(root)
    report: dict = {
        "counts": {},
        "errors": [],
        "warnings": [],
        "overspend": [],
        "manifest": [],
        "source_type": "provided_dataset",
        "synthetic_dataset": True,
    }
    for file in [*FILES.values(), *ASSETS]:
        path = root / file
        if not path.is_file():
            report["errors"].append(f"missing file: {file}")
            continue
        raw = path.read_bytes()
        report["manifest"].append(
            {"file": file, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        )
        try:
            report["counts"][path.name] = len(pd.read_csv(path, encoding="utf-8-sig"))
        except (ValueError, UnicodeError) as exc:
            report["errors"].append(f"invalid CSV {file}: {exc}")
    report["dataset_hash"] = hashlib.sha256(str(report["manifest"]).encode()).hexdigest()
    if report["errors"]:
        return report
    kit = load_dataset(root)
    for name, required in REQUIRED.items():
        missing = set(required) - set(kit[name].columns)
        if missing:
            report["errors"].append(f"{name}: missing columns {sorted(missing)}")
    if report["errors"]:
        return report
    numeric = {
        "history": [
            "budget_giornaliero_adset",
            "click",
            "impression",
            "spesa",
            "ctr",
            "cpm",
            "cpc",
            "copertura",
            "frequenza",
        ],
        "future": ["budget_giornaliero_adset"],
        "budgets": ["budget_giornaliero_eur"],
        "cpm_market": ["cpm_mediano", "cpm_q1", "cpm_q3"],
        "weekly_market": ["indice_ctr", "indice_cpm"],
    }
    for name, columns in numeric.items():
        for col in columns:
            raw = kit[name][col]
            values = pd.to_numeric(raw, errors="coerce")
            missing_allowed = (name, col) == ("history", "cpc")
            if (
                (values.isna() & (raw.notna() if missing_allowed else True)).any()
                or np.isinf(values).any()
                or (values < 0).any()
            ):
                report["errors"].append(f"{name}: invalid numeric {col}")
            kit[name][col] = values
    if report["errors"]:
        return report
    for name, keys in KEYS.items():
        if kit[name].duplicated(keys).any():
            report["errors"].append(f"{name}: duplicate key {keys}")
        if kit[name][keys].isna().any().any():
            report["errors"].append(f"{name}: missing key")
    for name in ["history", "future", "calendar", "budgets"]:
        if pd.to_datetime(kit[name].data, errors="coerce").isna().any():
            report["errors"].append(f"{name}: invalid date")
    for child, parent, key in [
        ("ads", "adsets", "adset_id"),
        ("ads", "assets", "asset_id"),
        ("adsets", "campaigns", "campaign_id"),
        ("campaigns", "advertisers", "inserzionista_id"),
        ("history", "ads", "ad_id"),
        ("future", "ads", "ad_id"),
    ]:
        if not set(kit[child][key]).issubset(set(kit[parent][key])):
            report["errors"].append(f"{child}: invalid reference {key}")
    if report["errors"]:
        return report
    h, f, cal, budget = (kit[k] for k in ["history", "future", "calendar", "budgets"])
    for name, rows in [("history", h), ("future", f)]:
        if (rows.budget_giornaliero_adset < 0).any():
            report["errors"].append(f"{name}: negative budget")
        for key in ["ads", "assets"]:
            idcol = "ad_id" if key == "ads" else "asset_id"
            joined = rows.merge(
                kit[key][[idcol, "data_lancio", "data_fine"]], on=idcol, validate="many_to_one"
            )
            if (
                (joined.data < joined.data_lancio)
                | (joined.data_fine.notna() & (joined.data > joined.data_fine))
            ).any():
                report["errors"].append(f"{name}: inactive {key}")
        joined = rows.merge(
            budget[["data", "adset_id", "budget_giornaliero_eur"]],
            on=["data", "adset_id"],
            how="left",
            validate="many_to_one",
        )
        if joined.budget_giornaliero_eur.isna().any() or not np.allclose(
            joined.budget_giornaliero_adset, joined.budget_giornaliero_eur
        ):
            report["errors"].append(f"{name}: budget mismatch")
    for col in ["click", "impression", "spesa", "copertura"]:
        if not np.isfinite(h[col]).all() or (h[col] < 0).any():
            report["errors"].append(f"history: invalid {col}")
    if (h.click > h.impression).any() or (h.impression <= 0).any():
        report["errors"].append("history: invalid impression/click counts")
    if not np.allclose(h.ctr, 100 * h.click / h.impression, atol=0.000051, rtol=0):
        report["errors"].append("history: inconsistent ctr")
    if not np.allclose(h.cpm, 1000 * h.spesa / h.impression, atol=0.000051, rtol=0):
        report["errors"].append("history: inconsistent cpm")
    if (h.cpc.isna() != (h.click == 0)).any():
        report["errors"].append("history: invalid missing cpc")
    report["cpc_missing_zero_click"] = int((h.cpc.isna() & (h.click == 0)).sum())
    joined = budget.merge(cal[["data", "periodo"]], on="data", suffixes=("_raw", "_calendar"), how="left")
    report["budget_period_mismatches"] = int((joined.periodo_raw != joined.periodo_calendar).sum())
    split = h.merge(cal[["data", "periodo"]], on="data", how="left")
    report["split_counts"] = {str(k): int(v) for k, v in split.periodo.value_counts().items()}
    groups = (
        h.groupby(["data", "adset_id"], as_index=False).spesa.sum().merge(budget, on=["data", "adset_id"])
    )
    for row in groups.loc[groups.spesa > groups.budget_giornaliero_eur + 1e-8].to_dict("records"):
        report["overspend"].append(
            {
                "date": row["data"],
                "adset_id": row["adset_id"],
                "spend": row["spesa"],
                "budget": row["budget_giornaliero_eur"],
                "severity": "error" if row["spesa"] - row["budget_giornaliero_eur"] > 0.02 else "rounding",
            }
        )
    report["cold_start_ads"] = sorted(set(f.ad_id) - set(h.ad_id))
    report["cold_start_assets"] = sorted(set(f.asset_id) - set(h.asset_id))
    report["warnings"] = [
        "Dataset simulato; nessuna label demografica.",
        "Paese IT e audience sono assunzioni.",
        "Calendario autoritativo per lo split.",
        "Benchmark senza data di pubblicazione: disponibilità assunta nel kit.",
    ]
    return report
