import numpy as np
import numpy as np
import pandas as pd

from engine.battery import BatteryConfig
from engine.multiservice_predelivery import (
    attach_opportunity_cost_bids,
    build_issue_time_multiservice_schedule,
    score_issue_time_multiservice_schedule,
)


def _market() -> pd.DataFrame:
    times = pd.date_range("2026-05-01T00:00:00Z", periods=48, freq="30min")
    return pd.DataFrame({
        "settlement_period": range(1, 49),
        "valid_time_utc": times,
        "market_index_price_gbp_per_mwh": [50.0] * 48,
        "soc_floor_mwh": [20.0] * 48,
        "soc_ceiling_mwh": [180.0] * 48,
    })


def _service(actual_price: float = 12.0, actual_volume: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame([{
        "delivery_start_utc": pd.Timestamp("2026-05-01T06:00:00Z"),
        "product": "PQR", "family": "Quick Reserve", "direction": "upward",
        "window_hours": 0.5,
        "forecast_clearing_price_gbp_per_mw_per_hour": 10.0,
        "prior_same_window_price_gbp_per_mw_per_hour": 8.0,
        "clearing_price_gbp_per_mw_per_hour": actual_price,
        "cleared_volume_mw": actual_volume,
    }])


def _calibration() -> pd.DataFrame:
    return pd.DataFrame([
        {"sample_class":"standalone_parent","product":"PQR","margin_bin":"1:2","quantity_bin":"10:25","orders":300,"accepted_fraction_sum":180.0},
        {"sample_class":"standalone_parent","product":"PQR","margin_bin":"-10:-5","quantity_bin":"10:25","orders":300,"accepted_fraction_sum":240.0},
        {"sample_class":"nonlooped_parent","product":"PQR","margin_bin":"1:2","quantity_bin":"10:25","orders":500,"accepted_fraction_sum":250.0},
    ])


def test_issue_time_capacity_selection_ignores_realised_clearing_price() -> None:
    battery = BatteryConfig(25.0, 8.0, 0.90, 0.50)
    frame_a, contracts_a, summary_a = build_issue_time_multiservice_schedule(
        _market(), _service(1.0, 1.0), battery, _calibration()
    )
    frame_b, contracts_b, summary_b = build_issue_time_multiservice_schedule(
        _market(), _service(999.0, 9999.0), battery, _calibration()
    )
    assert contracts_a[["product", "contracted_mw"]].equals(contracts_b[["product", "contracted_mw"]])
    assert np.allclose(frame_a["multiservice_soc_end_mwh"], frame_b["multiservice_soc_end_mwh"])
    assert summary_a["uses_realised_service_clearing_price_for_selection"] is False
    assert summary_b["uses_realised_forecast_error_for_selection"] is False


def test_opportunity_cost_bid_and_acceptance_score_are_bounded() -> None:
    battery = BatteryConfig(25.0, 8.0, 0.90, 0.50)
    schedule, contracts, _ = build_issue_time_multiservice_schedule(
        _market(), _service(), battery, _calibration()
    )
    bids, _ = attach_opportunity_cost_bids(contracts, _market(), battery, _calibration())
    assert (bids["opportunity_cost_bid_gbp_per_mw_per_hour"] >= 0).all()
    assert bids["predicted_acceptance_ratio_at_bid_time"].between(0, 1).all()
    realised_market = pd.DataFrame({
        "settlement_period": range(1,49), "market_index_price_gbp_per_mwh": [50.0]*48,
    })
    realised_services = pd.DataFrame([{
        "product":"PQR", "delivery_start_utc":pd.Timestamp("2026-05-01T06:00:00Z"),
        "clearing_price_gbp_per_mw_per_hour":12.0, "cleared_volume_mw":300.0,
    }])
    scored, summary = score_issue_time_multiservice_schedule(
        schedule, bids, realised_market, realised_services
    )
    assert (scored["acceptance_calibrated_expected_accepted_mw"] <= scored["contracted_mw"] + 1e-9).all()
    assert summary["counterfactual_acceptance_is_exact"] is False
