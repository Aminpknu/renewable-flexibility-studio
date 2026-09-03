"""Backtest forecast-driven wholesale scheduling against perfect-information upper bounds."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from adapters.forecast_data import load_historical_predictions
from adapters.market_reference import load_market_index_history
from engine.battery import BatteryConfig
from engine.market_optimisation import (
    WholesaleArbitrageConfig,
    evaluate_arbitrage_schedule,
    optimise_wholesale_arbitrage,
)
from engine.portfolio import build_virtual_portfolio
from engine.pre_delivery_strategy import build_reserve_soc_corridor
from engine.price_forecast import MarketPriceForecastConfig, backtest_market_price_forecast
from engine.reserve_planning import ReservePlanningConfig, build_reserve_plan
from engine.uncertainty import PredictionIntervalConfig, build_forecast_only_directional_interval

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "market_optimisation"
THROUGHPUT_COST = 2.0
BATTERY = BatteryConfig(power_mw=25.0, duration_hours=8.0, round_trip_efficiency=0.90, initial_soc_fraction=0.50)


def _realised_margin(signal: pd.DataFrame, realised: pd.DataFrame) -> float:
    schedule, _ = optimise_wholesale_arbitrage(
        signal, BATTERY, WholesaleArbitrageConfig(THROUGHPUT_COST)
    )
    return float(evaluate_arbitrage_schedule(
        schedule, realised, THROUGHPUT_COST
    )["realised_net_arbitrage_margin_gbp"])


def _annualise(value: float, days: int) -> float:
    return float(value * 365.25 / days)


def main() -> None:
    market = load_market_index_history(ROOT / "data" / "elexon_market_index_prices.csv")
    price_bt, price_summary = backtest_market_price_forecast(
        market, MarketPriceForecastConfig(minimum_history_days=30, ridge_alpha=20.0)
    )
    history = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")
    portfolio = build_virtual_portfolio(history, "mixed", 100.0, wind_share=0.5)
    segment = history[["settlement_date", "evaluation_segment"]].drop_duplicates()
    segment["settlement_date"] = pd.to_datetime(segment["settlement_date"]).dt.normalize()
    rows: list[dict[str, object]] = []
    interval_cfg = PredictionIntervalConfig(
        nominal_coverage=0.80, lookback_days=180, minimum_history_days=30, neighbour_count=600
    )
    dates = pd.Index(pd.to_datetime(price_bt["settlement_date"]).dt.normalize().unique()).sort_values()
    for index, target in enumerate(dates, start=1):
        day_prices = price_bt.loc[
            pd.to_datetime(price_bt["settlement_date"]).dt.normalize().eq(target)
        ].copy().sort_values("settlement_period")
        realised = day_prices[["settlement_period", "market_index_price_gbp_per_mwh"]].copy()
        perfect_signal = realised.copy()
        forecast_signal = day_prices[["settlement_period", "forecast_market_index_price_gbp_per_mwh"]].rename(
            columns={"forecast_market_index_price_gbp_per_mwh": "market_index_price_gbp_per_mwh"}
        )
        naive_signal = day_prices[["settlement_period", "naive_market_index_price_gbp_per_mwh"]].rename(
            columns={"naive_market_index_price_gbp_per_mwh": "market_index_price_gbp_per_mwh"}
        )
        perfect_margin = _realised_margin(perfect_signal, realised)
        forecast_margin = _realised_margin(forecast_signal, realised)
        naive_margin = _realised_margin(naive_signal, realised)
        day_portfolio = portfolio.loc[
            pd.to_datetime(portfolio["settlement_date"]).dt.normalize().eq(target)
        ].copy()
        interval, uncertainty = build_forecast_only_directional_interval(
            portfolio, day_portfolio, target, interval_cfg
        )
        reserve_margin = float("nan")
        corridor_meta = {"all_periods_feasible": False, "mean_corridor_width_mwh": float("nan")}
        if uncertainty.get("available"):
            reserve_series, _reserve = build_reserve_plan(
                interval, BATTERY, ReservePlanningConfig(current_soc_fraction=0.50)
            )
            corridor, corridor_meta = build_reserve_soc_corridor(reserve_series, BATTERY)
            if corridor_meta["all_periods_feasible"]:
                reserve_signal = forecast_signal.merge(
                    corridor[["settlement_period", "soc_floor_mwh", "soc_ceiling_mwh"]],
                    on="settlement_period", how="left", validate="one_to_one",
                )
                reserve_margin = _realised_margin(reserve_signal, realised)
        seg = segment.loc[segment["settlement_date"].eq(target), "evaluation_segment"].iloc[0]
        rows.append({
            "settlement_date": target.date().isoformat(),
            "evaluation_segment": seg,
            "perfect_foresight_margin_gbp": perfect_margin,
            "forecast_strategy_margin_gbp": forecast_margin,
            "naive_strategy_margin_gbp": naive_margin,
            "reserve_aware_forecast_margin_gbp": reserve_margin,
            "reserve_corridor_feasible": bool(corridor_meta["all_periods_feasible"]),
            "mean_reserve_corridor_width_mwh": corridor_meta["mean_corridor_width_mwh"],
        })
        if index % 50 == 0:
            print(f"completed {index}/{len(dates)}", flush=True)
    daily = pd.DataFrame(rows)
    days = int(len(daily))
    perfect_total = float(daily["perfect_foresight_margin_gbp"].sum())
    forecast_total = float(daily["forecast_strategy_margin_gbp"].sum())
    naive_total = float(daily["naive_strategy_margin_gbp"].sum())
    reserve_total = float(daily["reserve_aware_forecast_margin_gbp"].sum())
    summary = {
        "schema_version": "1.0",
        "stage": "9_market_optimisation_packet2_pre_delivery",
        "price_forecast": price_summary,
        "eligible_days": days,
        "battery": {"power_mw": 25.0, "energy_mwh": 200.0, "duration_hours": 8.0},
        "throughput_cost_gbp_per_mwh": THROUGHPUT_COST,
        "perfect_foresight_annualised_margin_gbp": _annualise(perfect_total, days),
        "forecast_strategy_annualised_margin_gbp": _annualise(forecast_total, days),
        "naive_strategy_annualised_margin_gbp": _annualise(naive_total, days),
        "reserve_aware_forecast_annualised_margin_gbp": _annualise(reserve_total, days),
        "forecast_capture_rate_pct": 100.0 * forecast_total / perfect_total,
        "naive_capture_rate_pct": 100.0 * naive_total / perfect_total,
        "reserve_aware_capture_rate_pct": 100.0 * reserve_total / perfect_total,
        "forecast_positive_margin_days_pct": 100.0 * float(daily["forecast_strategy_margin_gbp"].gt(0).mean()),
        "reserve_aware_positive_margin_days_pct": 100.0 * float(daily["reserve_aware_forecast_margin_gbp"].gt(0).mean()),
        "reserve_corridor_feasible_days_pct": 100.0 * float(daily["reserve_corridor_feasible"].mean()),
        "mean_reserve_opportunity_cost_gbp_per_day": float(
            (daily["forecast_strategy_margin_gbp"] - daily["reserve_aware_forecast_margin_gbp"]).mean()
        ),
    }
    locked = daily.loc[daily["evaluation_segment"].eq("locked_test")].copy()
    if not locked.empty:
        locked_perfect = float(locked["perfect_foresight_margin_gbp"].sum())
        locked_forecast = float(locked["forecast_strategy_margin_gbp"].sum())
        locked_reserve = float(locked["reserve_aware_forecast_margin_gbp"].sum())
        summary["locked_test"] = {
            "days": int(len(locked)),
            "forecast_capture_rate_pct": 100.0 * locked_forecast / locked_perfect,
            "reserve_aware_capture_rate_pct": 100.0 * locked_reserve / locked_perfect,
            "forecast_positive_margin_days_pct": 100.0 * float(locked["forecast_strategy_margin_gbp"].gt(0).mean()),
            "reserve_aware_positive_margin_days_pct": 100.0 * float(locked["reserve_aware_forecast_margin_gbp"].gt(0).mean()),
        }
    summary["limitations"] = [
        "Market Index Price is a short-term wholesale reference, not a day-ahead auction price",
        "forecast strategy is issue-time-correct with respect to the Market Index archive but assumes scheduled trades can be evaluated at realised MIP",
        "reserve-aware arbitrage preserves an uncertainty-derived SOC corridor but does not yet simulate real-time firming execution on top of the wholesale schedule",
        "no transaction fees, bid-ask spread, site grid limit or ancillary-service commitment is included",
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    price_bt.to_csv(OUT / "price_forecast_backtest.csv", index=False)
    daily.to_csv(OUT / "pre_delivery_strategy_daily.csv", index=False)
    (OUT / "pre_delivery_strategy_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
