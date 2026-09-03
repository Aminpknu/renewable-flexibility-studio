"""Tail-risk summaries with an explicit investment-loss convention."""

from __future__ import annotations

from typing import Any

import numpy as np


def summarise_npv_distribution(npv_gbp: np.ndarray, confidence: float = 0.95) -> dict[str, Any]:
    """Summarise probabilistic NPV and loss=-NPV VaR/CVaR."""
    values = np.asarray(npv_gbp, dtype=float)
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("NPV samples must be a non-empty finite array.")
    if not 0 < confidence < 1:
        raise ValueError("confidence must lie in (0, 1).")
    losses = -values
    var_loss = float(np.quantile(losses, confidence))
    tail = losses[losses >= var_loss - 1e-12]
    cvar_loss = float(tail.mean())
    return {
        "simulation_count": int(values.size),
        "npv_p10_gbp": float(np.quantile(values, 0.10)),
        "npv_p50_gbp": float(np.quantile(values, 0.50)),
        "npv_p90_gbp": float(np.quantile(values, 0.90)),
        "mean_npv_gbp": float(values.mean()),
        "probability_negative_npv_pct": float(100.0 * np.mean(values < 0.0)),
        "loss_convention": "investment_loss_gbp = -NPV_gbp",
        "var_confidence_pct": float(confidence * 100.0),
        "var_loss_gbp": var_loss,
        "cvar_expected_shortfall_gbp": cvar_loss,
    }