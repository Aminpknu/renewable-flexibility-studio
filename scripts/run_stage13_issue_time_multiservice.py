"""Backtest issue-time multi-service capacity offers and acceptance-calibrated value."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from adapters.forecast_data import load_historical_predictions
from adapters.neso_services import load_eac_service_history
from engine.battery import BatteryConfig
from engine.multiservice_predelivery import (
    attach_opportunity_cost_bids, build_issue_time_multiservice_schedule,
    score_issue_time_multiservice_schedule,
)
from engine.portfolio import build_virtual_portfolio
from engine.pre_delivery_strategy import build_reserve_soc_corridor
from engine.reserve_planning import ReservePlanningConfig, build_reserve_plan
from engine.uncertainty import PredictionIntervalConfig, build_forecast_only_directional_interval

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "multiservice"
BATTERY = BatteryConfig(25.0, 8.0, 0.90, 0.50)
THROUGHPUT_COST = 2.0


def _annualise(value: float, days: int) -> float:
    return float(value * 365.25 / days)


def main() -> None:
    history = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")
    portfolio = build_virtual_portfolio(history, "mixed", 100.0, 0.5)
    wholesale = pd.read_csv(ROOT / "outputs" / "market_optimisation" / "price_forecast_backtest.csv")
    wholesale["settlement_date"] = pd.to_datetime(wholesale["settlement_date"]).dt.normalize()
    wholesale["valid_time_utc"] = pd.to_datetime(wholesale["valid_time_utc"], utc=True)
    service_forecast = pd.read_csv(OUT / "stage13_price_forecast_backtest.csv")
    service_forecast["service_date"] = pd.to_datetime(service_forecast["service_date"]).dt.normalize()
    realised_services = load_eac_service_history(ROOT / "data" / "neso_multiservice_prices.csv")
    april_calibration = pd.read_csv(ROOT / "data" / "neso_multiservice_acceptance_calibration_april.csv")
    june_calibration = pd.read_csv(ROOT / "data" / "neso_multiservice_acceptance_calibration.csv")
    stage11_daily = pd.read_csv(OUT / "multiservice_daily.csv")
    stage11_daily["settlement_date"] = pd.to_datetime(stage11_daily["settlement_date"]).dt.normalize()
    pre_delivery_daily = pd.read_csv(ROOT / "outputs" / "market_optimisation" / "pre_delivery_strategy_daily.csv")
    pre_delivery_daily["settlement_date"] = pd.to_datetime(pre_delivery_daily["settlement_date"]).dt.normalize()
    interval_cfg = PredictionIntervalConfig(
        nominal_coverage=0.80, lookback_days=180, minimum_history_days=30, neighbour_count=600
    )
    candidate_dates = pd.date_range("2026-05-01", "2026-06-30", freq="D")
    portfolio_dates = set(pd.to_datetime(portfolio["settlement_date"]).dt.normalize())
    wholesale_dates = set(pd.to_datetime(wholesale["settlement_date"]).dt.normalize())
    service_dates = set(pd.to_datetime(service_forecast["service_date"]).dt.normalize())
    dates = pd.DatetimeIndex([
        value for value in candidate_dates
        if value in portfolio_dates and value in wholesale_dates and value in service_dates
    ])
    checkpoint_daily = OUT / "stage13_issue_time_checkpoint_daily.csv"
    checkpoint_offers = OUT / "stage13_issue_time_checkpoint_offers.csv"
    rows: list[dict[str, object]] = []
    bid_rows: list[pd.DataFrame] = []
    completed_dates: set[pd.Timestamp] = set()
    if checkpoint_daily.exists():
        prior_daily = pd.read_csv(checkpoint_daily)
        prior_daily["settlement_date"] = pd.to_datetime(prior_daily["settlement_date"]).dt.normalize()
        counts = prior_daily.groupby("settlement_date")["scenario"].nunique()
        completed_dates = set(counts.loc[counts.ge(2)].index)
        rows = prior_daily.to_dict("records")
    if checkpoint_offers.exists():
        bid_rows = [pd.read_csv(checkpoint_offers)]
    for index, target in enumerate(dates, start=1):
        if target in completed_dates:
            continue
        day_portfolio = portfolio.loc[portfolio["settlement_date"].eq(target)].copy()
        interval, uncertainty = build_forecast_only_directional_interval(
            portfolio, day_portfolio, target, interval_cfg
        )
        if not uncertainty.get("available"):
            raise RuntimeError(f"Directional uncertainty unavailable for {target.date()}.")
        reserve_series, _reserve = build_reserve_plan(
            interval, BATTERY, ReservePlanningConfig(current_soc_fraction=0.50)
        )
        corridor, corridor_meta = build_reserve_soc_corridor(reserve_series, BATTERY)
        if not corridor_meta["all_periods_feasible"]:
            raise RuntimeError(f"Stage 13 reserve corridor infeasible for {target.date()}.")
        day_wholesale = wholesale.loc[wholesale["settlement_date"].eq(target)].copy().sort_values("settlement_period")
        signal = day_wholesale[[
            "settlement_period", "valid_time_utc", "forecast_market_index_price_gbp_per_mwh"
        ]].rename(columns={"forecast_market_index_price_gbp_per_mwh": "market_index_price_gbp_per_mwh"})
        signal = signal.merge(
            corridor[["settlement_period", "soc_floor_mwh", "soc_ceiling_mwh"]],
            on="settlement_period", how="left", validate="one_to_one",
        )
        realised_market = day_wholesale[["settlement_period", "market_index_price_gbp_per_mwh"]].copy()
        day_service = service_forecast.loc[service_forecast["service_date"].eq(target)].copy()
        calibration = april_calibration if target.month == 5 else june_calibration
        for scenario, bm_eligible in (("non_bm", False), ("bm_eligible", True)):
            schedule, contracts, allocation = build_issue_time_multiservice_schedule(
                signal, day_service, BATTERY, calibration,
                throughput_cost_gbp_per_mwh=THROUGHPUT_COST,
                assume_bm_eligible=bm_eligible,
            )
            bids, bid_meta = attach_opportunity_cost_bids(
                contracts, signal, BATTERY, calibration, THROUGHPUT_COST
            )
            scored, realised = score_issue_time_multiservice_schedule(
                schedule, bids, realised_market, realised_services, THROUGHPUT_COST
            )
            if not scored.empty:
                scored["settlement_date"] = target.date().isoformat()
                scored["scenario"] = scenario
                bid_rows.append(scored)
            stage11_scenario = "bm_multiservice" if bm_eligible else "non_bm_multiservice"
            stage11_row = stage11_daily.loc[
                stage11_daily["settlement_date"].eq(target)
                & stage11_daily["scenario"].eq(stage11_scenario)
            ]
            stage11_value = float(stage11_row["net_value_gbp"].iloc[0]) if not stage11_row.empty else float("nan")
            reserve_row = pre_delivery_daily.loc[pre_delivery_daily["settlement_date"].eq(target)]
            reserve_wholesale = float(reserve_row["reserve_aware_forecast_margin_gbp"].iloc[0])
            offered_mwh = float((bids["contracted_mw"] * bids["window_hours"]).sum()) if not bids.empty else 0.0
            accepted_mwh = float(
                (scored["acceptance_calibrated_expected_accepted_mw"] * scored["window_hours"]).sum()
            ) if not scored.empty else 0.0
            rows.append({
                "settlement_date": target.date().isoformat(), "scenario": scenario,
                "forecast_selection_objective_gbp": float(allocation["net_stacked_value_gbp"]),
                "realised_wholesale_margin_gbp": realised["realised_wholesale_margin_gbp"],
                "acceptance_calibrated_ancillary_gbp": realised["acceptance_calibrated_ancillary_availability_gbp"],
                "acceptance_calibrated_total_gbp": realised["total_acceptance_calibrated_value_gbp"],
                "stage11_perfect_information_total_gbp": stage11_value,
                "reserve_aware_wholesale_only_gbp": reserve_wholesale,
                "offered_mw_hours": offered_mwh,
                "acceptance_calibrated_expected_accepted_mw_hours": accepted_mwh,
                "price_eligible_offer_pct": float(100.0 * scored["price_eligible_after_auction"].mean()) if not scored.empty else 0.0,
                "mean_predicted_acceptance_pct": float(100.0 * bids["predicted_acceptance_ratio_at_bid_time"].mean()) if not bids.empty else 0.0,
                "contract_rows": int(len(bids)),
                "mean_reserve_corridor_width_mwh": float(corridor_meta["mean_corridor_width_mwh"]),
                "baseline_forecast_wholesale_value_gbp": float(bid_meta["baseline_forecast_wholesale_value_gbp"]),
            })
        pd.DataFrame(rows).to_csv(checkpoint_daily, index=False)
        if bid_rows:
            pd.concat(bid_rows, ignore_index=True).to_csv(checkpoint_offers, index=False)
        if index % 10 == 0 or index == len(dates):
            print(f"completed {index}/{len(dates)} dates", flush=True)
    daily = pd.DataFrame(rows)
    offers = pd.concat(bid_rows, ignore_index=True) if bid_rows else pd.DataFrame()
    daily.to_csv(OUT / "stage13_issue_time_multiservice_daily.csv", index=False)
    offers.to_csv(OUT / "stage13_issue_time_multiservice_offers.csv", index=False)
    scenario_summary: dict[str, object] = {}
    for scenario, group in daily.groupby("scenario"):
        days = int(len(group))
        total = float(group["acceptance_calibrated_total_gbp"].sum())
        ancillary = float(group["acceptance_calibrated_ancillary_gbp"].sum())
        wholesale_value = float(group["realised_wholesale_margin_gbp"].sum())
        stage11 = float(group["stage11_perfect_information_total_gbp"].sum())
        reserve_only = float(group["reserve_aware_wholesale_only_gbp"].sum())
        selected_offers = offers.loc[offers["scenario"].eq(scenario)] if not offers.empty else pd.DataFrame()
        by_product = {}
        if not selected_offers.empty:
            for product, product_rows in selected_offers.groupby("product"):
                by_product[str(product)] = {
                    "offered_mw_hours": float((product_rows["contracted_mw"] * product_rows["window_hours"]).sum()),
                    "expected_accepted_mw_hours": float((product_rows["acceptance_calibrated_expected_accepted_mw"] * product_rows["window_hours"]).sum()),
                    "acceptance_calibrated_payment_gbp": float(product_rows["acceptance_calibrated_availability_payment_gbp"].sum()),
                    "mean_bid_gbp_per_mw_per_hour": float(product_rows["opportunity_cost_bid_gbp_per_mw_per_hour"].replace([float("inf")], pd.NA).dropna().mean()),
                }
        scenario_summary[str(scenario)] = {
            "days": days,
            "annualised_acceptance_calibrated_total_gbp": _annualise(total, days),
            "annualised_realised_wholesale_margin_gbp": _annualise(wholesale_value, days),
            "annualised_acceptance_calibrated_ancillary_gbp": _annualise(ancillary, days),
            "annualised_reserve_aware_wholesale_only_gbp": _annualise(reserve_only, days),
            "annualised_stage11_perfect_information_gbp": _annualise(stage11, days),
            "capture_vs_stage11_perfect_information_pct": 100.0 * total / stage11 if stage11 else 0.0,
            "incremental_value_vs_reserve_aware_wholesale_gbp_per_year": _annualise(total - reserve_only, days),
            "positive_total_value_days_pct": 100.0 * float(group["acceptance_calibrated_total_gbp"].gt(0).mean()),
            "mean_price_eligible_offer_pct": float(group["price_eligible_offer_pct"].mean()),
            "mean_predicted_acceptance_pct": float(group["mean_predicted_acceptance_pct"].mean()),
            "offered_mw_hours": float(group["offered_mw_hours"].sum()),
            "expected_accepted_mw_hours": float(group["acceptance_calibrated_expected_accepted_mw_hours"].sum()),
            "by_product": by_product,
        }
    payload = {
        "schema_version": "1.0",
        "stage": "13_issue_time_multiservice_acceptance_calibrated",
        "validation_start": "2026-05-01",
        "validation_end": "2026-06-30",
        "calendar_days": 61,
        "eligible_days": int(len(dates)),
        "excluded_calendar_dates": [
            value.date().isoformat() for value in candidate_dates if value not in set(dates)
        ],
        "battery": {"power_mw": 25.0, "energy_mwh": 200.0, "duration_hours": 8.0},
        "throughput_cost_gbp_per_mwh": THROUGHPUT_COST,
        "scenarios": scenario_summary,
        "decision_information": [
            "prior-date wholesale price forecast",
            "prior-date product-specific EAC clearing-price forecast",
            "Stage B prior-data directional uncertainty and SOC corridor",
            "acceptance calibration from earlier standalone-parent EAC orders",
            "opportunity-cost bid floor computed from forecast wholesale value",
        ],
        "realised_information_used_only_for_scoring": [
            "APX Market Index price",
            "EAC system clearing price and system cleared volume",
        ],
        "acceptance_scoring": (
            "expected accepted MW = offered MW capped by system cleared volume times issue-time predicted acceptance ratio; "
            "bids above realised clearing price receive zero"
        ),
        "limitations": [
            "counterfactual asset acceptance cannot be observed exactly",
            "acceptance is calibrated from comparable simple historical parent orders, not participant identity",
            "wholesale schedule is not re-optimised after a rejected ancillary offer",
            "utilisation energy/payments and performance penalties remain excluded",
            "APX Market Index is a public short-term wholesale reference, not a licensed day-ahead auction price",
            "capacity selection uses product-level prior acceptance before bid-specific acceptance is calculated",
            "opportunity-cost bid is a standalone-contract value-loss approximation and does not allocate joint-stack interaction value",
        ],
    }
    (OUT / "stage13_issue_time_multiservice_summary.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    checkpoint_daily.unlink(missing_ok=True)
    checkpoint_offers.unlink(missing_ok=True)
    print(json.dumps(payload, indent=2), flush=True)


if __name__ == "__main__":
    main()
