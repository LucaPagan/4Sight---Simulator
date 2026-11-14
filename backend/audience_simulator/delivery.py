"""Ad delivery: how a daily budget becomes spend and impressions. Independent of the panel.

Consumer interest does not set the platform's auction price. Spend follows the budget, the adset's observed
utilisation and the historical allocation between ads; impressions follow spend and CPM. Nothing in this
module reads panel evaluations. Platform optimisation toward better-performing creatives is not modelled.
"""

import numpy as np

DELIVERY_MODE = "history_allocation_independent_of_panel"
DELIVERY_NOTE = (
    "Spesa e impression seguono budget, utilizzo storico e allocazione storica tra annunci; "
    "non dipendono dal panel. L'ottimizzazione della piattaforma verso la creatività migliore non è modellata."
)


def allocate_spend(rows, models, rng, n_draws):
    """Monte Carlo daily spend per row. The draw order is part of the contract (seeded reproducibility)."""
    spend = np.zeros((n_draws, len(rows)))
    for (_, adset), ids in rows.groupby(["data", "adset_id"], sort=False).groups.items():
        idx = np.asarray(list(ids))
        budget = rows.loc[idx, "budget_giornaliero_adset"].to_numpy(float)
        if not np.allclose(budget, budget[0]):
            raise ValueError("Budget adset-giorno incoerente")
        usage = np.clip(models.utilization.get(adset, 0.95) + rng.normal(0, 0.025, n_draws), 0, 1)
        known = np.array(
            [
                models.allocation.get(a, np.median(list(models.allocation.values())))
                for a in rows.loc[idx, "ad_id"]
            ]
        )
        weights = np.maximum(known, 0.1)[None, :] * np.exp(rng.normal(0, 0.15, (n_draws, len(idx))))
        weights /= weights.sum(axis=1, keepdims=True)
        spend[:, idx] = budget[0] * usage[:, None] * weights
    return spend


def impressions_from(spend, cpm_draw):
    return spend / cpm_draw * 1000
