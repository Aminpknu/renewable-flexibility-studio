from __future__ import annotations

import numpy as np
import pytest

from engine.tail_risk import summarise_npv_distribution


def test_tail_risk_uses_loss_equals_negative_npv_convention() -> None:
    npv = np.array([-100.0, -50.0, 0.0, 50.0, 100.0])
    result = summarise_npv_distribution(npv, confidence=0.80)
    assert result["loss_convention"] == "investment_loss_gbp = -NPV_gbp"
    assert result["probability_negative_npv_pct"] == pytest.approx(40.0)
    assert result["var_loss_gbp"] == pytest.approx(60.0)
    assert result["cvar_expected_shortfall_gbp"] == pytest.approx(100.0)


def test_cvar_is_at_least_var_for_loss_tail() -> None:
    result = summarise_npv_distribution(np.array([-10.0, -5.0, 0.0, 5.0, 10.0]))
    assert result["cvar_expected_shortfall_gbp"] >= result["var_loss_gbp"]


def test_tail_risk_rejects_empty_samples() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        summarise_npv_distribution(np.array([]))