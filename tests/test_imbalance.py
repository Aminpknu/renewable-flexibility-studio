import pandas as pd
import pytest

from engine.imbalance import apply_imbalance_settlement, summarise_imbalance_settlement


def _simulation() -> pd.DataFrame:
    return pd.DataFrame({
        "settlement_period": [1, 2],
        "forecast_error_mw": [-10.0, 5.0],
        "residual_error_mw": [-2.0, 1.0],
    })


def _prices() -> pd.DataFrame:
    return pd.DataFrame({
        "settlement_period": [1, 2],
        "system_price_gbp_per_mwh": [100.0, 100.0],
        "net_imbalance_volume_mwh": [200.0, -150.0],
        "system_direction": ["short", "long"],
    })


def test_bsc_style_cashflow_and_exposure_math() -> None:
    settled = apply_imbalance_settlement(_simulation(), _prices())
    assert settled["imbalance_before_mwh"].tolist() == [-5.0, 2.5]
    assert settled["settlement_cashflow_before_gbp"].tolist() == [500.0, -250.0]
    assert settled["settlement_cashflow_after_gbp"].tolist() == [100.0, -50.0]
    summary = summarise_imbalance_settlement(settled)
    assert summary["gross_exposure_before_gbp"] == pytest.approx(750.0)
    assert summary["gross_exposure_after_gbp"] == pytest.approx(150.0)
    assert summary["gross_exposure_reduction_pct"] == pytest.approx(80.0)
    assert summary["signed_cashflow_before_gbp"] == pytest.approx(250.0)
    assert summary["signed_cashflow_after_gbp"] == pytest.approx(50.0)


def test_directional_system_support_is_sign_based() -> None:
    prices = _prices()
    prices["net_imbalance_volume_mwh"] = [-200.0, 150.0]
    prices["system_direction"] = ["long", "short"]
    settled = apply_imbalance_settlement(_simulation(), prices)
    assert settled["direction_helpful_before"].tolist() == [True, True]


def test_missing_price_period_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing"):
        apply_imbalance_settlement(_simulation(), _prices().iloc[[0]].copy())


def test_multiday_join_uses_date_and_period() -> None:
    simulation = pd.DataFrame({
        "settlement_date": ["2026-06-29", "2026-06-30"],
        "settlement_period": [1, 1],
        "forecast_error_mw": [-2.0, -2.0],
        "residual_error_mw": [-1.0, -1.0],
    })
    prices = pd.DataFrame({
        "settlement_date": ["2026-06-29", "2026-06-30"],
        "settlement_period": [1, 1],
        "system_price_gbp_per_mwh": [50.0, 150.0],
        "net_imbalance_volume_mwh": [1.0, 1.0],
        "system_direction": ["short", "short"],
    })
    settled = apply_imbalance_settlement(simulation, prices)
    assert settled["settlement_cashflow_before_gbp"].tolist() == [50.0, 150.0]
