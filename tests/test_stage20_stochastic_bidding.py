import numpy as np
import pandas as pd
import pytest

from engine.battery import BatteryConfig
from engine.stochastic_bidding import (
    StochasticBiddingConfig, build_stochastic_market_scenarios,
    optimise_stochastic_wholesale_bm,
)


def _base_prices(values=(20, 20, 100, 100)):
    return pd.DataFrame({
        "settlement_period": range(1, len(values)+1),
        "forecast_market_index_price_gbp_per_mwh": values,
    })


def test_scenario_builder_is_reproducible_and_mutually_exclusive():
    a = build_stochastic_market_scenarios(_base_prices(), scenario_count=5, seed=7)
    b = build_stochastic_market_scenarios(_base_prices(), scenario_count=5, seed=7)
    pd.testing.assert_frame_equal(a, b)
    assert np.all((a["bm_up_accepted"] + a["bm_down_accepted"]) <= 1)
    assert a.groupby("scenario_id")["scenario_probability"].first().sum() == pytest.approx(1)


def test_stochastic_optimiser_respects_power_and_reports_distribution():
    scenarios = build_stochastic_market_scenarios(
        _base_prices(), scenario_count=5, wholesale_sigma_gbp_per_mwh=0,
        bm_up_probability=0, bm_down_probability=0,
    )
    battery = BatteryConfig(power_mw=10, duration_hours=2, initial_soc_fraction=.5)
    schedule, summary = optimise_stochastic_wholesale_bm(
        scenarios, battery,
        StochasticBiddingConfig(throughput_cost_gbp_per_mwh=2, risk_aversion=.1),
    )
    assert ((schedule["wholesale_charge_mw"] + schedule["bm_down_offer_mw"]) <= 10 + 1e-7).all()
    assert ((schedule["wholesale_discharge_mw"] + schedule["bm_up_offer_mw"]) <= 10 + 1e-7).all()
    assert summary["perfect_information"] is False
    assert summary["scenario_count"] == 5
    assert summary["p10_net_value_gbp"] <= summary["p90_net_value_gbp"]
    assert summary["expected_net_value_gbp"] > 0


def test_higher_wear_cost_does_not_improve_expected_value():
    scenarios = build_stochastic_market_scenarios(
        _base_prices(), scenario_count=5, wholesale_sigma_gbp_per_mwh=0,
        bm_up_probability=0, bm_down_probability=0,
    )
    battery = BatteryConfig(power_mw=10, duration_hours=2)
    _, low = optimise_stochastic_wholesale_bm(scenarios, battery, StochasticBiddingConfig(throughput_cost_gbp_per_mwh=0, risk_aversion=0))
    _, high = optimise_stochastic_wholesale_bm(scenarios, battery, StochasticBiddingConfig(throughput_cost_gbp_per_mwh=100, risk_aversion=0))
    assert high["expected_net_value_gbp"] <= low["expected_net_value_gbp"] + 1e-6
