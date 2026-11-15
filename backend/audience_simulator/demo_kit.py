"""Dataset dimostrativo, interamente sintetico e deterministico.

Serve a far funzionare l'app subito dopo il clone, senza il kit dell'hackathon (che non si
redistribuisce). Ha lo stesso schema dei 13 CSV originali, quindi passa lo stesso audit e usa
la stessa pipeline; i numeri sono inventati e non descrivono alcun mercato reale.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .datasets import ASSETS, FILES

LAST_HISTORY = date(2026, 11, 15)
FIRST_DAY = date(2026, 8, 17)
LAST_DAY = date(2026, 11, 30)
WEEKDAYS = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
EVENTS = {
    date(2026, 9, 1): "Rientro dalle ferie",
    date(2026, 10, 31): "Halloween",
    date(2026, 11, 1): "Ognissanti (festivo)",
    date(2026, 11, 11): "Singles Day",
    date(2026, 11, 20): "Inizio Black Week (venerdi)",
    date(2026, 11, 27): "Black Friday",
    date(2026, 11, 30): "Cyber Monday",
}
# (id, nome, vertical, descrizione, base CTR %, base CPM €, budget di partenza)
BRANDS = [
    (
        "AUR",
        "Aurora Skin Lab",
        "beauty_skincare",
        "E-commerce di skincare: sieri, creme viso, detergenti.",
        1.25,
        10.0,
        100,
    ),
    (
        "ZMF",
        "Zampa Felice",
        "pet_ecommerce",
        "E-commerce di cibo, snack e accessori per cani e gatti.",
        1.35,
        7.2,
        70,
    ),
    (
        "TRU",
        "Trama Urbana",
        "abbigliamento",
        "Marchio di abbigliamento uomo e donna, fascia media.",
        1.30,
        9.0,
        80,
    ),
]
LEVER_PLAN = [  # (lever, format, video seconds, launch, end) per asset, 4 per leva
    ("scarcity", "immagine", None, "2026-08-01", None),
    ("scarcity", "video", 18, "2026-09-07", None),
    ("scarcity", "carosello", None, "2026-10-05", None),
    ("scarcity", "immagine", None, "2026-10-26", None),
    ("urgency", "video", 15, "2026-08-01", "2026-09-20"),
    ("urgency", "immagine", None, "2026-09-07", "2026-10-18"),
    ("urgency", "video", 22, "2026-10-05", None),
    ("urgency", "carosello", None, "2026-10-26", None),
    ("black_friday", "immagine", None, "2026-11-09", None),
    ("black_friday", "video", 16, "2026-11-12", None),
    ("black_friday", "carosello", None, "2026-11-20", None),
    ("black_friday", "video", 14, "2026-11-23", None),
]
COPY = {
    "beauty_skincare": [
        (
            "Siero illuminante: ultimi 200 flaconi",
            "Il lotto è quasi finito. Quando termina, torna a novembre.",
        ),
        ("Torna disponibile, ma per poco", "La crema più richiesta è di nuovo qui, in quantità limitata."),
        ("Edizione limitata: kit routine autunno", "Solo 500 kit numerati con detergente, siero e crema."),
        ("Ultimo lotto della crema notte", "Dopo questo non ne produciamo altri fino a primavera."),
        ("Solo fino a mezzanotte: -20%", "Lo sconto sulla routine viso finisce stasera."),
        ("Spedizione gratis: scade domenica", "Ordina entro domenica e non paghi la spedizione."),
        ("48 ore per la tua routine a -15%", "Due giorni per completare la routine con lo sconto."),
        ("Ultime 24 ore: regalo con ogni ordine", "Un mini-siero in omaggio fino a domani sera."),
        ("Black Friday anticipato: -25%", "Parte prima: tutta la linea viso con il 25% in meno."),
        ("La Black Week è iniziata", "Sconti sulle routine complete, fino a esaurimento."),
        ("Black Friday: fino al -40%", "I kit più amati con lo sconto più alto dell'anno."),
        ("Black Friday: solo oggi", "Ultima occasione: tutto al prezzo più basso."),
    ],
    "pet_ecommerce": [
        ("Croccantini grain-free: ultime scorte", "Il lotto di cibo per cani sta finendo, ordina ora."),
        ("Torna la lettiera top, per poco", "Disponibile di nuovo per pochi giorni."),
        ("Box snack autunno, solo 300 pezzi", "Una scatola numerata di snack per cani e gatti."),
        ("Cuccia invernale: ultimi pezzi", "Le ultime cucce imbottite prima della stagione fredda."),
        ("Snack 3x2 solo oggi", "Prendi tre confezioni, ne paghi due. Scade a mezzanotte."),
        ("Spedizione gratis fino a domenica", "Per ogni ordine, senza soglia minima."),
        ("48 ore: -15% sul cibo umido", "Due giorni per fare scorta con lo sconto."),
        ("Ultime ore: giocattolo in omaggio", "Un regalo per il tuo animale con ogni ordine."),
        ("Black Friday anticipato: -25%", "Cibo e accessori con il 25% in meno."),
        ("La Black Week è iniziata", "Offerte ogni giorno su cibo e accessori."),
        ("Black Friday: fino al -35%", "Il prezzo più basso dell'anno per i tuoi amici a quattro zampe."),
        ("Black Friday: solo oggi -35%", "Ultime ore per fare scorta."),
    ],
    "abbigliamento": [
        ("Cappotto in lana: ultimi pezzi", "Le taglie rimaste del cappotto più venduto."),
        ("Torna il maglione, ma per poco", "Riassortimento limitato in tre colori."),
        ("Capsule autunno: 400 pezzi", "Una collezione numerata, mai più ristampata."),
        ("Ultime taglie del giubbotto", "Quando finiscono, non rientrano."),
        ("Solo fino a stasera: -20%", "Lo sconto sulla maglieria termina a mezzanotte."),
        ("Resi gratis fino a domenica", "Prova a casa e restituisci senza costi."),
        ("48 ore: -15% su jeans e felpe", "Due giorni per rinnovare l'armadio."),
        ("Ultime 24 ore: sciarpa in omaggio", "Una sciarpa con ogni ordine fino a domani."),
        ("Black Friday anticipato: -25%", "Tutta la collezione inverno con il 25% in meno."),
        ("La Black Week è iniziata", "Ogni giorno nuove offerte sull'abbigliamento."),
        ("Black Friday: fino al -40%", "I capi più amati al prezzo più basso."),
        ("Black Friday: solo oggi -40%", "Ultime ore per approfittarne."),
    ],
}
VISUAL = {
    "immagine": "Foto del prodotto su sfondo pieno con prezzo e scritta in evidenza.",
    "video": "Video verticale con il prodotto in uso e testo sovraimpresso.",
    "carosello": "Carosello di cinque schede con prodotto, dettagli e offerta.",
}
CTA = {"scarcity": "Scopri di più", "urgency": "Acquista ora", "black_friday": "Approfitta dell'offerta"}
LEVER_CTR = {"scarcity": 1.0, "urgency": 1.06, "black_friday": 1.12}
FORMAT_CTR = {"immagine": 1.0, "video": 1.08, "carosello": 1.03}
LEVER_ORDER = ["S", "U", "B"]


def _active(day: date, launch: str, end: str | None) -> bool:
    return date.fromisoformat(launch) <= day and (end is None or day <= date.fromisoformat(end))


def write_demo_kit(root: Path, seed: int = 7) -> Path:
    root = Path(root)
    (root / "asset_creativi").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    days = [FIRST_DAY + timedelta(days=i) for i in range((LAST_DAY - FIRST_DAY).days + 1)]

    def period(day):
        return (
            "test" if day > LAST_HISTORY else "validazione" if day >= date(2026, 11, 2) else "addestramento"
        )

    calendar = pd.DataFrame(
        {
            "data": [d.isoformat() for d in days],
            "giorno_settimana": [WEEKDAYS[d.weekday()] for d in days],
            "weekend": ["si" if d.weekday() >= 5 else "no" for d in days],
            "evento": [EVENTS.get(d, "") for d in days],
            "periodo": [period(d) for d in days],
        }
    )
    advertisers: list[dict[str, Any]] = []
    campaigns: list[dict[str, Any]] = []
    adsets: list[dict[str, Any]] = []
    assets_by_vertical: dict[str, list[dict[str, Any]]] = {}
    ads: list[dict[str, Any]] = []
    budgets: list[dict[str, Any]] = []
    for code, name, vertical, description, _, _, budget in BRANDS:
        advertisers.append(
            {"inserzionista_id": code, "nome": name, "vertical": vertical, "descrizione": description}
        )
        campaigns.append(
            {
                "campaign_id": f"{code}-C1",
                "inserzionista_id": code,
                "vertical": vertical,
                "piattaforma": "meta",
                "obiettivo": "vendite",
                "campaign_name": f"{code} | Vendite | {vertical}",
                "data_inizio": "2026-08-01",
            }
        )
        for k in range(1, 5):
            adsets.append(
                {
                    "adset_id": f"{code}-AS{k}",
                    "campaign_id": f"{code}-C1",
                    "adset_name": f"{code} | Ad set {k}",
                    "ottimizzazione": "acquisti",
                    "strategia_offerta": "costo più basso (senza limite)",
                    "budget_giornaliero_iniziale": int(budget * (0.6 + 0.3 * k)),
                    "pubblico": "da definire",
                }
            )
            base = int(budget * (0.6 + 0.3 * k))
            for day in days:
                budgets.append(
                    {
                        "data": day.isoformat(),
                        "adset_id": f"{code}-AS{k}",
                        "budget_giornaliero_eur": float(base if day <= LAST_HISTORY else round(base * 1.25)),
                        "periodo": "test" if day > LAST_HISTORY else "addestramento",
                    }
                )
        rows: list[dict[str, Any]] = []
        for i, (lever, fmt, seconds, launch, end) in enumerate(LEVER_PLAN):
            head, text = COPY[vertical][i]
            rows.append(
                {
                    "asset_id": f"{code}-{LEVER_ORDER[i // 4]}{i % 4 + 1}",
                    "vertical": vertical,
                    "leva": lever,
                    "formato": fmt,
                    "durata_video_s": seconds,
                    "headline": head,
                    "testo_principale": text,
                    "call_to_action": CTA[lever],
                    "descrizione_visual": VISUAL[fmt],
                    "data_lancio": launch,
                    "data_fine": end,
                }
            )
        assets_by_vertical[vertical] = rows
        # Ogni asset serve due annunci in ad set diversi: 24 annunci per marchio.
        for n, row in enumerate(rows * 2, start=1):
            adset_id = f"{code}-AS{(n - 1) % 4 + 1}"
            ads.append(
                {
                    "ad_id": f"{code}-AD{n:02d}",
                    "campaign_id": f"{code}-C1",
                    "adset_id": adset_id,
                    "asset_id": row["asset_id"],
                    "ad_name": f"{row['leva']} | {row['formato']} | {row['headline']}",
                    "data_lancio": row["data_lancio"],
                    "data_fine": row["data_fine"],
                }
            )

    asset_index = {a["asset_id"]: a for rows in assets_by_vertical.values() for a in rows}
    brand = {b[0]: b for b in BRANDS}
    budget_map = {(b["data"], b["adset_id"]): b["budget_giornaliero_eur"] for b in budgets}
    history: list[dict[str, Any]] = []
    future: list[dict[str, Any]] = []
    for day in days:
        iso = day.isoformat()
        weekend = day.weekday() >= 5
        event = EVENTS.get(day, "")
        black = day >= date(2026, 11, 20)
        for adset in adsets:
            live = [
                a
                for a in ads
                if a["adset_id"] == adset["adset_id"] and _active(day, a["data_lancio"], a["data_fine"])
            ]
            if not live:
                continue
            budget = budget_map[(iso, adset["adset_id"])]
            if day > LAST_HISTORY:
                for a in live:
                    asset = asset_index[a["asset_id"]]
                    future.append(
                        {
                            "data": iso,
                            "giorno_settimana": WEEKDAYS[day.weekday()],
                            "piattaforma": "meta",
                            "vertical": asset["vertical"],
                            "campaign_id": a["campaign_id"],
                            "adset_id": a["adset_id"],
                            "ad_id": a["ad_id"],
                            "asset_id": a["asset_id"],
                            "leva": asset["leva"],
                            "formato": asset["formato"],
                            "budget_giornaliero_adset": budget,
                        }
                    )
                continue
            weights = rng.dirichlet(np.full(len(live), 8.0))
            total = budget * rng.uniform(0.9, 0.985)
            for a, w in zip(live, weights, strict=True):
                code = a["campaign_id"].split("-")[0]
                _, _, vertical, _, base_ctr, base_cpm, _ = brand[code]
                asset = asset_index[a["asset_id"]]
                age = (day - date.fromisoformat(a["data_lancio"])).days
                ctr = base_ctr * LEVER_CTR[asset["leva"]] * FORMAT_CTR[asset["formato"]]
                ctr *= (1.05 if weekend else 1.0) * (1.08 if event else 1.0) * max(0.8, 1 - 0.004 * age)
                cpm = (
                    base_cpm
                    * (1.12 if weekend else 1.0)
                    * (1.25 if black or event else 1.0)
                    * rng.lognormal(0, 0.08)
                )
                spend = round(float(total * w), 2)
                impressions = max(int(spend / cpm * 1000), 300)
                clicks = int(rng.binomial(impressions, min(0.2, ctr * rng.lognormal(0, 0.12) / 100)))
                reach = max(int(impressions / rng.uniform(1.03, 1.3)), 1)
                history.append(
                    {
                        "data": iso,
                        "giorno_settimana": WEEKDAYS[day.weekday()],
                        "piattaforma": "meta",
                        "inserzionista_id": code,
                        "vertical": vertical,
                        "campaign_id": a["campaign_id"],
                        "campaign_name": f"{code} | Vendite | {vertical}",
                        "adset_id": a["adset_id"],
                        "ad_id": a["ad_id"],
                        "asset_id": a["asset_id"],
                        "leva": asset["leva"],
                        "formato": asset["formato"],
                        "budget_giornaliero_adset": budget,
                        "spesa": spend,
                        "impression": impressions,
                        "copertura": reach,
                        "frequenza": round(impressions / reach, 4),
                        "click": clicks,
                        "ctr": round(100 * clicks / impressions, 4),
                        "cpc": round(spend / clicks, 4) if clicks else None,
                        "cpm": round(1000 * spend / impressions, 4),
                    }
                )

    market: list[dict[str, Any]] = []
    for month in range(22):
        year, mon = divmod(month, 12)
        label = f"{2025 + year}-{mon + 1:02d}"
        for platform, factor in (("meta", 1.0), ("tiktok", 0.8)):
            for country, cfactor in (("IT", 1.0), ("ES", 0.85), ("FR", 1.1), ("DE", 1.25)):
                for goal, gfactor in (
                    ("vendite", 1.0),
                    ("lead", 1.2),
                    ("traffico", 0.55),
                    ("notorieta", 0.4),
                ):
                    mid = round(
                        6 * factor * cfactor * gfactor * (1.3 if mon >= 9 else 1.0) * rng.uniform(0.92, 1.08),
                        2,
                    )
                    market.append(
                        {
                            "piattaforma": platform,
                            "paese": country,
                            "mese": label,
                            "obiettivo": goal,
                            "cpm_mediano": mid,
                            "cpm_q1": round(mid * 0.72, 2),
                            "cpm_q3": round(mid * 1.42, 2),
                            "n_campagne": int(rng.integers(42, 1700)),
                        }
                    )
    weekly: list[dict[str, Any]] = []
    for week in range(22):
        monday = date(2025, 8, 4) + timedelta(weeks=week)
        for _, _, vertical, *_ in BRANDS:
            peak = 1 + 0.35 * max(0, (week - 15) / 6)
            weekly.append(
                {
                    "settimana_dal": monday.isoformat(),
                    "vertical": vertical,
                    "piattaforma": "meta",
                    "paese": "IT",
                    "indice_cpm": round(95 * peak * rng.uniform(0.85, 1.1), 1),
                    "indice_ctr": round(100 * rng.uniform(0.9, 1.12), 1),
                }
            )

    frames = {
        "history": history,
        "future": future,
        "calendar": calendar,
        "budgets": budgets,
        "ads": ads,
        "adsets": adsets,
        "campaigns": campaigns,
        "advertisers": advertisers,
        "cpm_market": market,
        "weekly_market": weekly,
    }
    for key, rows in frames.items():
        frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
        frame.to_csv(root / FILES[key], index=False)
    for vertical, rows in assets_by_vertical.items():
        pd.DataFrame(rows).to_csv(root / f"asset_creativi/asset_{vertical}.csv", index=False)
    assert all((root / a).exists() for a in ASSETS)
    return root
