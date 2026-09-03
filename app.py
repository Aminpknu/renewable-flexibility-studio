"""Standalone interactive Renewable Flexibility Studio."""

from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html, no_update
from plotly.subplots import make_subplots

from adapters.design_grid import load_design_grid, scaled_design_grid
from adapters.forecast_data import available_dates, load_historical_predictions, select_date
from adapters.grid_context import fetch_day_ahead_demand
from adapters.imbalance_settlement import load_system_price_history, select_system_prices
from adapters.latest_forecast import latest_target_date, load_latest_forecast
from adapters.market_reference import load_market_index_history, select_market_index_prices
from adapters.quick_reserve import load_quick_reserve_history
from adapters.spatial_forecast import build_spatial_virtual_forecast, load_latest_spatial_forecast
from adapters.market_forecast_bundle import assess_market_forecast_bundle, validate_market_forecast_bundle
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.design_sizing import select_stable_design
from engine.frontier import build_risk_value_frontier
from engine.sensitivity import build_capex_consequence_sensitivity
from engine.value import (
    ValueAssumptions,
    break_even_consequence_value_gbp_per_mwh,
    maximum_capex_for_zero_npv_gbp,
)
from engine.imbalance import apply_imbalance_settlement, summarise_imbalance_settlement
from engine.metrics import calculate_firming_metrics
from engine.market_investment import (
    MarketInvestmentAssumptions, appraise_market_operating_value,
    maximum_capex_for_market_zero_npv_gbp, minimum_annual_market_value_for_zero_npv_gbp,
)
from engine.market_investment_monte_carlo import (
    MarketInvestmentDistributions, MarketInvestmentMonteCarloConfig,
    run_market_investment_monte_carlo,
)
from engine.market_optimisation import (
    SettlementOptimisationConfig, WholesaleArbitrageConfig,
    optimise_firming_and_arbitrage, optimise_settlement_aware_firming,
    optimise_wholesale_arbitrage,
)
from engine.monte_carlo import (
    MonteCarloConfig, MonteCarloDistributions, TriangularMultiplier,
    build_daily_value_evidence, run_value_monte_carlo,
)
from engine.portfolio import build_virtual_forecast, build_virtual_portfolio
from engine.pre_delivery_strategy import build_reserve_soc_corridor
from engine.reserve_planning import ReservePlanningConfig, build_reserve_plan
from engine.quick_reserve import (
    QuickReserveStackingConfig, optimise_arbitrage_and_quick_reserve,
    optimise_firming_arbitrage_and_quick_reserve,
)
from engine.sizing import find_minimum_battery
from engine.stress import run_value_stress_scenarios
from engine.uncertainty import (
    PredictionIntervalConfig,
    build_forecast_only_directional_interval,
    build_forecast_only_prediction_interval,
    build_rolling_prediction_interval,
)

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "historical_backtest.csv"
FULL_BACKTEST_PATH = ROOT / "outputs" / "full_backtest_summary.json"
EXTENDED_SIZING_PATH = ROOT / "outputs" / "extended_sizing.csv"
IMBALANCE_SUMMARY_PATH = ROOT / "outputs" / "imbalance_backtest_summary.json"
DESIGN_GRID_PATH = ROOT / "outputs" / "design_sizing_grid_100mw.csv"
LATEST_FORECAST_PATH = ROOT / "data" / "latest_forecast.csv"
LATEST_SPATIAL_FORECAST_PATH = ROOT / "data" / "latest_spatial_forecast.csv"
SYSTEM_PRICES_PATH = ROOT / "data" / "elexon_system_prices.csv"
MARKET_INDEX_PATH = ROOT / "data" / "elexon_market_index_prices.csv"
MARKET_BACKTEST_PATH = ROOT / "outputs" / "market_optimisation" / "default_mixed_summary.json"
QUICK_RESERVE_PATH = ROOT / "data" / "neso_quick_reserve_prices.csv"
QUICK_RESERVE_SUMMARY_PATH = ROOT / "outputs" / "quick_reserve" / "quick_reserve_summary.json"
QUICK_RESERVE_PREDELIVERY_SUMMARY_PATH = ROOT / "outputs" / "quick_reserve" / "quick_reserve_predelivery_summary.json"
QUICK_RESERVE_PREDELIVERY_DAILY_PATH = ROOT / "outputs" / "quick_reserve" / "quick_reserve_predelivery_daily.csv"
QUICK_RESERVE_PRICE_FORECAST_PATH = ROOT / "outputs" / "quick_reserve" / "quick_reserve_price_forecast_backtest.csv"
QUICK_RESERVE_PREDELIVERY_ALLOCATIONS_PATH = ROOT / "outputs" / "quick_reserve" / "quick_reserve_predelivery_allocations.csv"
QUICK_RESERVE_ACCEPTANCE_DIAGNOSTIC_PATH = ROOT / "outputs" / "quick_reserve" / "quick_reserve_acceptance_diagnostic.json"
PRICE_FORECAST_BACKTEST_PATH = ROOT / "outputs" / "market_optimisation" / "price_forecast_backtest.csv"
PREDELIVERY_DAILY_PATH = ROOT / "outputs" / "market_optimisation" / "pre_delivery_strategy_daily.csv"
PREDELIVERY_SUMMARY_PATH = ROOT / "outputs" / "market_optimisation" / "pre_delivery_strategy_summary.json"
LATEST_MARKET_FORECAST_PATH = ROOT / "data" / "latest_market_price_forecast.csv"
LATEST_MARKET_FORECAST_MANIFEST_PATH = ROOT / "data" / "latest_market_price_forecast_manifest.json"
MARKET_PIPELINE_STATUS_PATH = ROOT / "data" / "market_forecast_pipeline_status.json"
MARKET_INVESTMENT_SUMMARY_PATH = ROOT / "outputs" / "market_investment" / "market_investment_summary.json"
MARKET_INVESTMENT_MC_PATH = ROOT / "outputs" / "market_investment" / "market_investment_monte_carlo_5000.csv"
HISTORICAL_DATA = load_historical_predictions(DATA_PATH)
SYSTEM_PRICES = load_system_price_history(SYSTEM_PRICES_PATH)
MARKET_INDEX_PRICES = load_market_index_history(MARKET_INDEX_PATH)
QUICK_RESERVE = load_quick_reserve_history(str(QUICK_RESERVE_PATH))
LATEST_FORECAST = load_latest_forecast(LATEST_FORECAST_PATH)
LATEST_SPATIAL_FORECAST = load_latest_spatial_forecast(LATEST_SPATIAL_FORECAST_PATH)
LATEST_TARGET_DATE = latest_target_date(LATEST_FORECAST)
FULL_BACKTEST = json.loads(FULL_BACKTEST_PATH.read_text(encoding="utf-8"))
IMBALANCE_BACKTEST = json.loads(IMBALANCE_SUMMARY_PATH.read_text(encoding="utf-8"))
MARKET_BACKTEST = json.loads(MARKET_BACKTEST_PATH.read_text(encoding="utf-8"))
QUICK_RESERVE_SUMMARY = json.loads(QUICK_RESERVE_SUMMARY_PATH.read_text(encoding="utf-8"))
QUICK_RESERVE_PREDELIVERY_SUMMARY = json.loads(QUICK_RESERVE_PREDELIVERY_SUMMARY_PATH.read_text(encoding="utf-8"))
QUICK_RESERVE_PREDELIVERY_DAILY = pd.read_csv(QUICK_RESERVE_PREDELIVERY_DAILY_PATH)
QUICK_RESERVE_PRICE_FORECAST = pd.read_csv(QUICK_RESERVE_PRICE_FORECAST_PATH)
QUICK_RESERVE_PREDELIVERY_ALLOCATIONS = pd.read_csv(QUICK_RESERVE_PREDELIVERY_ALLOCATIONS_PATH)
QUICK_RESERVE_ACCEPTANCE_DIAGNOSTIC = json.loads(QUICK_RESERVE_ACCEPTANCE_DIAGNOSTIC_PATH.read_text(encoding="utf-8"))
PRICE_FORECAST_BACKTEST = pd.read_csv(PRICE_FORECAST_BACKTEST_PATH)
PREDELIVERY_DAILY = pd.read_csv(PREDELIVERY_DAILY_PATH)
PREDELIVERY_SUMMARY = json.loads(PREDELIVERY_SUMMARY_PATH.read_text(encoding="utf-8"))
MARKET_INVESTMENT_SUMMARY = json.loads(MARKET_INVESTMENT_SUMMARY_PATH.read_text(encoding="utf-8"))
LATEST_MARKET_FORECAST, LATEST_MARKET_FORECAST_MANIFEST = validate_market_forecast_bundle(
    LATEST_MARKET_FORECAST_PATH, LATEST_MARKET_FORECAST_MANIFEST_PATH
)
LATEST_MARKET_FORECAST_HEALTH = assess_market_forecast_bundle(
    LATEST_MARKET_FORECAST_MANIFEST, expected_target_date=LATEST_TARGET_DATE
)
MARKET_PIPELINE_STATUS = (
    json.loads(MARKET_PIPELINE_STATUS_PATH.read_text(encoding="utf-8"))
    if MARKET_PIPELINE_STATUS_PATH.exists() else {"pipeline_status": "MANUAL_BUNDLE"}
)
EXTENDED_SIZING = pd.read_csv(EXTENDED_SIZING_PATH)
DESIGN_GRID = load_design_grid(DESIGN_GRID_PATH)
DATE_OPTIONS = available_dates(HISTORICAL_DATA)
DEFAULT_DATE = DATE_OPTIONS[-1]
SPATIAL_ZONE_OPTIONS = sorted(LATEST_SPATIAL_FORECAST["zone"].dropna().unique().tolist())

app = Dash(__name__, title="Renewable Flexibility Studio")
server = app.server


def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    figure.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=360)
    return figure


def _generation_figure(simulation: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    band_columns = {
        "prediction_interval_lower_mw",
        "prediction_interval_upper_mw",
        "actual_inside_prediction_interval",
    }
    has_band = band_columns.issubset(simulation.columns)
    if has_band:
        figure.add_trace(
            go.Scatter(
                x=simulation["valid_time_utc"],
                y=simulation["prediction_interval_lower_mw"],
                mode="lines",
                line={"width": 0},
                hoverinfo="skip",
                showlegend=False,
                name="Interval lower",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=simulation["valid_time_utc"],
                y=simulation["prediction_interval_upper_mw"],
                mode="lines",
                line={"width": 0},
                fill="tonexty",
                fillcolor="rgba(99,110,250,0.16)",
                name="Nominal 80% expected range",
                hovertemplate="Expected upper %{y:.2f} MW<extra></extra>",
            )
        )
    figure.add_trace(
        go.Scatter(
            x=simulation["valid_time_utc"],
            y=simulation["forecast_mw"],
            mode="lines",
            name="Forecast",
            line={"dash": "dash", "width": 2.4},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=simulation["valid_time_utc"],
            y=simulation["actual_mw"],
            mode="lines",
            name="Actual",
            line={"width": 2.4},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=simulation["valid_time_utc"],
            y=simulation["firmed_delivery_mw"],
            mode="lines",
            name="After battery",
            line={"width": 2.8},
        )
    )
    if has_band:
        outside = ~simulation["actual_inside_prediction_interval"].astype(bool)
        if outside.any():
            figure.add_trace(
                go.Scatter(
                    x=simulation.loc[outside, "valid_time_utc"],
                    y=simulation.loc[outside, "actual_mw"],
                    mode="markers",
                    marker={"symbol": "x", "size": 9},
                    name="Actual outside range",
                )
            )
    figure.update_layout(
        xaxis_title="Settlement time (UTC)",
        yaxis_title="Power (MW)",
        hovermode="x unified",
        margin=dict(l=45, r=20, t=72, b=45),
        legend={"orientation": "h", "y": 1.03, "yanchor": "bottom", "x": 0, "xanchor": "left", "bgcolor": "rgba(255,255,255,0.96)", "bordercolor": "#dbe3e8", "borderwidth": 1, "font": {"size": 11}},
        height=450,
    )
    return figure


def _battery_figure(simulation: pd.DataFrame) -> go.Figure:
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=simulation["valid_time_utc"],
            y=-simulation["charge_mw"],
            name="Charge",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Bar(
            x=simulation["valid_time_utc"],
            y=simulation["discharge_mw"],
            name="Discharge",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=simulation["valid_time_utc"],
            y=simulation["soc_fraction"] * 100,
            mode="lines+markers",
            name="State of charge",
        ),
        secondary_y=True,
    )
    figure.update_yaxes(title_text="Battery power (MW)", secondary_y=False)
    figure.update_yaxes(title_text="State of charge (%)", range=[0, 100], secondary_y=True)
    figure.update_layout(
        xaxis_title="Settlement time (UTC)",
        barmode="relative",
        hovermode="x unified",
        margin=dict(l=45, r=45, t=58, b=45),
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0, "xanchor": "left", "bgcolor": "rgba(255,255,255,0.94)", "bordercolor": "#dbe3e8", "borderwidth": 1, "font": {"size": 12}},
        height=390,
    )
    return figure


def _imbalance_figure(frame: pd.DataFrame) -> go.Figure:
    """Show portfolio imbalance before/after battery against Elexon System Price."""
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=frame["valid_time_utc"], y=frame["imbalance_before_mwh"],
            name="Imbalance before battery",
            hovertemplate="Before %{y:.2f} MWh<extra></extra>",
        ), secondary_y=False,
    )
    figure.add_trace(
        go.Bar(
            x=frame["valid_time_utc"], y=frame["imbalance_after_mwh"],
            name="Residual after battery",
            hovertemplate="After %{y:.2f} MWh<extra></extra>",
        ), secondary_y=False,
    )
    custom = frame[["net_imbalance_volume_mwh", "system_direction"]].to_numpy()
    figure.add_trace(
        go.Scatter(
            x=frame["valid_time_utc"], y=frame["system_price_gbp_per_mwh"],
            mode="lines", name="Elexon System Price", customdata=custom,
            hovertemplate=("System Price £%{y:.2f}/MWh<br>GB NIV %{customdata[0]:.1f} MWh "
                           "(%{customdata[1]})<extra></extra>"),
        ), secondary_y=True,
    )
    figure.add_hline(y=0, line_width=1, line_dash="dot", secondary_y=False)
    figure.update_yaxes(title_text="Portfolio imbalance (MWh)", secondary_y=False)
    figure.update_yaxes(title_text="System Price (£/MWh)", secondary_y=True)
    figure.update_layout(
        barmode="group", hovermode="x unified", height=430,
        margin=dict(l=50, r=55, t=65, b=45),
        legend={"orientation": "h", "y": 1.03, "yanchor": "bottom", "x": 0},
        xaxis_title="Settlement time (UTC)",
    )
    return figure



def _design_heatmap(grid: pd.DataFrame, target_pct: float, reliability_pct: float, selected: dict[str, Any] | None) -> go.Figure:
    target = int(round(float(target_pct)))
    work = grid.copy()
    work["worst_overall_pct"] = work[["development_overall_absorbed_pct", "locked_overall_absorbed_pct"]].min(axis=1)
    work["worst_days_pct"] = work[[f"development_days{target}_pct", f"locked_days{target}_pct"]].min(axis=1)
    work["display_reliability_pct"] = work["worst_days_pct"].where(work["worst_overall_pct"].ge(target))
    pivot = work.pivot(index="power_mw", columns="duration_hours", values="display_reliability_pct")
    overall = work.pivot(index="power_mw", columns="duration_hours", values="worst_overall_pct")
    figure = go.Figure(go.Heatmap(
        x=[f"{value:g} h" for value in pivot.columns], y=pivot.index, z=pivot.to_numpy(),
        customdata=overall.to_numpy(), zmin=0, zmax=100,
        colorbar={"title": "Days meeting target %"},
        hovertemplate="Duration %{x}<br>Power %{y:.1f} MW<br>Worst-period days meeting target %{z:.1f}%<br>Worst-period overall absorption %{customdata:.1f}%<extra></extra>",
    ))
    if selected is not None:
        figure.add_trace(go.Scatter(
            x=[f"{selected['duration_hours']:g} h"], y=[selected["power_mw"]],
            mode="markers", marker={"symbol": "star", "size": 17}, name="Minimum stable design",
            hovertemplate="Selected %{y:.1f} MW / " + f"{selected['energy_mwh']:.0f} MWh<extra></extra>",
        ))
    figure.add_hline(y=0, line_width=0)
    figure.update_layout(
        xaxis_title="Battery duration", yaxis_title="Battery power (MW)", height=465,
        margin=dict(l=55, r=25, t=55, b=50),
        title=f"Two-period stability for {target}% firming target · required reliability {reliability_pct:.0f}%",
    )
    return figure


def _best_standard_design(grid: pd.DataFrame, target_pct: float, reliability_pct: float) -> dict[str, Any]:
    target = int(round(float(target_pct)))
    standard = grid.loc[grid["duration_hours"].le(12)].copy()
    standard["worst_overall_pct"] = standard[["development_overall_absorbed_pct", "locked_overall_absorbed_pct"]].min(axis=1)
    standard["worst_days_pct"] = standard[[f"development_days{target}_pct", f"locked_days{target}_pct"]].min(axis=1)
    feasible = standard.loc[
        standard["worst_overall_pct"].ge(target) & standard["worst_days_pct"].ge(float(reliability_pct))
    ].sort_values(["energy_mwh", "power_mw", "duration_hours"])
    if not feasible.empty:
        result = feasible.iloc[0].to_dict()
        result["standard_gate_met"] = True
        return result
    result = standard.sort_values(["worst_overall_pct", "worst_days_pct", "energy_mwh"], ascending=[False, False, True]).iloc[0].to_dict()
    result["standard_gate_met"] = False
    return result


def _design_cards_and_note(grid: pd.DataFrame, target_pct: float, reliability_pct: float):
    target = int(round(float(target_pct)))
    selected = select_stable_design(grid, target_pct, reliability_pct)
    standard = _best_standard_design(grid, target_pct, reliability_pct)
    if selected is None:
        work = grid.copy()
        work["worst_overall_pct"] = work[["development_overall_absorbed_pct", "locked_overall_absorbed_pct"]].min(axis=1)
        work["worst_days_pct"] = work[[f"development_days{target}_pct", f"locked_days{target}_pct"]].min(axis=1)
        best = work.sort_values(["worst_overall_pct", "worst_days_pct"], ascending=False).iloc[0]
        note = html.Div([
            html.Strong("No tested design meets this stability gate."),
            html.P(f"The strongest tested case reaches {best['worst_overall_pct']:.1f}% overall absorption in the weaker historical period and meets the {target}% daily target on {best['worst_days_pct']:.1f}% of days. Capacity alone is not enough under this operating rule; lower the requirement or change the operating strategy."),
        ])
        return [], note, None
    worst_overall = min(selected["development_overall_absorbed_pct"], selected["locked_overall_absorbed_pct"])
    worst_days = min(selected[f"development_days{target}_pct"], selected[f"locked_days{target}_pct"])
    mean_reset = float(selected["grid_reset_import_mwh"]) / 450.0
    mean_reset_export = float(selected["grid_reset_export_mwh"]) / 450.0
    cards = [
        _kpi_card("Design power", f"{selected['power_mw']:.0f} MW", "Minimum-energy tested stable design"),
        _kpi_card("Design energy", f"{selected['energy_mwh']:.0f} MWh", "Usable sizing benchmark before economics"),
        _kpi_card("Duration", f"{selected['duration_hours']:.0f} h", str(selected["classification"])),
        _kpi_card("Worst-period overall", f"{worst_overall:.1f}%", f"Must be at least {target}% in both historical regimes"),
        _kpi_card("Worst-period reliability", f"{worst_days:.1f}%", f"Share of days meeting the {target}% daily firming target"),
        _kpi_card("Grid energy to restore SOC", f"{mean_reset:.1f} MWh/day import", "Average pre-day grid import used to restore 50% SOC"),
        _kpi_card("Grid energy returned", f"{mean_reset_export:.1f} MWh/day export", "Average pre-day export when the battery ends above 50% SOC"),
    ]
    duration_warning = (
        "This result is in long-duration storage territory, not a conventional short-duration lithium-ion BESS."
        if float(selected["duration_hours"]) > 12 else
        "This result remains within the tested 1–12 h BESS design envelope."
    )
    if standard["standard_gate_met"]:
        standard_text = (
            f"The same stability gate is achievable within the ≤12 h BESS envelope. Its minimum tested design is "
            f"{standard['power_mw']:.0f} MW / {standard['energy_mwh']:.0f} MWh ({standard['duration_hours']:.0f} h)."
        )
    else:
        standard_text = (
            f"No tested ≤12 h BESS meets the same gate. The strongest ≤12 h case is {standard['power_mw']:.0f} MW / "
            f"{standard['energy_mwh']:.0f} MWh ({standard['duration_hours']:.0f} h), with worst-period overall absorption "
            f"{standard['worst_overall_pct']:.1f}% and {standard['worst_days_pct']:.1f}% of days meeting the {target}% daily target."
        )
    note = html.Div([
        html.Strong(f"Minimum tested design stable across both historical regimes: {selected['power_mw']:.0f} MW / {selected['energy_mwh']:.0f} MWh ({selected['duration_hours']:.0f} h)."),
        html.P(f"Apr 2025–Mar 2026: {selected['development_overall_absorbed_pct']:.1f}% overall, {selected[f'development_days{target}_pct']:.1f}% of days meet target. Apr–Jun 2026: {selected['locked_overall_absorbed_pct']:.1f}% overall, {selected[f'locked_days{target}_pct']:.1f}% of days meet target."),
        html.P(duration_warning + " " + standard_text),
        html.P("Sizing mode: grid-connected reserve BESS. SOC is restored to 50% before each day, then the battery reacts only to renewable forecast errors during that day. Grid-restoration energy is tracked, not treated as free."),
    ])
    return cards, note, selected


def _kpi_card(label: str, value: str, help_text: str) -> html.Div:
    return html.Div(
        [html.Div(label, className="kpi-label"), html.Div(value, className="kpi-value"), html.Div(help_text, className="kpi-help")],
        className="kpi-card",
    )


def _kpi_cards(metrics: dict[str, Any]) -> list[html.Div]:
    return [
        _kpi_card("MAE before", f"{metrics['mae_before_mw']:.2f} MW", "Original portfolio forecast error"),
        _kpi_card("MAE after", f"{metrics['mae_after_mw']:.2f} MW", "Residual error after battery response"),
        _kpi_card("Error absorbed", f"{metrics['error_reduction_pct']:.1f}%", "Absolute forecast deviation removed"),
        _kpi_card("Battery energy", f"{metrics['battery_energy_mwh']:.1f} MWh", "Power multiplied by selected duration"),
        _kpi_card("Equivalent cycles", f"{metrics['equivalent_full_cycles']:.2f}", "Throughput relative to usable energy"),
        _kpi_card("Conversion losses", f"{metrics['conversion_losses_mwh']:.2f} MWh", "Charging and discharging losses"),
        _kpi_card("Power-limited", str(metrics["power_limited_periods"]), "Periods where MW response was insufficient"),
        _kpi_card("Energy-limited", str(metrics["energy_limited_periods"]), "Periods where SOC headroom was insufficient"),
    ]


def _long_run_benchmark_content() -> list[html.Div | html.P]:
    cards = []
    for kind, label in (("wind", "Wind"), ("solar", "Solar"), ("mixed", "Mixed 50/50")):
        metrics = FULL_BACKTEST[kind]
        cards.append(_kpi_card(
            label,
            f"{metrics['error_reduction_pct']:.1f}%",
            "Absolute deviation absorbed by 25 MW / 50 MWh over 450 continuous days",
        ))
    recommendations = []
    for kind, label in (("wind", "Wind"), ("solar", "Solar"), ("mixed", "Mixed")):
        rows = EXTENDED_SIZING[(EXTENDED_SIZING["portfolio_type"] == kind) & (EXTENDED_SIZING["initial_soc_case"] == "start_at_minimum_10pct") & EXTENDED_SIZING["meets_target"]]
        if not rows.empty:
            best = rows.sort_values(["energy_mwh", "power_mw", "duration_hours"]).iloc[0]
            recommendations.append(
                f"{label}: {best['power_mw']:.0f} MW / {best['energy_mwh']:.0f} MWh ({best['duration_hours']:.0f} h)"
            )
    exposure_cards = []
    for kind, label in (("wind", "Wind"), ("solar", "Solar"), ("mixed", "Mixed 50/50")):
        risk = IMBALANCE_BACKTEST[kind]
        exposure_cards.append(_kpi_card(
            label,
            f"{risk['gross_exposure_reduction_pct']:.1f}%",
            "Reduction in 450-day gross Elexon System-Price cash-out exposure for the same 25 MW / 50 MWh battery",
        ))
    mixed_risk = IMBALANCE_BACKTEST["mixed"]
    return [
        html.Div(cards, className="kpi-grid"),
        html.P("First tested configurations reaching 80% in the conservative start-at-minimum-SOC no-grid diagnostic: " + "; ".join(recommendations) + ".", className="section-copy"),
        html.Div("450-day grid-settlement exposure", className="chart-title"),
        html.Div(exposure_cards, className="kpi-grid"),
        html.P(
            f"For the default 100 MW mixed portfolio, mean daily gross cash-out exposure falls from £{mixed_risk['mean_daily_gross_exposure_before_gbp']:,.0f} to £{mixed_risk['mean_daily_gross_exposure_after_gbp']:,.0f}; "
            f"the 95th-percentile day falls from £{mixed_risk['p95_daily_gross_exposure_before_gbp']:,.0f} to £{mixed_risk['p95_daily_gross_exposure_after_gbp']:,.0f}, and exposure is lower on {mixed_risk['days_with_lower_gross_exposure']}/450 days. "
            "These are imbalance-risk magnitudes, not battery profit or avoided cost.",
            className="section-copy",
        ),
    ]


def _initial_energy_explanation(power_mw: float, duration_hours: float, initial_soc_pct: float, efficiency_pct: float) -> str:
    energy_mwh = float(power_mw) * float(duration_hours)
    stored_mwh = energy_mwh * float(initial_soc_pct) / 100.0
    minimum_mwh = energy_mwh * 0.10
    usable_above_minimum = max(stored_mwh - minimum_mwh, 0.0)
    discharge_efficiency = (float(efficiency_pct) / 100.0) ** 0.5
    deliverable_mwh = usable_above_minimum * discharge_efficiency
    if usable_above_minimum <= 1e-9:
        return f"Start of selected day: {stored_mwh:.1f} MWh stored at the 10% minimum SOC, so there is no usable prior energy above the reserve."
    return (f"Start of selected day: {stored_mwh:.1f} MWh is assumed already stored. "
            f"That leaves {usable_above_minimum:.1f} MWh above the 10% reserve (about {deliverable_mwh:.1f} MWh deliverable after discharge efficiency). "
            "This energy must come from earlier periods; it is not created on the selected day.")


def _historical_baseline_exposure(
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
) -> tuple[float, float]:
    portfolio = build_virtual_portfolio(
        HISTORICAL_DATA,
        portfolio_type=portfolio_type,
        capacity_mw=float(capacity_mw),
        wind_share=float(wind_share_pct) / 100.0,
    )
    error = portfolio["actual_mw"].astype(float) - portfolio["forecast_mw"].astype(float)
    exposure_mwh = float(error.abs().sum() * 0.5)
    observed_days = float(pd.to_datetime(portfolio["settlement_date"]).dt.normalize().nunique())
    return exposure_mwh, observed_days


def _risk_value_frontier_figure(
    frontier: pd.DataFrame,
    selected_power_mw: float,
    selected_duration_hours: float,
) -> go.Figure:
    figure = go.Figure()
    for status, symbol in (("value-efficient", "circle"), ("dominated", "x")):
        subset = frontier.loc[frontier["frontier_status"].eq(status)]
        if subset.empty:
            continue
        figure.add_trace(go.Scatter(
            x=subset["lifecycle_cost_gbp"] / 1e6,
            y=subset["pv_avoided_loss_gbp"] / 1e6,
            mode="markers",
            name=status.replace("-", " ").title(),
            marker={"symbol": symbol, "size": 9},
            customdata=subset[["power_mw", "duration_hours", "energy_mwh", "npv_gbp", "benefit_cost_ratio"]],
            hovertemplate=(
                "%{customdata[0]:.0f} MW / %{customdata[2]:.0f} MWh (%{customdata[1]:.0f} h)<br>"
                "Lifecycle cost £%{x:.2f}m<br>PV avoided loss £%{y:.2f}m<br>"
                "NPV £%{customdata[3]:,.0f}<br>BCR %{customdata[4]:.2f}<extra></extra>"
            ),
        ))
    selected = frontier.loc[
        frontier["power_mw"].sub(float(selected_power_mw)).abs().lt(1e-9)
        & frontier["duration_hours"].sub(float(selected_duration_hours)).abs().lt(1e-9)
    ]
    if not selected.empty:
        row = selected.iloc[0]
        figure.add_trace(go.Scatter(
            x=[row["lifecycle_cost_gbp"] / 1e6],
            y=[row["pv_avoided_loss_gbp"] / 1e6],
            mode="markers",
            name="Selected Stage A design",
            marker={"symbol": "star", "size": 16},
            hovertemplate=(
                f"Selected {row['power_mw']:.0f} MW / {row['energy_mwh']:.0f} MWh<br>"
                f"NPV £{row['npv_gbp']/1e6:.2f}m<br>BCR {row['benefit_cost_ratio']:.2f}<extra></extra>"
            ),
        ))
    figure.update_layout(
        xaxis_title="Lifecycle cost (£m)",
        yaxis_title="PV avoided expected loss (£m)",
        hovermode="closest",
        margin=dict(l=60, r=20, t=55, b=50),
        legend={"orientation": "h", "y": 1.03, "yanchor": "bottom", "x": 0},
        height=430,
    )
    return figure


def _risk_value_sensitivity_figure(
    annual_avoided_exposure_mwh: float,
    annual_throughput_mwh: float,
    assumptions: ValueAssumptions,
) -> go.Figure:
    consequence = assumptions.consequence_value_gbp_per_mwh
    consequence_values = [0.5 * consequence, 0.75 * consequence, consequence, 1.25 * consequence, 1.5 * consequence]
    table = build_capex_consequence_sensitivity(
        annual_avoided_exposure_mwh, annual_throughput_mwh, assumptions,
        consequence_values_gbp_per_mwh=consequence_values,
        capex_multipliers=[0.75, 1.0, 1.25],
    )
    pivot = table.pivot(index="consequence_value_gbp_per_mwh", columns="capex_multiplier", values="npv_gbp") / 1e6
    figure = go.Figure(go.Heatmap(
        x=[f"{value:.0%} CAPEX" for value in pivot.columns],
        y=[f"£{value:,.0f}/MWh" for value in pivot.index],
        z=pivot.to_numpy(),
        colorbar={"title": "NPV £m"},
        hovertemplate="%{y}<br>%{x}<br>NPV £%{z:.2f}m<extra></extra>",
    ))
    figure.update_layout(
        xaxis_title="Selected-design CAPEX sensitivity",
        yaxis_title="Consequence-value sensitivity",
        margin=dict(l=85, r=20, t=35, b=55), height=380,
    )
    return figure


def _risk_value_analysis(
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
    consequence_value: float,
    reference_capex_million: float,
    fixed_opex_million_per_year: float,
    variable_opex_per_mwh: float,
    asset_life_years: int,
    discount_rate_pct: float,
    degradation_pct: float,
    availability_pct: float,
):
    grid = scaled_design_grid(
        DESIGN_GRID, portfolio_type, float(capacity_mw), float(wind_share_pct)
    )
    selected = select_stable_design(grid, design_target_pct, design_reliability_pct)
    if selected is None:
        raise ValueError("No stable future design exists for the selected design gate.")
    baseline_exposure, observed_days = _historical_baseline_exposure(
        portfolio_type, capacity_mw, wind_share_pct
    )
    reference_capex_gbp = float(reference_capex_million) * 1e6
    fixed_opex_gbp = float(fixed_opex_million_per_year) * 1e6
    frontier = build_risk_value_frontier(
        grid,
        baseline_exposure_total_mwh=baseline_exposure,
        observed_days=observed_days,
        reference_energy_mwh=float(selected["energy_mwh"]),
        reference_capex_gbp=reference_capex_gbp,
        reference_fixed_opex_gbp_per_year=fixed_opex_gbp,
        consequence_value_gbp_per_mwh=float(consequence_value),
        variable_opex_gbp_per_mwh=float(variable_opex_per_mwh),
        asset_life_years=int(asset_life_years),
        discount_rate=float(discount_rate_pct) / 100.0,
        annual_degradation_fraction=float(degradation_pct) / 100.0,
        availability_fraction=float(availability_pct) / 100.0,
    )
    selected_row = frontier.loc[
        frontier["power_mw"].sub(float(selected["power_mw"])).abs().lt(1e-9)
        & frontier["duration_hours"].sub(float(selected["duration_hours"])).abs().lt(1e-9)
    ].iloc[0]
    assumptions = ValueAssumptions(
        consequence_value_gbp_per_mwh=float(consequence_value),
        total_capex_gbp=reference_capex_gbp,
        fixed_opex_gbp_per_year=fixed_opex_gbp,
        variable_opex_gbp_per_mwh=float(variable_opex_per_mwh),
        asset_life_years=int(asset_life_years),
        discount_rate=float(discount_rate_pct) / 100.0,
        annual_degradation_fraction=float(degradation_pct) / 100.0,
    )
    break_even = break_even_consequence_value_gbp_per_mwh(
        float(selected_row["annual_avoided_exposure_mwh"]),
        float(selected_row["annual_throughput_mwh"]),
        assumptions,
    )
    max_capex = maximum_capex_for_zero_npv_gbp(
        float(selected_row["annual_avoided_exposure_mwh"]),
        float(selected_row["annual_throughput_mwh"]),
        assumptions,
    )
    return frontier, selected, selected_row, break_even, max_capex



def _npv_distribution_figure(draws: pd.DataFrame, summary: dict[str, Any]) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(go.Histogram(
        x=draws["npv_gbp"] / 1e6,
        nbinsx=40,
        name="Simulated NPV",
        hovertemplate="NPV £%{x:.2f}m<extra></extra>",
    ))
    for key, label, dash in (
        ("npv_p10_gbp", "P10", "dash"),
        ("npv_p50_gbp", "P50", "solid"),
        ("npv_p90_gbp", "P90", "dash"),
    ):
        figure.add_vline(
            x=float(summary[key]) / 1e6,
            line_dash=dash,
            annotation_text=label,
            annotation_position="top",
        )
    figure.update_layout(
        xaxis_title="NPV (£m)", yaxis_title="Simulation count",
        margin=dict(l=55, r=20, t=55, b=45), height=390,
    )
    return figure


def _stress_scenario_figure(stress: pd.DataFrame) -> go.Figure:
    figure = go.Figure(go.Bar(
        x=stress["scenario"].str.replace("_", " ").str.title(),
        y=stress["npv_gbp"] / 1e6,
        customdata=stress[["benefit_cost_ratio"]],
        hovertemplate="NPV £%{y:.2f}m<br>BCR %{customdata[0]:.2f}<extra></extra>",
    ))
    figure.add_hline(y=0.0, line_dash="dash")
    figure.update_layout(
        yaxis_title="NPV (£m)", xaxis_title="Stress scenario",
        margin=dict(l=55, r=20, t=45, b=85), height=390,
    )
    return figure


def _downside_risk_analysis(
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
    consequence_value: float,
    reference_capex_million: float,
    fixed_opex_million_per_year: float,
    variable_opex_per_mwh: float,
    asset_life_years: int,
    discount_rate_pct: float,
    degradation_pct: float,
    availability_pct: float,
    simulations: int,
    block_days: int,
    seed: int,
):
    grid = scaled_design_grid(
        DESIGN_GRID, portfolio_type, float(capacity_mw), float(wind_share_pct)
    )
    selected = select_stable_design(grid, design_target_pct, design_reliability_pct)
    if selected is None:
        raise ValueError("No stable future design exists for the selected design gate.")
    portfolio = build_virtual_portfolio(
        HISTORICAL_DATA, portfolio_type=portfolio_type, capacity_mw=float(capacity_mw),
        wind_share=float(wind_share_pct) / 100.0,
    )
    battery = BatteryConfig(
        power_mw=float(selected["power_mw"]), duration_hours=float(selected["duration_hours"]),
        round_trip_efficiency=0.90, initial_soc_fraction=0.50,
    )
    daily = build_daily_value_evidence(portfolio, battery)
    assumptions = ValueAssumptions(
        consequence_value_gbp_per_mwh=float(consequence_value),
        total_capex_gbp=float(reference_capex_million) * 1e6,
        fixed_opex_gbp_per_year=float(fixed_opex_million_per_year) * 1e6,
        variable_opex_gbp_per_mwh=float(variable_opex_per_mwh),
        asset_life_years=int(asset_life_years),
        discount_rate=float(discount_rate_pct) / 100.0,
        annual_degradation_fraction=float(degradation_pct) / 100.0,
    )
    availability_mode = float(availability_pct) / 100.0
    availability_distribution = TriangularMultiplier(
        max(0.0, availability_mode - 0.05),
        availability_mode,
        min(1.0, availability_mode + 0.05),
    )
    distributions = MonteCarloDistributions(
        availability_fraction=availability_distribution,
    )
    config = MonteCarloConfig(
        simulations=int(simulations), seed=int(seed), sample_days=365,
        block_days=int(block_days), confidence=0.95,
        firming_target_pct=float(design_target_pct),
        reliability_target_pct=float(design_reliability_pct),
    )
    draws, summary = run_value_monte_carlo(daily, assumptions, config, distributions)
    annualisation = 365.25 / float(len(daily))
    annual_avoided = float(daily["avoided_exposure_mwh"].sum()) * annualisation * availability_mode
    annual_throughput = float(daily["throughput_mwh"].sum()) * annualisation * availability_mode
    stress = run_value_stress_scenarios(annual_avoided, annual_throughput, assumptions)
    distribution_metadata = {
        "consequence_multiplier": [0.70, 1.00, 1.30],
        "capex_multiplier": [0.85, 1.00, 1.20],
        "opex_multiplier": [0.90, 1.00, 1.15],
        "availability_fraction": [
            availability_distribution.low,
            availability_distribution.mode,
            availability_distribution.high,
        ],
        "degradation_multiplier": [0.75, 1.00, 1.25],
        "dependence": "parameter multipliers independent; temporal forecast-error dependence retained through contiguous day blocks; daily outage states independent conditional on sampled availability",
    }
    return draws, summary, stress, selected, distribution_metadata

def _market_vwap(frame: pd.DataFrame) -> float:
    volume = float(frame["market_index_volume_mwh"].sum())
    if volume <= 0:
        raise ValueError("Market Index volume must be positive for a daily VWAP.")
    return float(
        (frame["market_index_price_gbp_per_mwh"] * frame["market_index_volume_mwh"]).sum()
        / volume
    )


def _reactive_market_value(
    portfolio: pd.DataFrame,
    system_prices: pd.DataFrame,
    battery: BatteryConfig,
    restoration_price: float,
    throughput_cost: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    simulation = simulate_reactive_firming(portfolio, battery)
    settlement = apply_imbalance_settlement(simulation, system_prices)
    summary = summarise_imbalance_settlement(settlement)
    ending_soc = float(simulation["soc_end_mwh"].iloc[-1])
    if ending_soc < battery.initial_soc_mwh:
        restore_import = (battery.initial_soc_mwh - ending_soc) / battery.charge_efficiency
        restore_export = 0.0
    else:
        restore_import = 0.0
        restore_export = (ending_soc - battery.initial_soc_mwh) * battery.discharge_efficiency
    restoration_net_cost = (restore_import - restore_export) * restoration_price
    throughput = float(
        (simulation["charge_mw"].sum() + simulation["discharge_mw"].sum())
        * battery.interval_hours
    )
    throughput_cost_gbp = throughput * throughput_cost
    settlement_improvement = (
        float(summary["signed_cashflow_before_gbp"])
        - float(summary["signed_cashflow_after_gbp"])
    )
    before = float(summary["absolute_imbalance_before_mwh"])
    after = float(summary["absolute_imbalance_after_mwh"])
    return settlement, {
        "error_reduction_pct": 100.0 * (1.0 - after / before) if before > 0 else 0.0,
        "settlement_value_improvement_gbp": settlement_improvement,
        "restoration_net_cost_gbp": float(restoration_net_cost),
        "throughput_mwh": throughput,
        "throughput_cost_gbp": throughput_cost_gbp,
        "net_value_improvement_gbp": float(
            settlement_improvement - restoration_net_cost - throughput_cost_gbp
        ),
        "restore_import_mwh": float(restore_import),
        "restore_export_mwh": float(restore_export),
    }


def _market_day_analysis(
    date_value: str,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
    throughput_cost: float,
):
    grid = scaled_design_grid(
        DESIGN_GRID, portfolio_type, float(capacity_mw), float(wind_share_pct)
    )
    selected = select_stable_design(grid, design_target_pct, design_reliability_pct)
    if selected is None:
        raise ValueError("No stable future design exists for the selected design gate.")
    source_day = select_date(HISTORICAL_DATA, date_value)
    portfolio = build_virtual_portfolio(
        source_day, portfolio_type, float(capacity_mw),
        wind_share=float(wind_share_pct) / 100.0,
    )
    system = select_system_prices(SYSTEM_PRICES, date_value)
    market = select_market_index_prices(MARKET_INDEX_PRICES, date_value)
    restoration_price = _market_vwap(market)
    battery = BatteryConfig(
        power_mw=float(selected["power_mw"]),
        duration_hours=float(selected["duration_hours"]),
        round_trip_efficiency=0.90,
        initial_soc_fraction=0.50,
    )
    market_frame, settlement_aware = optimise_settlement_aware_firming(
        portfolio, system, battery,
        SettlementOptimisationConfig(restoration_price, float(throughput_cost)),
    )
    _reactive_frame, reactive = _reactive_market_value(
        portfolio, system, battery, restoration_price, float(throughput_cost)
    )
    arbitrage_frame, arbitrage = optimise_wholesale_arbitrage(
        market, battery, WholesaleArbitrageConfig(float(throughput_cost))
    )
    coopt_frame, coopt = optimise_firming_and_arbitrage(
        portfolio, system, market, battery, float(throughput_cost)
    )
    return {
        "selected": selected,
        "battery": battery,
        "market": market,
        "system": system,
        "market_frame": market_frame,
        "arbitrage_frame": arbitrage_frame,
        "coopt_frame": coopt_frame,
        "restoration_price": restoration_price,
        "settlement_aware": settlement_aware,
        "reactive": reactive,
        "arbitrage": arbitrage,
        "coopt": coopt,
    }


def _market_optimisation_figure(analysis: dict[str, Any]) -> go.Figure:
    market_frame = analysis["market_frame"]
    market = analysis["market"]
    coopt = analysis["coopt_frame"]
    figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
        row_heights=[0.45, 0.55],
    )
    figure.add_trace(go.Scatter(
        x=market_frame["valid_time_utc"],
        y=market_frame["system_price_gbp_per_mwh"],
        mode="lines", name="Elexon System Price",
    ), row=1, col=1)
    figure.add_trace(go.Scatter(
        x=market_frame["valid_time_utc"],
        y=market["market_index_price_gbp_per_mwh"],
        mode="lines", name="APX Market Index Price",
        line={"dash": "dash"},
    ), row=1, col=1)
    figure.add_trace(go.Scatter(
        x=market_frame["valid_time_utc"],
        y=market_frame["forecast_error_mw"],
        mode="lines", name="Original forecast error",
    ), row=2, col=1)
    figure.add_trace(go.Scatter(
        x=market_frame["valid_time_utc"],
        y=market_frame["market_optimised_residual_error_mw"],
        mode="lines", name="Settlement-aware residual",
    ), row=2, col=1)
    figure.add_trace(go.Scatter(
        x=coopt["valid_time_utc"],
        y=coopt["coopt_residual_error_mw"],
        mode="lines", name="Co-optimised residual",
        line={"dash": "dot"},
    ), row=2, col=1)
    figure.add_hline(y=0.0, line_dash="dash", row=2, col=1)
    figure.update_yaxes(title_text="£/MWh", row=1, col=1)
    figure.update_yaxes(title_text="MW", row=2, col=1)
    figure.update_xaxes(title_text="Settlement time (UTC)", row=2, col=1)
    figure.update_layout(
        hovermode="x unified", height=620,
        margin=dict(l=60, r=20, t=55, b=50),
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
    )
    return figure



def _pre_delivery_strategy_view(date_value: str):
    target = pd.Timestamp(date_value).normalize()
    forecast_frame = PRICE_FORECAST_BACKTEST.copy()
    forecast_frame["settlement_date"] = pd.to_datetime(forecast_frame["settlement_date"]).dt.normalize()
    day = forecast_frame.loc[forecast_frame["settlement_date"].eq(target)].copy().sort_values("settlement_period")
    daily = PREDELIVERY_DAILY.copy()
    daily["settlement_date"] = pd.to_datetime(daily["settlement_date"]).dt.normalize()
    daily_row = daily.loc[daily["settlement_date"].eq(target)]
    if day.empty or daily_row.empty:
        message = (
            "Pre-delivery price-strategy evidence starts after 30 prior market days; "
            "choose a date from 1 May 2025 onward."
        )
        return message, [], _empty_figure(message)
    signal = day[["settlement_period", "forecast_market_index_price_gbp_per_mwh"]].rename(
        columns={"forecast_market_index_price_gbp_per_mwh": "market_index_price_gbp_per_mwh"}
    )
    battery = BatteryConfig(
        power_mw=25.0, duration_hours=8.0, round_trip_efficiency=0.90,
        initial_soc_fraction=0.50,
    )
    schedule, _ = optimise_wholesale_arbitrage(
        signal, battery, WholesaleArbitrageConfig(2.0)
    )
    schedule = schedule.merge(
        day[["settlement_period", "valid_time_utc", "market_index_price_gbp_per_mwh", "forecast_market_index_price_gbp_per_mwh"]],
        on="settlement_period", how="left", validate="one_to_one",
        suffixes=("", "_actual"),
    )
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12)
    figure.add_trace(go.Scatter(
        x=schedule["valid_time_utc"], y=schedule["market_index_price_gbp_per_mwh_actual"],
        mode="lines", name="Realised APX MIP",
    ), row=1, col=1)
    figure.add_trace(go.Scatter(
        x=schedule["valid_time_utc"], y=schedule["forecast_market_index_price_gbp_per_mwh"],
        mode="lines", name="Pre-delivery price forecast", line={"dash": "dash"},
    ), row=1, col=1)
    figure.add_trace(go.Bar(
        x=schedule["valid_time_utc"], y=schedule["arbitrage_net_export_mw"],
        name="Forecast-selected battery schedule",
    ), row=2, col=1)
    figure.add_hline(y=0.0, line_dash="dash", row=2, col=1)
    figure.update_yaxes(title_text="£/MWh", row=1, col=1)
    figure.update_yaxes(title_text="Battery MW", row=2, col=1)
    figure.update_xaxes(title_text="Settlement time (UTC)", row=2, col=1)
    figure.update_layout(height=560, hovermode="x unified", margin=dict(l=60, r=20, t=55, b=50))
    row = daily_row.iloc[0]
    perfect = float(row["perfect_foresight_margin_gbp"])
    forecast_margin = float(row["forecast_strategy_margin_gbp"])
    day_capture = 100.0 * forecast_margin / perfect if perfect > 0 else 0.0
    pf = PREDELIVERY_SUMMARY["price_forecast"]
    locked = PREDELIVERY_SUMMARY.get("locked_test", {})
    cards = [
        _kpi_card("Price forecast MAE", f"£{pf['forecast']['mae_gbp_per_mwh']:.1f}/MWh", "420-day expanding backtest"),
        _kpi_card("MAE gain vs naive", f"{pf['mae_improvement_vs_naive_pct']:.1f}%", "Versus previous observed same-period price"),
        _kpi_card("Selected-day realised margin", f"£{forecast_margin:,.0f}", "Schedule chosen from forecast, valued at realised MIP"),
        _kpi_card("Selected-day capture", f"{day_capture:.1f}%", "Share of perfect-foresight arbitrage upper bound"),
        _kpi_card("420-day capture", f"{PREDELIVERY_SUMMARY['forecast_capture_rate_pct']:.1f}%", "Forecast-price strategy / perfect foresight"),
        _kpi_card("Reserve-aware capture", f"{PREDELIVERY_SUMMARY['reserve_aware_capture_rate_pct']:.1f}%", "SOC corridor preserved for renewable uncertainty"),
        _kpi_card("Forecast strategy value", f"£{PREDELIVERY_SUMMARY['forecast_strategy_annualised_margin_gbp']/1e6:.2f}m/yr", "Annualised realised margin"),
        _kpi_card("Locked-period capture", f"{locked.get('forecast_capture_rate_pct', 0):.1f}%", "Apr-Jun 2026 stability period"),
    ]
    note = html.Div([
        html.Div(
            "This schedule is chosen before the target day from a leakage-safe APX Market Index price forecast trained only on earlier settlement dates. Realised MIP is used only afterwards to score what the forecast-selected schedule would have been worth.",
            className="scenario-note-line",
        ),
        html.Div(
            f"Across 420 eligible days the forecast strategy captures {PREDELIVERY_SUMMARY['forecast_capture_rate_pct']:.1f}% of the perfect-information arbitrage upper bound. Preserving the Stage B SOC reserve corridor lowers capture to {PREDELIVERY_SUMMARY['reserve_aware_capture_rate_pct']:.1f}% and costs about £{PREDELIVERY_SUMMARY['mean_reserve_opportunity_cost_gbp_per_day']:.0f}/day of market opportunity on the default benchmark.",
            className="scenario-note-line uncertainty-line",
        ),
        html.Div(
            "This remains a short-term wholesale-reference strategy benchmark, not a licensed day-ahead auction backtest or proof that these trades could have cleared at the realised MIP.",
            className="scenario-note-line uncertainty-warning",
        ),
    ])
    return note, cards, figure




def _forecast_day_market_schedule(
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
    current_soc_pct: float,
    throughput_cost: float,
):
    grid = scaled_design_grid(
        DESIGN_GRID, portfolio_type, float(capacity_mw), float(wind_share_pct)
    )
    selected = select_stable_design(grid, design_target_pct, design_reliability_pct)
    if selected is None:
        raise ValueError("No stable future design exists for the selected gate.")
    target = str(LATEST_MARKET_FORECAST_MANIFEST["target_date"])
    if target != str(LATEST_TARGET_DATE):
        raise ValueError("Latest market-price forecast target does not match the renewable forecast target.")
    reserve_series, _config, planning = _tomorrow_planning_data(
        portfolio_type, capacity_mw, wind_share_pct,
        selected["power_mw"], selected["duration_hours"], current_soc_pct, 90.0,
    )
    reserve = planning.get("reserve")
    if not reserve:
        raise ValueError("Directional reserve evidence is unavailable for the forecast day.")
    recommended_soc = float(reserve["recommended_start_soc_pct"])
    battery = BatteryConfig(
        power_mw=float(selected["power_mw"]),
        duration_hours=float(selected["duration_hours"]),
        round_trip_efficiency=0.90,
        initial_soc_fraction=recommended_soc / 100.0,
    )
    corridor, corridor_meta = build_reserve_soc_corridor(reserve_series, battery)
    if not corridor_meta["all_periods_feasible"]:
        raise ValueError("The forecast-day reserve SOC corridor is infeasible for this design.")
    price = LATEST_MARKET_FORECAST.copy().sort_values("settlement_period")
    price["valid_time_utc"] = pd.to_datetime(price["valid_time_utc"], utc=True)
    signal = price[["settlement_period", "forecast_market_index_price_gbp_per_mwh"]].rename(
        columns={"forecast_market_index_price_gbp_per_mwh": "market_index_price_gbp_per_mwh"}
    )
    unconstrained, unconstrained_summary = optimise_wholesale_arbitrage(
        signal, battery, WholesaleArbitrageConfig(float(throughput_cost))
    )
    reserve_signal = signal.merge(
        corridor[["settlement_period", "soc_floor_mwh", "soc_ceiling_mwh"]],
        on="settlement_period", how="left", validate="one_to_one",
    )
    guarded, guarded_summary = optimise_wholesale_arbitrage(
        reserve_signal, battery, WholesaleArbitrageConfig(float(throughput_cost))
    )
    display = price[["settlement_period", "valid_time_utc", "forecast_market_index_price_gbp_per_mwh"]].merge(
        unconstrained[["settlement_period", "arbitrage_net_export_mw"]],
        on="settlement_period", validate="one_to_one",
    ).merge(
        guarded[["settlement_period", "arbitrage_net_export_mw", "arbitrage_soc_end_mwh"]].rename(
            columns={"arbitrage_net_export_mw": "guarded_net_export_mw"}
        ),
        on="settlement_period", validate="one_to_one",
    ).merge(
        corridor[["settlement_period", "soc_floor_mwh", "soc_ceiling_mwh"]],
        on="settlement_period", validate="one_to_one",
    )
    figure = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.09,
        row_heights=[0.30, 0.32, 0.38],
    )
    figure.add_trace(go.Scatter(
        x=display["valid_time_utc"], y=display["forecast_market_index_price_gbp_per_mwh"],
        mode="lines", name="Forecast APX MIP",
    ), row=1, col=1)
    figure.add_trace(go.Scatter(
        x=display["valid_time_utc"], y=display["arbitrage_net_export_mw"],
        mode="lines", name="Price-only schedule",
    ), row=2, col=1)
    figure.add_trace(go.Scatter(
        x=display["valid_time_utc"], y=display["guarded_net_export_mw"],
        mode="lines", name="Reserve-aware schedule", line={"dash": "dash"},
    ), row=2, col=1)
    figure.add_trace(go.Scatter(
        x=display["valid_time_utc"], y=100.0 * display["arbitrage_soc_end_mwh"] / battery.energy_capacity_mwh,
        mode="lines", name="Reserve-aware SOC",
    ), row=3, col=1)
    figure.add_trace(go.Scatter(
        x=display["valid_time_utc"], y=100.0 * display["soc_floor_mwh"] / battery.energy_capacity_mwh,
        mode="lines", name="Reserve SOC floor", line={"dash": "dot"},
    ), row=3, col=1)
    figure.add_trace(go.Scatter(
        x=display["valid_time_utc"], y=100.0 * display["soc_ceiling_mwh"] / battery.energy_capacity_mwh,
        mode="lines", name="Reserve SOC ceiling", line={"dash": "dot"},
    ), row=3, col=1)
    figure.add_hline(y=0.0, line_dash="dash", row=2, col=1)
    figure.update_yaxes(title_text="£/MWh", row=1, col=1)
    figure.update_yaxes(title_text="Battery MW", row=2, col=1)
    figure.update_yaxes(title_text="SOC (%)", row=3, col=1)
    figure.update_xaxes(title_text="Settlement time (UTC)", row=3, col=1)
    figure.update_layout(
        height=720, hovermode="x unified", margin=dict(l=60, r=20, t=55, b=50),
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
    )
    signal_value = float(unconstrained_summary["net_arbitrage_margin_gbp"])
    guarded_value = float(guarded_summary["net_arbitrage_margin_gbp"])
    price_min = float(price["forecast_market_index_price_gbp_per_mwh"].min())
    price_max = float(price["forecast_market_index_price_gbp_per_mwh"].max())
    cards = [
        _kpi_card("Installed design", f"{selected['power_mw']:.0f} MW / {selected['energy_mwh']:.0f} MWh", "Stage A selected battery"),
        _kpi_card("Recommended start SOC", f"{recommended_soc:.1f}%", "Stage B reserve-readiness result"),
        _kpi_card("Forecast price range", f"£{price_min:.0f}–£{price_max:.0f}/MWh", "APX MIP forecast signal"),
        _kpi_card("Price-only signal value", f"£{signal_value:,.0f}", "Model-implied value, not realised revenue"),
        _kpi_card("Reserve-aware signal value", f"£{guarded_value:,.0f}", "After preserving the SOC reserve corridor"),
        _kpi_card("Reserve opportunity cost", f"£{signal_value-guarded_value:,.0f}", "Forecast-signal value given up for reserve"),
        _kpi_card("Minimum SOC corridor", f"{corridor_meta['minimum_corridor_width_mwh']:.1f} MWh", "Narrowest reserve-safe energy band"),
        _kpi_card("Price history", f"{LATEST_MARKET_FORECAST_MANIFEST['retrieved_history_days']} days", "Prior APX days used in this reconstruction"),
        _kpi_card("Market bundle", LATEST_MARKET_FORECAST_HEALTH["status"], str(MARKET_PIPELINE_STATUS.get("pipeline_status", "MANUAL_BUNDLE"))),
    ]
    status = str(LATEST_MARKET_FORECAST_HEALTH["status"])
    if status == "LIVE":
        timing_text = "The market-price forecast was generated before the target delivery day began and matches the current renewable target."
    elif status == "RECONSTRUCTED":
        timing_text = (
            "This file was regenerated after the target day had already begun, so it is shown as an as-if pre-delivery reconstruction. "
            "The model still excludes every target-day Market Index observation."
        )
    else:
        timing_text = (
            f"Market bundle status is {status}. The site keeps the last validated bundle visible for audit, "
            "but it must not be used as a current operating schedule until a matching fresh target is published."
        )
    pipeline_text = f"Market forecast pipeline: {MARKET_PIPELINE_STATUS.get('pipeline_status', 'MANUAL_BUNDLE')}."
    if MARKET_PIPELINE_STATUS.get("refresh_error"):
        pipeline_text += " Refresh failed, so the last validated bundle was retained."
    note = html.Div([
        html.Div(timing_text, className="scenario-note-line uncertainty-warning"),
        html.Div(pipeline_text, className="scenario-note-line uncertainty-line"),
        html.Div(
            "The price-only schedule maximises value under the forecast APX signal. The reserve-aware schedule uses the same price forecast but keeps SOC inside the Stage B uncertainty corridor so battery energy/headroom remains available for renewable forecast risk.",
            className="scenario-note-line",
        ),
        html.Div(
            "Displayed £ values are model-implied under the forecast price signal and the entered throughput-cost assumption. They are not realised trading revenue and APX MIP is not a licensed day-ahead auction price.",
            className="scenario-note-line uncertainty-line",
        ),
    ])
    return note, cards, figure


def _quick_reserve_day_analysis(
    date_value: str,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
    throughput_cost: float,
    guard_windows: int,
):
    market = select_market_index_prices(MARKET_INDEX_PRICES, date_value)
    system = select_system_prices(SYSTEM_PRICES, date_value)
    source_day = select_date(HISTORICAL_DATA, date_value)
    portfolio = build_virtual_portfolio(
        source_day, portfolio_type, float(capacity_mw),
        wind_share=float(wind_share_pct) / 100.0,
    )
    valid = pd.to_datetime(market["valid_time_utc"], utc=True)
    qr = QUICK_RESERVE.loc[QUICK_RESERVE["delivery_start_utc"].isin(valid)].copy()
    if len(qr) != 2 * len(market):
        raise ValueError("Quick Reserve evidence is unavailable for this historical date.")
    grid = scaled_design_grid(
        DESIGN_GRID, portfolio_type, float(capacity_mw), float(wind_share_pct)
    )
    selected = select_stable_design(grid, design_target_pct, design_reliability_pct)
    if selected is None:
        raise ValueError("No stable future design exists for the selected design gate.")
    battery = BatteryConfig(
        power_mw=float(selected["power_mw"]), duration_hours=float(selected["duration_hours"]),
        round_trip_efficiency=0.90, initial_soc_fraction=0.50,
    )
    _arb_frame, arb = optimise_wholesale_arbitrage(
        market, battery, WholesaleArbitrageConfig(float(throughput_cost))
    )
    _firm_arb_frame, firm_arb = optimise_firming_and_arbitrage(
        portfolio, system, market, battery, float(throughput_cost)
    )
    _qr_only_frame, qr_only = optimise_arbitrage_and_quick_reserve(
        market, qr, battery,
        QuickReserveStackingConfig(
            float(throughput_cost), crossover_guard_windows=int(guard_windows),
            enable_arbitrage=False,
        ),
    )
    stacked_frame, stacked = optimise_arbitrage_and_quick_reserve(
        market, qr, battery,
        QuickReserveStackingConfig(
            float(throughput_cost), crossover_guard_windows=int(guard_windows),
            enable_arbitrage=True,
        ),
    )
    triple_frame, triple = optimise_firming_arbitrage_and_quick_reserve(
        portfolio, system, market, qr, battery,
        QuickReserveStackingConfig(
            float(throughput_cost), crossover_guard_windows=int(guard_windows),
            enable_arbitrage=True,
        ),
    )
    return {
        "market": market, "qr": qr, "selected": selected, "battery": battery,
        "arbitrage": arb, "firm_arb": firm_arb,
        "qr_only": qr_only, "stacked": stacked,
        "stacked_frame": stacked_frame, "triple": triple,
        "triple_frame": triple_frame,
    }


def _quick_reserve_figure(analysis: dict[str, Any]) -> go.Figure:
    frame = analysis["triple_frame"]
    triple = frame
    battery = analysis["battery"]
    figure = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.07,
        row_heights=[0.20, 0.27, 0.25, 0.28],
    )
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"], y=frame["pqr_price"],
        mode="lines", name="PQR clearing price",
    ), row=1, col=1)
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"], y=frame["nqr_price"],
        mode="lines", name="NQR clearing price", line={"dash": "dash"},
    ), row=1, col=1)
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"], y=frame["triple_pqr_contracted_mw"],
        mode="lines", name="PQR contracted MW",
    ), row=2, col=1)
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"], y=-frame["triple_nqr_contracted_mw"],
        mode="lines", name="NQR contracted MW (shown negative)",
    ), row=2, col=1)
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"],
        y=frame["triple_arbitrage_discharge_mw"] - frame["triple_arbitrage_charge_mw"],
        mode="lines", name="Wholesale schedule", line={"dash": "dot"},
    ), row=2, col=1)
    original_error = triple["actual_mw"].astype(float) - triple["forecast_mw"].astype(float)
    figure.add_trace(go.Scatter(
        x=triple["valid_time_utc"], y=original_error,
        mode="lines", name="Original renewable error",
    ), row=3, col=1)
    figure.add_trace(go.Scatter(
        x=triple["valid_time_utc"], y=triple["triple_residual_error_mw"],
        mode="lines", name="Triple-stack residual", line={"dash": "dash"},
    ), row=3, col=1)
    figure.add_trace(go.Scatter(
        x=triple["valid_time_utc"],
        y=100.0 * triple["triple_soc_end_mwh"] / battery.energy_capacity_mwh,
        mode="lines", name="Triple-stack SOC",
    ), row=4, col=1)
    figure.add_hline(y=0.0, line_dash="dash", row=2, col=1)
    figure.add_hline(y=0.0, line_dash="dash", row=3, col=1)
    figure.add_hline(y=100.0 * battery.minimum_soc_fraction, line_dash="dot", row=4, col=1)
    figure.add_hline(y=100.0 * battery.maximum_soc_fraction, line_dash="dot", row=4, col=1)
    figure.update_yaxes(title_text="?/MW/h", row=1, col=1)
    figure.update_yaxes(title_text="MW", row=2, col=1)
    figure.update_yaxes(title_text="Error (MW)", row=3, col=1)
    figure.update_yaxes(title_text="SOC (%)", row=4, col=1)
    figure.update_xaxes(title_text="Delivery time (UTC)", row=4, col=1)
    figure.update_layout(
        height=820, hovermode="x unified", margin=dict(l=60, r=20, t=55, b=50),
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
    )
    return figure

def _quick_reserve_predelivery_view(date_value: str):
    target = pd.Timestamp(date_value).normalize()
    daily = QUICK_RESERVE_PREDELIVERY_DAILY.copy()
    daily["settlement_date"] = pd.to_datetime(daily["settlement_date"]).dt.normalize()
    selected_daily = daily.loc[daily["settlement_date"].eq(target)]
    summary = QUICK_RESERVE_PREDELIVERY_SUMMARY
    diagnostic = QUICK_RESERVE_ACCEPTANCE_DIAGNOSTIC["combined"]
    cards = [
        _kpi_card("QR price forecast MAE", f"£{summary['locked_price_mae_gbp_per_mw_per_hour']:.2f}/MW/h", "90 locked Apr–Jun dates"),
        _kpi_card("Forecast allocation capture", f"{summary['forecast_value_capture_pct']:.1f}%", "Price-taker/system-volume scoring"),
        _kpi_card("Naive allocation capture", f"{summary['naive_value_capture_pct']:.1f}%", "Previous-same-product/period signal"),
        _kpi_card("Forecast QR value", f"£{summary['forecast_selected_availability_annualised_gbp']/1e6:.2f}m/yr", "90-day regime annualisation"),
        _kpi_card("Forecast uplift vs naive", f"£{summary['forecast_uplift_vs_naive_annualised_gbp']/1e3:.0f}k/yr", "Same price-taker scoring assumption"),
        _kpi_card("Simple bid-threshold precision", f"{diagnostic['precision_pct']:.1f}%", "Why clearing price alone cannot model acceptance"),
    ]
    note = html.Div([
        html.Div(
            "The QR clearing-price model uses earlier EAC delivery dates only. Forecast-selected PQR/NQR capacity is frozen before the target day, then scored against subsequent clearing results.",
            className="scenario-note-line",
        ),
        html.Div(
            "The 93% capture figure is not acceptance-adjusted asset revenue. It assumes offered capacity is accepted up to realised system-cleared volume. Historical Sell Orders show that bid price alone is a poor execution classifier, so no unsupported asset-specific acceptance probability is applied.",
            className="scenario-note-line uncertainty-warning",
        ),
        html.Div(
            f"Across Apr–Jun 2026 Sell Orders, the simple rule bid price ≤ clearing price has only {diagnostic['precision_pct']:.1f}% precision for actual execution across {diagnostic['orders']:,} Quick Reserve orders.",
            className="scenario-note-line uncertainty-line",
        ),
    ])
    if selected_daily.empty:
        return note, cards, _empty_figure(
            "Pre-delivery QR allocation evidence is available on the 90 Apr–Jun 2026 V2 locked dates."
        )
    row = selected_daily.iloc[0]
    cards = cards + [
        _kpi_card("Selected-day perfect QR", f"£{row['perfect_qr_availability_gbp']:,.0f}", "Realised clearing-price upper bound"),
        _kpi_card("Selected-day forecast QR", f"£{row['forecast_selected_qr_availability_gbp']:,.0f}", "Forecast-selected capacity, ex-post scored"),
        _kpi_card("Selected-day capture", f"{row['forecast_capture_pct']:.1f}%", "Relative to perfect-information QR-only"),
    ]
    price = QUICK_RESERVE_PRICE_FORECAST.copy()
    price["settlement_date"] = pd.to_datetime(price["settlement_date"]).dt.normalize()
    price = price.loc[price["settlement_date"].eq(target)].copy()
    allocation = QUICK_RESERVE_PREDELIVERY_ALLOCATIONS.copy()
    allocation["settlement_date"] = pd.to_datetime(allocation["settlement_date"]).dt.normalize()
    allocation = allocation.loc[allocation["settlement_date"].eq(target)].copy()
    if price.empty or allocation.empty:
        return note, cards, _empty_figure("Selected-day QR price/allocation detail is unavailable.")
    price["delivery_start_utc"] = pd.to_datetime(price["delivery_start_utc"], utc=True)
    allocation["delivery_start_utc"] = pd.to_datetime(allocation["delivery_start_utc"], utc=True)
    pqr = price.loc[price["product"].eq("PQR")]
    nqr = price.loc[price["product"].eq("NQR")]
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10)
    for subset, product in ((pqr, "PQR"), (nqr, "NQR")):
        figure.add_trace(go.Scatter(
            x=subset["delivery_start_utc"],
            y=subset["clearing_price_gbp_per_mw_per_hour"],
            mode="lines", name=f"{product} realised clearing",
        ), row=1, col=1)
        figure.add_trace(go.Scatter(
            x=subset["delivery_start_utc"],
            y=subset["forecast_qr_clearing_price_gbp_per_mw_per_hour"],
            mode="lines", name=f"{product} prior-date forecast", line={"dash": "dash"},
        ), row=1, col=1)
    figure.add_trace(go.Scatter(
        x=allocation["delivery_start_utc"],
        y=allocation["pqr_contracted_mw"],
        mode="lines", name="Forecast-selected PQR MW",
    ), row=2, col=1)
    figure.add_trace(go.Scatter(
        x=allocation["delivery_start_utc"],
        y=-allocation["nqr_contracted_mw"],
        mode="lines", name="Forecast-selected NQR MW (shown negative)",
    ), row=2, col=1)
    figure.add_hline(y=0.0, line_dash="dash", row=2, col=1)
    figure.update_yaxes(title_text="£/MW/h", row=1, col=1)
    figure.update_yaxes(title_text="MW", row=2, col=1)
    figure.update_xaxes(title_text="Delivery time (UTC)", row=2, col=1)
    figure.update_layout(
        height=560, hovermode="x unified", margin=dict(l=60, r=20, t=55, b=50),
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
    )
    return note, cards, figure


def _market_investment_reference_supported(
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
) -> bool:
    return (
        portfolio_type == "mixed"
        and abs(float(capacity_mw) - 100.0) < 1e-9
        and abs(float(wind_share_pct) - 50.0) < 1e-9
        and abs(float(design_target_pct) - 90.0) < 1e-9
        and abs(float(design_reliability_pct) - 90.0) < 1e-9
    )


def _annualise_daily_value(frame: pd.DataFrame, column: str) -> float:
    values = pd.to_numeric(frame[column], errors="raise")
    if frame.empty:
        raise ValueError("Market investment evidence is empty.")
    return float(values.sum() * 365.25 / len(frame))


def _market_investment_assumptions(
    capex_million: float,
    fixed_opex_million: float,
    asset_life_years: int,
    discount_rate_pct: float,
    degradation_pct: float,
    replacement_year: int | float | None,
    replacement_cost_million: float,
) -> MarketInvestmentAssumptions:
    replacement_value = int(replacement_year or 0)
    replacement = None if replacement_value <= 0 else replacement_value
    return MarketInvestmentAssumptions(
        total_capex_gbp=float(capex_million) * 1e6,
        fixed_opex_gbp_per_year=float(fixed_opex_million) * 1e6,
        asset_life_years=int(asset_life_years),
        discount_rate=float(discount_rate_pct) / 100.0,
        annual_revenue_degradation_fraction=float(degradation_pct) / 100.0,
        replacement_year=replacement,
        replacement_cost_gbp=float(replacement_cost_million) * 1e6,
    )


def _market_investment_scenarios(
    assumptions: MarketInvestmentAssumptions,
) -> dict[str, dict[str, Any]]:
    market = PREDELIVERY_DAILY.copy()
    locked = market.loc[market["evaluation_segment"].eq("locked_test")].copy()
    qr = QUICK_RESERVE_PREDELIVERY_DAILY.copy()
    annual_values = {
        "Forecast wholesale · 420d": _annualise_daily_value(
            market, "forecast_strategy_margin_gbp"
        ),
        "Reserve-aware wholesale · 420d": _annualise_daily_value(
            market, "reserve_aware_forecast_margin_gbp"
        ),
    }
    locked_market = _annualise_daily_value(
        locked, "forecast_strategy_margin_gbp"
    )
    locked_reserve = _annualise_daily_value(
        locked, "reserve_aware_forecast_margin_gbp"
    )
    qr_value = _annualise_daily_value(
        qr, "forecast_selected_qr_availability_gbp"
    )
    annual_values["Apr–Jun wholesale + QR upside"] = locked_market + qr_value
    annual_values["Apr–Jun reserve + QR upside"] = locked_reserve + qr_value
    results: dict[str, dict[str, Any]] = {}
    break_even_annual = minimum_annual_market_value_for_zero_npv_gbp(assumptions)
    for name, annual_value in annual_values.items():
        appraisal = appraise_market_operating_value(annual_value, assumptions)
        results[name] = {
            "annual_operating_value_gbp": float(annual_value),
            "npv_gbp": float(appraisal["npv_gbp"]),
            "benefit_cost_ratio": float(appraisal["benefit_cost_ratio"]),
            "simple_payback_years": appraisal["simple_payback_years"],
            "maximum_capex_for_zero_npv_gbp": maximum_capex_for_market_zero_npv_gbp(
                annual_value, assumptions
            ),
            "minimum_annual_market_value_for_zero_npv_gbp": break_even_annual,
        }
    return results


def _market_investment_figure(
    scenarios: dict[str, dict[str, Any]],
) -> go.Figure:
    names = list(scenarios)
    npv = [scenarios[name]["npv_gbp"] / 1e6 for name in names]
    custom = [
        [
            scenarios[name]["annual_operating_value_gbp"] / 1e6,
            scenarios[name]["benefit_cost_ratio"],
        ]
        for name in names
    ]
    figure = go.Figure(go.Bar(
        x=names,
        y=npv,
        customdata=custom,
        hovertemplate=(
            "NPV £%{y:.2f}m<br>Annual operating value £%{customdata[0]:.2f}m"
            "<br>BCR %{customdata[1]:.2f}<extra></extra>"
        ),
    ))
    figure.add_hline(y=0.0, line_dash="dash")
    figure.update_layout(
        yaxis_title="NPV (£m)", xaxis_title="Market-backed scenario",
        margin=dict(l=60, r=20, t=45, b=105), height=430,
    )
    return figure


def _market_investment_mc(
    assumptions: MarketInvestmentAssumptions,
    availability_pct: float,
    simulations: int,
    block_days: int,
    seed: int,
):
    evidence = PREDELIVERY_DAILY[[
        "settlement_date", "forecast_strategy_margin_gbp"
    ]].rename(columns={"forecast_strategy_margin_gbp": "market_value_gbp"})
    availability_mode = float(availability_pct) / 100.0
    distributions = MarketInvestmentDistributions(
        availability_fraction=TriangularMultiplier(
            max(0.0, availability_mode - 0.05),
            availability_mode,
            min(1.0, availability_mode + 0.05),
        )
    )
    return run_market_investment_monte_carlo(
        evidence,
        "market_value_gbp",
        assumptions,
        MarketInvestmentMonteCarloConfig(
            simulations=int(simulations), seed=int(seed), sample_days=365,
            block_days=int(block_days), confidence=0.95,
        ),
        distributions,
    )


def _tomorrow_planning_data(
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    battery_power_mw: float,
    duration_hours: float,
    current_soc_pct: float,
    efficiency_pct: float,
) -> tuple[pd.DataFrame, BatteryConfig, dict[str, Any]]:
    history = build_virtual_portfolio(
        HISTORICAL_DATA, portfolio_type=portfolio_type, capacity_mw=float(capacity_mw),
        wind_share=float(wind_share_pct) / 100,
    )
    forecast = build_virtual_forecast(
        LATEST_FORECAST, portfolio_type=portfolio_type, capacity_mw=float(capacity_mw),
        wind_share=float(wind_share_pct) / 100,
    )
    interval, uncertainty = build_forecast_only_directional_interval(
        history, forecast, LATEST_TARGET_DATE,
        PredictionIntervalConfig(lookback_days=180, minimum_history_days=30, neighbour_count=600),
    )
    config = BatteryConfig(
        power_mw=float(battery_power_mw), duration_hours=float(duration_hours),
        round_trip_efficiency=float(efficiency_pct) / 100,
        initial_soc_fraction=float(current_soc_pct) / 100,
    )
    planning: dict[str, Any] = {"uncertainty": uncertainty}
    reserve_series = interval
    if uncertainty.get("available"):
        reserve_series, reserve = build_reserve_plan(
            interval,
            config,
            ReservePlanningConfig(current_soc_fraction=float(current_soc_pct) / 100),
        )
        planning["reserve"] = reserve
        planning.update({
            "peak_downward_reserve_mw": reserve["peak_downward_reserve_mw"],
            "peak_upward_headroom_mw": reserve["peak_upward_headroom_mw"],
            "peak_interval_deviation_mw": max(
                reserve["peak_downward_reserve_mw"], reserve["peak_upward_headroom_mw"]
            ),
            "battery_power_coverage_pct": min(
                reserve["downward_power_coverage_pct"], reserve["upward_power_coverage_pct"]
            ),
        })
    planning["forecast_energy_mwh"] = float(reserve_series["forecast_mw"].sum() * 0.5)
    planning["peak_forecast_mw"] = float(reserve_series["forecast_mw"].max())
    return reserve_series, config, planning


def _tomorrow_forecast_figure(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    if {"prediction_interval_lower_mw", "prediction_interval_upper_mw"}.issubset(frame.columns):
        figure.add_trace(go.Scatter(
            x=frame["valid_time_utc"], y=frame["prediction_interval_lower_mw"],
            mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False,
        ))
        figure.add_trace(go.Scatter(
            x=frame["valid_time_utc"], y=frame["prediction_interval_upper_mw"],
            mode="lines", line={"width": 0}, fill="tonexty",
            fillcolor="rgba(99,110,250,0.16)", name="Directional empirical 80% range",
        ))
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"], y=frame["forecast_mw"],
        mode="lines", name="Scheduled renewable export", line={"dash": "dash", "width": 2.6},
    ))
    figure.update_layout(
        xaxis_title="Settlement time (UTC)", yaxis_title="Virtual portfolio power (MW)",
        hovermode="x unified", margin=dict(l=45, r=20, t=65, b=45),
        legend={"orientation": "h", "y": 1.03, "yanchor": "bottom", "x": 0}, height=390,
    )
    return figure


def _reserve_plan_figure(frame: pd.DataFrame, reserve: dict[str, Any]) -> go.Figure:
    """Show rolling downward reserve and upward headroom needs for the forecast day."""
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"],
        y=frame["downward_reserve_requirement_mwh"],
        mode="lines",
        name="Downward reserve need",
        hovertemplate="Downward reserve %{y:.1f} MWh<extra></extra>",
    ))
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"],
        y=frame["upward_headroom_requirement_mwh"],
        mode="lines",
        name="Upward charge headroom need",
        hovertemplate="Upward headroom %{y:.1f} MWh<extra></extra>",
    ))
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"],
        y=[reserve["available_discharge_reserve_mwh"]] * len(frame),
        mode="lines",
        name="Available discharge reserve",
        line={"dash": "dash"},
        hovertemplate="Available discharge reserve %{y:.1f} MWh<extra></extra>",
    ))
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"],
        y=[reserve["available_charge_headroom_mwh"]] * len(frame),
        mode="lines",
        name="Available charge headroom",
        line={"dash": "dot"},
        hovertemplate="Available charge headroom %{y:.1f} MWh<extra></extra>",
    ))
    figure.update_layout(
        xaxis_title="Reserve-window start (UTC)",
        yaxis_title="Energy (MWh)",
        hovermode="x unified",
        margin=dict(l=55, r=20, t=65, b=45),
        legend={"orientation": "h", "y": 1.03, "yanchor": "bottom", "x": 0},
        height=390,
    )
    return figure


def _grid_demand_figure(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"], y=frame["national_demand_mw"] / 1000.0,
        mode="lines", name="NESO National Demand Forecast", line={"width": 2.6},
    ))
    figure.update_layout(
        xaxis_title="Settlement time (UTC)", yaxis_title="GB National Demand Forecast (GW)",
        hovermode="x unified", margin=dict(l=55, r=20, t=55, b=45),
        legend={"orientation": "h", "y": 1.03, "yanchor": "bottom", "x": 0}, height=330,
    )
    return figure


def _spatial_zone_figure(frame: pd.DataFrame, zone: str) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"], y=frame["zone_wind_virtual_mw"],
        mode="lines", name="Allocated wind forecast",
    ))
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"], y=frame["zone_solar_virtual_mw"],
        mode="lines", name="Allocated solar forecast",
    ))
    figure.add_trace(go.Scatter(
        x=frame["valid_time_utc"], y=frame["zone_virtual_forecast_mw"],
        mode="lines", name="Zone total", line={"width": 3},
    ))
    figure.update_layout(
        xaxis_title="Settlement time (UTC)",
        yaxis_title="Allocated virtual portfolio forecast (MW)",
        hovermode="x unified", height=390,
        margin=dict(l=55, r=20, t=55, b=45),
        legend={"orientation": "h", "y": 1.03, "yanchor": "bottom", "x": 0},
        title=f"{zone} spatial allocation",
    )
    return figure


def _spatial_zone_view(
    zone: str,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
):
    spatial = build_spatial_virtual_forecast(
        LATEST_SPATIAL_FORECAST, LATEST_FORECAST,
        portfolio_type, float(capacity_mw), float(wind_share_pct) / 100.0,
    )
    selected_zone = spatial.loc[spatial["zone"].eq(zone)].copy()
    if selected_zone.empty:
        raise KeyError(f"Unknown spatial zone: {zone}")
    design_grid = scaled_design_grid(
        DESIGN_GRID, portfolio_type, float(capacity_mw), float(wind_share_pct)
    )
    selected_design = select_stable_design(
        design_grid, float(design_target_pct), float(design_reliability_pct)
    )
    if selected_design is None:
        raise ValueError("No stable future battery design exists for this gate.")
    zone_capacity = float(selected_zone["zone_virtual_capacity_proxy_mw"].iloc[0])
    capacity_share = float(selected_zone["zone_capacity_share"].iloc[0])
    zone_energy = float(selected_zone["zone_virtual_forecast_mw"].sum() * 0.5)
    national_energy = float(spatial.groupby("settlement_period")["zone_virtual_forecast_mw"].sum().sum() * 0.5)
    energy_share = 100.0 * zone_energy / national_energy if national_energy > 0 else 0.0
    peak = float(selected_zone["zone_virtual_forecast_mw"].max())
    proxy_power = float(selected_design["power_mw"]) * capacity_share
    proxy_energy = float(selected_design["energy_mwh"]) * capacity_share
    cards = [
        _kpi_card("Spatial zone", zone, "One of the 10 V2 weather/allocation zones"),
        _kpi_card("Allocated nameplate proxy", f"{zone_capacity:.1f} MW", f"{100*capacity_share:.1f}% of selected virtual portfolio"),
        _kpi_card("Forecast energy", f"{zone_energy:.1f} MWh", f"{energy_share:.1f}% of allocated forecast-day energy"),
        _kpi_card("Peak allocated forecast", f"{peak:.1f} MW", "Weather-informed share of national V2 forecast"),
        _kpi_card("Indicative BESS share", f"{proxy_power:.1f} MW / {proxy_energy:.1f} MWh", "Proportional Stage A allocation only"),
        _kpi_card("Implied duration", f"{float(selected_design['duration_hours']):.0f} h", "Inherited from national Stage A design"),
    ]
    note = html.Div([
        html.Div(
            "This is a spatial allocation of the authoritative GB V2 forecast, not an independently trained or observed city-generation forecast.",
            className="scenario-note-line uncertainty-warning",
        ),
        html.Div(
            "Each half-hour, the national wind/solar MW totals are distributed across the same 10 V2 weather locations using DESNZ REPD operational-capacity proxy weights multiplied by local issue-time weather signals. The ten zones reconcile exactly back to the GB V2 totals.",
            className="scenario-note-line",
        ),
        html.Div(
            "The BESS figure is only a proportional allocation of the national Stage A design. City-specific forecast-error histories and local grid constraints are not available, so it is not an independently sized local battery recommendation. Demand, System Price and market settlement remain GB-level.",
            className="scenario-note-line uncertainty-line",
        ),
    ])
    return note, cards, _spatial_zone_figure(selected_zone, zone)


def _scenario(
    date_value: str,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    battery_power_mw: float,
    duration_hours: float,
    initial_soc_pct: float,
    round_trip_efficiency_pct: float,
) -> tuple[pd.DataFrame, BatteryConfig, dict[str, Any], dict[str, Any]]:
    full_portfolio = build_virtual_portfolio(
        HISTORICAL_DATA,
        portfolio_type=portfolio_type,  # type: ignore[arg-type]
        capacity_mw=float(capacity_mw),
        wind_share=float(wind_share_pct) / 100,
    )
    target = pd.Timestamp(date_value).normalize()
    portfolio = full_portfolio.loc[
        full_portfolio["settlement_date"].eq(target)
    ].copy().reset_index(drop=True)
    if portfolio.empty:
        raise KeyError(f"No historical evidence is available for {target.date()}.")
    interval, uncertainty = build_rolling_prediction_interval(
        full_portfolio, target
    )
    config = BatteryConfig(
        power_mw=float(battery_power_mw),
        duration_hours=float(duration_hours),
        round_trip_efficiency=float(round_trip_efficiency_pct) / 100,
        initial_soc_fraction=float(initial_soc_pct) / 100,
    )
    simulation = simulate_reactive_firming(portfolio, config)
    if uncertainty.get("available"):
        columns = [
            "settlement_period",
            "prediction_interval_lower_mw",
            "prediction_interval_upper_mw",
            "actual_inside_prediction_interval",
        ]
        simulation = simulation.merge(
            interval[columns], on="settlement_period", how="left", validate="one_to_one"
        )
    metrics = calculate_firming_metrics(simulation, config)
    return simulation, config, metrics, uncertainty


app.layout = html.Div(
    [
        dcc.Store(id="scenario-store"),
        dcc.Download(id="scenario-download"),
        html.Header(
            [
                html.Div("RENEWABLE FLEXIBILITY STUDIO", className="eyebrow"),
                html.H1("Turn renewable forecast deviations into storage decisions"),
                html.P(
                    "Explore a virtual wind, solar or mixed portfolio; configure a battery; and see how power, duration and state of charge affect delivery firming.",
                    className="subtitle",
                ),
                html.Div(
                    [
                        html.Span("Historical evidence: 1 Apr 2025 to 30 Jun 2026", className="status-pill"),
                        html.Span("V2 out-of-sample: OOF + locked test", className="status-pill"),
                        html.Span("Reactive strategy", className="status-pill"),
                    ],
                    className="status-row",
                ),
            ],
            className="hero",
        ),
        html.Main(
            [
                html.Section(
                    [
                        html.Div(
                            [
                                html.H2("Configure the scenario"),
                                html.P("Small, transparent controls recalculate the physical battery response.", className="section-copy"),
                                html.Label("Historical target date"),
                                dcc.Dropdown(
                                    id="date-input",
                                    options=[{"label": date, "value": date} for date in DATE_OPTIONS],
                                    value=DEFAULT_DATE,
                                    clearable=False,
                                ),
                                html.Label("Renewable portfolio"),
                                dcc.RadioItems(
                                    id="portfolio-input",
                                    options=[
                                        {"label": "Wind", "value": "wind"},
                                        {"label": "Solar", "value": "solar"},
                                        {"label": "Mixed", "value": "mixed"},
                                    ],
                                    value="mixed",
                                    inline=True,
                                    className="radio-row",
                                ),
                                html.Label("Portfolio capacity (MW)"),
                                dcc.Input(id="capacity-input", type="number", min=10, max=500, step=10, value=100),
                                html.Div(
                                    [
                                        html.Label("Wind share in mixed portfolio (%)"),
                                        dcc.Slider(
                                            id="wind-share-input",
                                            min=0,
                                            max=100,
                                            step=5,
                                            value=50,
                                            marks={0: "0", 50: "50", 100: "100"},
                                            tooltip={"placement": "bottom", "always_visible": False},
                                        ),
                                    ],
                                    id="wind-share-container",
                                ),
                                html.Hr(),
                                html.Label("Historical scenario battery power (MW)"),
                                dcc.Input(id="power-input", type="number", min=1, max=250, step=1, value=25),
                                html.Label("Historical scenario battery duration"),
                                dcc.RadioItems(
                                    id="duration-input",
                                    options=[
                                        {"label": "1 hour", "value": 1},
                                        {"label": "2 hours", "value": 2},
                                        {"label": "4 hours", "value": 4},
                                    ],
                                    value=2,
                                    inline=True,
                                    className="radio-row",
                                ),
                                html.Label("Initial SOC for selected historical day (%)"),
                                dcc.Slider(
                                    id="soc-input",
                                    min=10,
                                    max=90,
                                    step=5,
                                    value=50,
                                    marks={10: "10", 50: "50", 90: "90"},
                                    tooltip={"placement": "bottom", "always_visible": False},
                                ),
                                html.Div(id="initial-energy-note", className="control-help"),
                                html.Label("Historical scenario round-trip efficiency (%)"),
                                dcc.Slider(
                                    id="efficiency-input",
                                    min=80,
                                    max=100,
                                    step=1,
                                    value=90,
                                    marks={80: "80", 90: "90", 100: "100"},
                                    tooltip={"placement": "bottom", "always_visible": False},
                                ),
                                html.Label("Selected-day sizing target: deviations absorbed"),
                                dcc.Dropdown(
                                    id="target-input",
                                    options=[
                                        {"label": "50%", "value": 50},
                                        {"label": "80%", "value": 80},
                                        {"label": "90%", "value": 90},
                                        {"label": "95%", "value": 95},
                                    ],
                                    value=80,
                                    clearable=False,
                                ),
                                html.Div(
                                    [
                                        html.Button("Run scenario", id="run-button", n_clicks=0, className="primary-button"),
                                        html.Button("Size selected day", id="size-button", n_clicks=0, className="secondary-button"),
                                    ],
                                    className="button-row",
                                ),
                            ],
                            className="control-panel",
                        ),
                        html.Div(
                            [
                                html.Div(id="scenario-note", className="scenario-note"),
                                html.Div(id="kpi-grid", className="kpi-grid"),
                                html.Div("Forecast uncertainty and battery firming", className="chart-title"),
                                html.Div(
                                    "Shaded band = nominal 80% rolling prediction interval calibrated only from earlier out-of-sample forecast errors. It is not yet a weather-ensemble P10/P50/P90 forecast.",
                                    className="chart-subtitle",
                                ),
                                dcc.Graph(id="generation-chart", config={"displaylogo": False}),
                                html.Div("Battery operation and state of charge", className="chart-title"),
                                dcc.Graph(id="battery-chart", config={"displaylogo": False}),
                            ],
                            className="results-panel",
                        ),
                    ],
                    className="workspace",
                ),
                html.Section(
                    [
                        html.H2("Future battery sizing benchmark"),
                        html.P(
                            "This is the main design output. It uses all 450 out-of-sample historical days as future-like evidence and requires the chosen MW/MWh design to remain stable in both Apr 2025–Mar 2026 and Apr–Jun 2026. Portfolio capacity and wind/solar mix come from the controls above.",
                            className="section-copy",
                        ),
                        html.P(
                            "Practical sizing mode assumes a grid-connected reserve battery: SOC is restored to 50% before each operating day, then the battery reacts only to renewable forecast deviations during that day. The required grid-restoration energy is measured and will be costed in the economics stage.",
                            className="section-copy",
                        ),
                        html.Div(
                            [
                                html.Div([
                                    html.Label("Daily firming target"),
                                    dcc.Dropdown(
                                        id="design-target-input",
                                        options=[{"label": f"{v}% of forecast-error energy", "value": v} for v in (80, 90, 95)],
                                        value=90, clearable=False,
                                    ),
                                ]),
                                html.Div([
                                    html.Label("Required reliability across days"),
                                    dcc.Dropdown(
                                        id="design-reliability-input",
                                        options=[{"label": f"At least {v}% of days", "value": v} for v in (80, 90, 95)],
                                        value=90, clearable=False,
                                    ),
                                ]),
                            ],
                            className="design-controls",
                        ),
                        html.Div(id="design-note", className="recommendation-box"),
                        html.Div(id="design-kpi-grid", className="kpi-grid"),
                        dcc.Graph(
                            id="design-heatmap",
                            figure=_empty_figure("Future sizing evidence is loading."),
                            config={"displaylogo": False},
                        ),
                    ],
                    className="download-section design-section",
                ),
                html.Section(
                    [
                        html.H2("Risk & Value decision layer"),
                        html.P(
                            "This pre-feasibility layer converts the 450-day physical firming evidence into avoided exposure and discounted lifecycle value. All monetary inputs below are visible scenario assumptions, not observed market prices or bankable project costs.",
                            className="section-copy",
                        ),
                        html.Div(
                            [
                                html.Div([
                                    html.Label("Consequence value (£/MWh)"),
                                    dcc.Input(id="risk-consequence-input", type="number", min=0, step=10, value=100),
                                ]),
                                html.Div([
                                    html.Label("Selected-design CAPEX (£m)"),
                                    dcc.Input(id="risk-capex-input", type="number", min=0, step=1, value=25),
                                ]),
                                html.Div([
                                    html.Label("Selected-design fixed OPEX (£m/year)"),
                                    dcc.Input(id="risk-fixed-opex-input", type="number", min=0, step=0.1, value=0.5),
                                ]),
                                html.Div([
                                    html.Label("Variable OPEX (£/MWh throughput)"),
                                    dcc.Input(id="risk-variable-opex-input", type="number", min=0, step=0.5, value=2.0),
                                ]),
                            ],
                            className="design-controls",
                        ),
                        html.Div(
                            [
                                html.Div([
                                    html.Label("Asset life (years)"),
                                    dcc.Input(id="risk-life-input", type="number", min=1, step=1, value=15),
                                ]),
                                html.Div([
                                    html.Label("Discount rate (%)"),
                                    dcc.Input(id="risk-discount-input", type="number", min=-99, step=0.5, value=8),
                                ]),
                                html.Div([
                                    html.Label("Annual degradation (%)"),
                                    dcc.Input(id="risk-degradation-input", type="number", min=0, max=99, step=0.5, value=2),
                                ]),
                                html.Div([
                                    html.Label("Expected battery availability (%)"),
                                    dcc.Input(id="risk-availability-input", type="number", min=0, max=100, step=1, value=95),
                                ]),
                            ],
                            className="design-controls",
                        ),
                        html.Div(
                            "For comparison across battery configurations, CAPEX and fixed OPEX are scaled in proportion to candidate MWh relative to the Stage A selected design. This is a transparent screening assumption, not a supplier cost curve.",
                            className="control-help",
                        ),
                        html.Div(id="risk-value-note", className="recommendation-box"),
                        html.Div(id="risk-value-kpi-grid", className="kpi-grid"),
                        html.Div("Risk–value frontier", className="chart-title"),
                        html.Div(
                            "Each point is one tested battery configuration. The x-axis is discounted lifecycle cost; the y-axis is present value of avoided expected loss under the consequence-value assumption. Dominated options cost at least as much while avoiding no more loss than another tested option.",
                            className="chart-subtitle",
                        ),
                        dcc.Graph(
                            id="risk-value-frontier",
                            figure=_empty_figure("Risk-value appraisal is loading."),
                            config={"displaylogo": False},
                        ),
                        html.Div("CAPEX and consequence-value sensitivity", className="chart-title"),
                        html.Div("This heatmap varies the selected-design CAPEX by ±25% and consequence value from 50% to 150% of the entered scenario value while holding other assumptions constant.", className="chart-subtitle"),
                        dcc.Graph(id="risk-value-sensitivity", figure=_empty_figure("Sensitivity analysis is loading."), config={"displaylogo": False}),
                        html.Button("Download risk-value scenario JSON", id="risk-value-download-button", n_clicks=0, className="secondary-button"),
                        dcc.Download(id="risk-value-download"),
                        html.Hr(),
                        html.H3("Market-backed investment case (Stage 10)"),
                        html.P(
                            "This section replaces the abstract consequence-value benefit with the realised value of the prior-date forecast-selected wholesale battery schedule. It reuses CAPEX, fixed OPEX, asset life, discount rate and degradation entered above. The historical market dispatch already includes the frozen £2/MWh throughput-cost assumption.",
                            className="section-copy",
                        ),
                        html.Div(
                            [
                                html.Div([
                                    html.Label("Replacement year (0 = none)"),
                                    dcc.Input(
                                        id="market-replacement-year-input", type="number",
                                        min=0, step=1, value=0,
                                    ),
                                ]),
                                html.Div([
                                    html.Label("Replacement cost (£m)"),
                                    dcc.Input(
                                        id="market-replacement-cost-input", type="number",
                                        min=0, step=1, value=0,
                                    ),
                                ]),
                            ],
                            className="design-controls",
                        ),
                        html.Div(id="market-investment-note", className="recommendation-box"),
                        html.Div(id="market-investment-kpi-grid", className="kpi-grid"),
                        html.Div("Market-backed lifecycle NPV by evidence case", className="chart-title"),
                        html.Div(
                            "The 420-day wholesale cases are the core investment evidence. Quick Reserve is shown only as an Apr–Jun aligned price-taker availability upside because asset-specific EAC acceptance is not yet identified.",
                            className="chart-subtitle",
                        ),
                        dcc.Graph(
                            id="market-investment-chart",
                            figure=_empty_figure("Market-backed investment evidence is loading."),
                            config={"displaylogo": False},
                        ),
                        html.H4("Market-backed downside risk"),
                        html.P(
                            "This Monte Carlo resamples the realised daily value of the forecast-selected wholesale schedule in contiguous blocks, then varies CAPEX, fixed OPEX, availability and degradation. Quick Reserve is excluded from this probabilistic base until auction acceptance is modelled.",
                            className="section-copy",
                        ),
                        html.Button(
                            "Run market-backed Monte Carlo",
                            id="market-investment-mc-button", n_clicks=0,
                            className="primary-button",
                        ),
                        html.Div(id="market-investment-mc-note", className="scenario-note"),
                        html.Div(id="market-investment-mc-kpi-grid", className="kpi-grid"),
                        dcc.Graph(
                            id="market-investment-mc-chart",
                            figure=_empty_figure("Run the market-backed Monte Carlo to generate probabilistic NPV."),
                            config={"displaylogo": False},
                        ),
                        dcc.Store(id="market-investment-mc-store"),
                        html.Button(
                            "Download market-backed investment summary JSON",
                            id="market-investment-download-button", n_clicks=0,
                            className="secondary-button",
                        ),
                        dcc.Download(id="market-investment-download"),
                        html.Hr(),
                        html.H3("Quantitative downside risk (Stage 6B)"),
                        html.P(
                            "Run complete-day block-resampled Monte Carlo around the selected Stage A battery. Forecast-error dependence is preserved by sampling contiguous historical day blocks; CAPEX, consequence value, OPEX, availability and degradation use visible scenario distributions.",
                            className="section-copy",
                        ),
                        html.Div(
                            [
                                html.Div([
                                    html.Label("Monte Carlo simulations"),
                                    dcc.Dropdown(
                                        id="downside-simulations-input",
                                        options=[{"label": f"{v:,}", "value": v} for v in (500, 1000, 2000)],
                                        value=1000, clearable=False,
                                    ),
                                ]),
                                html.Div([
                                    html.Label("Contiguous block length (days)"),
                                    dcc.Dropdown(
                                        id="downside-block-input",
                                        options=[{"label": f"{v} day" if v == 1 else f"{v} days", "value": v} for v in (1, 3, 7, 14)],
                                        value=7, clearable=False,
                                    ),
                                ]),
                                html.Div([
                                    html.Label("Random seed"),
                                    dcc.Input(
                                        id="downside-seed-input", type="number", step=1,
                                        value=20260903,
                                    ),
                                ]),
                            ],
                            className="design-controls",
                        ),
                        html.Button(
                            "Run downside-risk analysis", id="downside-risk-button",
                            n_clicks=0, className="primary-button",
                        ),
                        html.Div(id="downside-risk-note", className="scenario-note"),
                        html.Div(id="downside-risk-kpi-grid", className="kpi-grid"),
                        html.Div("Probabilistic NPV distribution", className="chart-title"),
                        html.Div(
                            "P10/P50/P90 are NPV quantiles. Tail loss uses the explicit convention investment loss = -NPV, so 95% CVaR is the average loss in the worst 5% of simulations.",
                            className="chart-subtitle",
                        ),
                        dcc.Graph(
                            id="downside-risk-chart",
                            figure=_empty_figure("Run the downside-risk analysis to generate probabilistic NPV."),
                            config={"displaylogo": False},
                        ),
                        html.Div("Deterministic downside stress cases", className="chart-title"),
                        html.Div(
                            "Named stresses reduce physical benefit or availability and/or worsen cost/value assumptions. They are transparent screening scenarios, not calibrated forecasts.",
                            className="chart-subtitle",
                        ),
                        dcc.Graph(
                            id="downside-stress-chart",
                            figure=_empty_figure("Stress scenarios will appear after the downside-risk run."),
                            config={"displaylogo": False},
                        ),
                        dcc.Store(id="downside-risk-store"),
                        html.Button(
                            "Download downside-risk summary JSON",
                            id="downside-risk-download-button", n_clicks=0,
                            className="secondary-button",
                        ),
                        dcc.Download(id="downside-risk-download"),
                    ],
                    className="download-section risk-value-section",
                ),
                html.Section(
                    [
                        html.Div(
                            [
                                html.H2("Selected-day battery sizing (exploratory)"),
                                html.P(
                                    "This quick search applies only to the historical day selected above. It tests 1h, 2h and 4h batteries across a controlled MW grid and returns the smallest tested candidate that reaches your chosen deviation-absorption target. It is not the long-run battery recommendation; use the 450-day continuous-SOC evidence below for that.",
                                    className="section-copy",
                                ),
                                html.Div(
                                    "No sizing result yet. Choose a historical date and target, then click ‘Size selected day’ in the left-hand controls.",
                                    id="sizing-recommendation",
                                    className="recommendation-box sizing-placeholder",
                                ),
                            ],
                            className="sizing-copy",
                        ),
                        dcc.Graph(id="sizing-chart", figure=_empty_figure("Click ‘Size selected day’ to run the one-day sizing comparison."), config={"displaylogo": False}),
                    ],
                    className="sizing-section",
                ),
                html.Section(
                    [
                        html.H2("Historical grid imbalance & System Price"),
                        html.P(
                            "For the selected historical day, the point forecast is treated as an illustrative contracted/scheduled export. Actual-minus-schedule energy is then settled at the official Elexon System Price. This is a BSC-style virtual benchmark, not an actual registered trading account or profit calculation.",
                            className="section-copy",
                        ),
                        html.Div(id="imbalance-note", className="scenario-note"),
                        html.Div(id="imbalance-kpi-grid", className="kpi-grid"),
                        html.Div("Portfolio imbalance versus Elexon System Price", className="chart-title"),
                        html.Div(
                            "Positive portfolio imbalance means the portfolio was long (generated more than scheduled); negative means short. The price line is the official single System Price for each settlement period.",
                            className="chart-subtitle",
                        ),
                        dcc.Graph(
                            id="imbalance-chart",
                            figure=_empty_figure("Run a historical scenario above to calculate grid imbalance settlement."),
                            config={"displaylogo": False},
                        ),
                    ],
                    className="download-section",
                ),
                html.Section(
                    [
                        html.H2("GB market-linked battery optimisation"),
                        html.P(
                            "This section uses actual historical Elexon System Price plus APX Market Index Data to test how the selected battery would allocate scarce MW and SOC when financial value matters. These are ex-post perfect-information benchmarks, not deployable trading forecasts.",
                            className="section-copy",
                        ),
                        html.P(
                            "APX Market Index Price is an open short-term GB wholesale reference from Elexon. It is not labelled as a day-ahead auction price. A separate validated contract is ready for a future licensed Nord Pool/EPEX day-ahead feed without changing the optimiser architecture.",
                            className="section-copy",
                        ),
                        html.Div(
                            [
                                html.Div([
                                    html.Label("Battery throughput / degradation cost (£/MWh)"),
                                    dcc.Input(
                                        id="market-throughput-cost-input", type="number",
                                        min=0, step=0.5, value=2.0,
                                    ),
                                ]),
                            ],
                            className="design-controls",
                        ),
                        html.Button(
                            "Run market optimisation", id="market-optimisation-button",
                            n_clicks=0, className="primary-button",
                        ),
                        html.Div(id="market-optimisation-note", className="scenario-note"),
                        html.Div(id="market-optimisation-kpi-grid", className="kpi-grid"),
                        html.Div("Market prices and financially selected residual error", className="chart-title"),
                        html.Div(
                            "System Price is the realised imbalance-settlement price. APX Market Index Price is the realised short-term wholesale reference. The lower panel shows that market optimisation deliberately leaves some forecast error unfirmed when battery energy has a more valuable use.",
                            className="chart-subtitle",
                        ),
                        dcc.Graph(
                            id="market-optimisation-chart",
                            figure=_empty_figure("Select a historical day and run the market optimisation."),
                            config={"displaylogo": False},
                        ),
                        html.Hr(),
                        html.H3("Pre-delivery forecast-price strategy"),
                        html.P(
                            "This second view removes price perfect foresight. A ridge forecast uses only Market Index observations from earlier settlement dates, selects the wholesale battery schedule before the target day, and then scores that fixed schedule against the realised APX Market Index Price.",
                            className="section-copy",
                        ),
                        html.Div(id="pre-delivery-note", className="scenario-note"),
                        html.Div(id="pre-delivery-kpi-grid", className="kpi-grid"),
                        dcc.Graph(
                            id="pre-delivery-price-chart",
                            figure=_empty_figure("Pre-delivery strategy evidence is loading."),
                            config={"displaylogo": False},
                        ),
                        html.Hr(),
                        html.H3("Quick Reserve availability stacking"),
                        html.P(
                            "This view adds NESO Quick Reserve availability value to the same physical battery used for wholesale arbitrage. It uses actual EAC PQR/NQR clearing prices (£/MW/h), whole-MW contracts and a configurable state-of-energy crossover guard. Utilisation revenue and activation energy are excluded.",
                            className="section-copy",
                        ),
                        html.Div(
                            [
                                html.Div([
                                    html.Label("Quick Reserve energy/crossover guard"),
                                    dcc.Dropdown(
                                        id="quick-reserve-guard-input",
                                        options=[
                                            {"label": "1 window (30 min)", "value": 1},
                                            {"label": "2 windows (1 h)", "value": 2},
                                            {"label": "4 windows (2 h)", "value": 4},
                                        ],
                                        value=2, clearable=False,
                                    ),
                                ]),
                            ],
                            className="design-controls",
                        ),
                        html.Button(
                            "Run Quick Reserve stacking", id="quick-reserve-button",
                            n_clicks=0, className="primary-button",
                        ),
                        html.Div(id="quick-reserve-note", className="scenario-note"),
                        html.Div(id="quick-reserve-kpi-grid", className="kpi-grid"),
                        html.Div("Quick Reserve prices, commitments and shared-battery SOC", className="chart-title"),
                        html.Div(
                            "PQR is upward reserve and NQR is downward reserve. NQR commitments are plotted below zero only for visual separation. The wholesale schedule and reserve commitments share one BESS power and SOC budget.",
                            className="chart-subtitle",
                        ),
                        dcc.Graph(
                            id="quick-reserve-chart",
                            figure=_empty_figure("Quick Reserve evidence is available for Apr–Jun 2026 historical dates."),
                            config={"displaylogo": False},
                        ),
                        html.H4("Pre-delivery Quick Reserve capacity signal"),
                        html.P(
                            "This layer forecasts PQR/NQR clearing prices using earlier EAC delivery dates only, freezes the capacity split before the target date, and measures how much of the perfect-information availability value that allocation would retain. It is intentionally separate from asset-specific bid acceptance.",
                            className="section-copy",
                        ),
                        html.Div(id="quick-reserve-predelivery-note", className="scenario-note"),
                        html.Div(id="quick-reserve-predelivery-kpi-grid", className="kpi-grid"),
                        dcc.Graph(
                            id="quick-reserve-predelivery-chart",
                            figure=_empty_figure("Pre-delivery QR capacity evidence is available on the locked Apr?Jun 2026 dates."),
                            config={"displaylogo": False},
                        ),
                        html.Hr(),
                        html.H3(f"Forecast-day market schedule · {LATEST_TARGET_DATE}"),
                        html.P(
                            "This view combines the latest renewable forecast, the Stage B reserve corridor and a prior-data-only APX Market Index price forecast. It shows how much wholesale scheduling value is given up to preserve battery energy/headroom for renewable uncertainty.",
                            className="section-copy",
                        ),
                        html.Div(id="forecast-market-note", className="scenario-note"),
                        html.Div(id="forecast-market-kpi-grid", className="kpi-grid"),
                        dcc.Graph(
                            id="forecast-market-chart",
                            figure=_empty_figure("Forecast-day market scheduling is loading."),
                            config={"displaylogo": False},
                        ),
                    ],
                    className="download-section market-optimisation-section",
                ),
                html.Section(
                    [
                        html.H2(f"Forecast-day operational planning & GB grid context · {LATEST_TARGET_DATE}"),
                        html.P(
                            "This section carries forward the battery selected by the Future battery sizing benchmark and combines it with the latest V2 renewable forecast. It does not simulate a future dispatch path. Instead, it calculates a directional uncertainty range, the rolling reserve/headroom needed over the installed battery duration, and the minimum SOC adjustment required before the forecast day.",
                            className="section-copy",
                        ),
                        html.Div(
                            [
                                html.Label("Current battery SOC before forecast day (%)"),
                                dcc.Slider(
                                    id="tomorrow-soc-input", min=10, max=90, step=5, value=50,
                                    marks={10: "10", 50: "50", 90: "90"},
                                    tooltip={"placement": "bottom", "always_visible": False},
                                ),
                                html.Div(
                                    "If current SOC is already inside the uncertainty-derived safe band, the recommendation is to hold it. Otherwise the planner moves only to the nearest safe boundary.",
                                    className="control-help",
                                ),
                            ],
                            className="tomorrow-soc-control",
                        ),
                        html.Button("Refresh forecast-day planning", id="tomorrow-button", n_clicks=0, className="primary-button"),
                        html.Div(id="tomorrow-note", className="scenario-note"),
                        html.Div(id="tomorrow-kpi-grid", className="kpi-grid"),
                        html.Div("Forecast-day renewable schedule and directional expected range", className="chart-title"),
                        html.Div("The dashed line is the V2 scheduled renewable export. The shaded band is an empirical directional q10–q90 residual range calibrated only from earlier out-of-sample errors; it is not yet an ECMWF ensemble P10/P90 forecast.", className="chart-subtitle"),
                        dcc.Graph(id="tomorrow-forecast-chart", figure=_empty_figure("Forecast-day planning will load automatically."), config={"displaylogo": False}),
                        html.Div("Rolling battery reserve and headroom requirements", className="chart-title"),
                        html.Div("Each point asks how much downward discharge reserve or upward charging headroom may be needed over the following window equal to the installed battery duration. Dashed reference lines show what is available at the recommended starting SOC.", className="chart-subtitle"),
                        dcc.Graph(id="tomorrow-reserve-chart", figure=_empty_figure("Reserve planning will load automatically."), config={"displaylogo": False}),
                        html.Hr(),
                        html.H3("Spatial renewable allocation zones"),
                        html.P(
                            "Select one of the ten representative V2 weather zones to inspect an indicative city-level allocation of the national renewable forecast. National wind and solar totals remain authoritative and are exactly conserved across all ten zones.",
                            className="section-copy",
                        ),
                        html.Div([
                            html.Div([
                                html.Label("Spatial zone"),
                                dcc.Dropdown(
                                    id="spatial-zone-input",
                                    options=[{"label": zone, "value": zone} for zone in SPATIAL_ZONE_OPTIONS],
                                    value="London" if "London" in SPATIAL_ZONE_OPTIONS else SPATIAL_ZONE_OPTIONS[0],
                                    clearable=False,
                                ),
                            ]),
                        ], className="design-controls"),
                        html.Div(id="spatial-zone-note", className="scenario-note"),
                        html.Div(id="spatial-zone-kpi-grid", className="kpi-grid"),
                        html.Div("Weather-informed spatial renewable allocation", className="chart-title"),
                        html.Div(
                            "The allocation combines DESNZ REPD operational-capacity proxy weights with the same ten issue-time weather locations used by V2. It is reconciled to the GB forecast and is not observed city generation.",
                            className="chart-subtitle",
                        ),
                        dcc.Graph(
                            id="spatial-zone-chart",
                            figure=_empty_figure("Spatial allocation will load automatically."),
                            config={"displaylogo": False},
                        ),
                        html.Div("Official GB day-ahead demand context", className="chart-title"),
                        html.Div("National Demand Forecast is official NESO data served through Elexon Insights. It provides system-scale context; the virtual portfolio is not claimed to be a physical national battery.", className="chart-subtitle"),
                        dcc.Graph(id="grid-demand-chart", figure=_empty_figure("GB demand context will load automatically."), config={"displaylogo": False}),
                    ],
                    className="download-section",
                ),
                html.Section(
                    [
                        html.H2("Renewable-only continuous-SOC stress test"),
                        html.P(
                            "This intentionally harsh stress test prohibits grid SOC restoration. SOC carries across all 450 days and is never reset at midnight. It explains why a renewable-only strategy can require very long energy duration. The fixed comparison uses a 100 MW virtual portfolio, 25 MW / 50 MWh battery, 90% round-trip efficiency and no grid charging.",
                            className="section-copy",
                        ),
                        *_long_run_benchmark_content(),
                        html.P(
                            "Use the Future battery sizing benchmark above for the practical MW/MWh design. This renewable-only result is retained as a boundary/stress case, while the selected-day controls remain diagnostic only.",
                            className="section-copy",
                        ),
                    ],
                    className="download-section",
                ),
                html.Section(
                    [
                        html.H2("Export and inspect"),
                        html.P(
                            "Download the half-hourly scenario so every charge, discharge, SOC and residual-error calculation can be checked outside the website.",
                            className="section-copy",
                        ),
                        html.Button("Download scenario CSV", id="download-button", n_clicks=0, className="secondary-button"),
                    ],
                    className="download-section",
                ),
                html.Section(
                    [
                        html.H2("Interpretation and limits"),
                        html.P(
                            "This is a virtual portfolio-level firming benchmark. It scales national wind and solar capacity-factor evidence to a user-defined portfolio; it is not a site-specific battery design, a physical national battery, a trading model or investment advice. The reactive strategy uses the current observed deviation but no future settlement-period knowledge.",
                            className="section-copy",
                        ),
                        html.P(
                            "The full 450-day out-of-sample archive supports historical analysis, while Tomorrow planning consumes the latest V2 forecast bundle and official grid-demand context. A later upgrade will replace the residual-based future range with dedicated P10/P50/P90 or weather-ensemble probabilistic forecasts.",
                            className="section-copy",
                        ),
                    ],
                    className="limits-section",
                ),
            ]
        ),
        html.Footer("Standalone analytical prototype · source data exchanged through a versioned file contract"),
    ],
    className="app-shell",
)


@app.callback(
    Output("initial-energy-note", "children"),
    Input("power-input", "value"),
    Input("duration-input", "value"),
    Input("soc-input", "value"),
    Input("efficiency-input", "value"),
)
def explain_initial_energy(power_mw: float, duration_hours: float, initial_soc_pct: float, efficiency_pct: float) -> str:
    try:
        return _initial_energy_explanation(power_mw, duration_hours, initial_soc_pct, efficiency_pct)
    except (TypeError, ValueError):
        return "Enter a valid battery configuration to calculate starting stored energy."


@app.callback(
    Output("wind-share-container", "className"),
    Input("portfolio-input", "value"),
)
def show_wind_share(portfolio_type: str) -> str:
    return "control-visible" if portfolio_type == "mixed" else "control-muted"


@app.callback(
    Output("spatial-zone-note", "children"),
    Output("spatial-zone-kpi-grid", "children"),
    Output("spatial-zone-chart", "figure"),
    Input("spatial-zone-input", "value"),
    Input("portfolio-input", "value"),
    Input("capacity-input", "value"),
    Input("wind-share-input", "value"),
    Input("design-target-input", "value"),
    Input("design-reliability-input", "value"),
)
def update_spatial_zone(
    zone, portfolio_type, capacity_mw, wind_share_pct,
    design_target_pct, design_reliability_pct,
):
    try:
        return _spatial_zone_view(
            zone, portfolio_type, capacity_mw, wind_share_pct,
            design_target_pct, design_reliability_pct,
        )
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        message = f"Spatial zone allocation could not be calculated: {error}"
        return message, [], _empty_figure(message)


@app.callback(
    Output("design-note", "children"),
    Output("design-kpi-grid", "children"),
    Output("design-heatmap", "figure"),
    Input("portfolio-input", "value"),
    Input("capacity-input", "value"),
    Input("wind-share-input", "value"),
    Input("design-target-input", "value"),
    Input("design-reliability-input", "value"),
)
def update_future_design(
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    target_pct: float,
    reliability_pct: float,
):
    try:
        grid = scaled_design_grid(
            DESIGN_GRID, portfolio_type, float(capacity_mw), float(wind_share_pct)
        )
        cards, note, selected = _design_cards_and_note(grid, target_pct, reliability_pct)
        figure = _design_heatmap(grid, target_pct, reliability_pct, selected)
        return note, cards, figure
    except (TypeError, ValueError, KeyError) as error:
        message = f"Future battery sizing could not be calculated: {error}"
        return message, [], _empty_figure(message)


@app.callback(
    Output("risk-value-note", "children"),
    Output("risk-value-kpi-grid", "children"),
    Output("risk-value-frontier", "figure"),
    Output("risk-value-sensitivity", "figure"),
    Input("portfolio-input", "value"),
    Input("capacity-input", "value"),
    Input("wind-share-input", "value"),
    Input("design-target-input", "value"),
    Input("design-reliability-input", "value"),
    Input("risk-consequence-input", "value"),
    Input("risk-capex-input", "value"),
    Input("risk-fixed-opex-input", "value"),
    Input("risk-variable-opex-input", "value"),
    Input("risk-life-input", "value"),
    Input("risk-discount-input", "value"),
    Input("risk-degradation-input", "value"),
    Input("risk-availability-input", "value"),
)
def update_risk_value(
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
    consequence_value: float,
    reference_capex_million: float,
    fixed_opex_million_per_year: float,
    variable_opex_per_mwh: float,
    asset_life_years: int,
    discount_rate_pct: float,
    degradation_pct: float,
    availability_pct: float,
):
    try:
        frontier, selected, row, break_even, max_capex = _risk_value_analysis(
            portfolio_type, capacity_mw, wind_share_pct,
            design_target_pct, design_reliability_pct,
            consequence_value, reference_capex_million,
            fixed_opex_million_per_year, variable_opex_per_mwh,
            asset_life_years, discount_rate_pct, degradation_pct, availability_pct,
        )
    except (TypeError, ValueError, KeyError) as error:
        message = f"Risk-value appraisal could not be calculated: {error}"
        return message, [], _empty_figure(message), _empty_figure(message)

    payback = row["simple_payback_years"]
    payback_text = "Not within life" if pd.isna(payback) else f"{int(payback)} years"
    break_even_text = "N/A" if break_even is None else f"£{break_even:.0f}/MWh"
    cards = [
        _kpi_card(
            "Selected design",
            f"{selected['power_mw']:.0f} MW / {selected['energy_mwh']:.0f} MWh",
            f"Stage A {design_target_pct:.0f}% / {design_reliability_pct:.0f}% gate",
        ),
        _kpi_card(
            "Annual avoided exposure",
            f"{row['annual_avoided_exposure_mwh']:,.0f} MWh/yr",
            "Annualised from the 450-day physical backtest",
        ),
        _kpi_card(
            "Annual risk reduction",
            f"£{row['annual_avoided_exposure_mwh'] * float(consequence_value) / 1e6:.2f}m/yr",
            f"Using scenario consequence value £{float(consequence_value):,.0f}/MWh",
        ),
        _kpi_card(
            "NPV",
            f"£{row['npv_gbp'] / 1e6:.2f}m",
            f"{int(asset_life_years)}-year discounted pre-feasibility value",
        ),
        _kpi_card("Benefit-cost ratio", f"{row['benefit_cost_ratio']:.2f}", "PV avoided loss / PV lifecycle cost"),
        _kpi_card("Simple payback", payback_text, "Undiscounted net benefit recovery"),
        _kpi_card("Break-even consequence", break_even_text, "£/MWh required for NPV = 0"),
        _kpi_card("Max CAPEX at NPV = 0", f"£{max_capex / 1e6:.2f}m", "Switching value under current assumptions"),
        _kpi_card("Expected availability", f"{float(availability_pct):.0f}%", "Stage 6A expected-availability scaling assumption"),
    ]
    status = str(row["frontier_status"])
    if bool(row["diminishing_return"]):
        decision = "The selected technical design lies on the efficient set but its incremental avoided-loss value is below the incremental lifecycle cost versus the next cheaper efficient option."
    elif status == "dominated":
        decision = "Under these assumptions, at least one tested battery configuration costs no more while avoiding at least as much expected loss, so the selected technical design is economically dominated."
    else:
        decision = "Under these assumptions, the selected Stage A technical design is not economically dominated by another tested configuration."
    note = html.Div([
        html.Strong(decision),
        html.P(
            "Monetary results are scenario-based screening outputs. The consequence value is user supplied, and candidate CAPEX/fixed OPEX are scaled from the selected design in proportion to MWh. The frontier includes all tested configurations, including some that do not meet the selected Stage A firming gate, so economic efficiency alone does not make a design technically acceptable. No actual market-revenue claim is made."
        ),
    ])
    figure = _risk_value_frontier_figure(
        frontier, float(selected["power_mw"]), float(selected["duration_hours"])
    )
    sensitivity_assumptions = ValueAssumptions(
        consequence_value_gbp_per_mwh=float(consequence_value),
        total_capex_gbp=float(reference_capex_million) * 1e6,
        fixed_opex_gbp_per_year=float(fixed_opex_million_per_year) * 1e6,
        variable_opex_gbp_per_mwh=float(variable_opex_per_mwh),
        asset_life_years=int(asset_life_years),
        discount_rate=float(discount_rate_pct) / 100.0,
        annual_degradation_fraction=float(degradation_pct) / 100.0,
    )
    sensitivity = _risk_value_sensitivity_figure(
        float(row["annual_avoided_exposure_mwh"]),
        float(row["annual_throughput_mwh"]),
        sensitivity_assumptions,
    )
    return note, cards, figure, sensitivity


@app.callback(
    Output("risk-value-download", "data"),
    Input("risk-value-download-button", "n_clicks"),
    State("portfolio-input", "value"), State("capacity-input", "value"), State("wind-share-input", "value"),
    State("design-target-input", "value"), State("design-reliability-input", "value"),
    State("risk-consequence-input", "value"), State("risk-capex-input", "value"),
    State("risk-fixed-opex-input", "value"), State("risk-variable-opex-input", "value"),
    State("risk-life-input", "value"), State("risk-discount-input", "value"),
    State("risk-degradation-input", "value"), State("risk-availability-input", "value"),
    prevent_initial_call=True,
)
def download_risk_value_scenario(
    _clicks, portfolio_type, capacity_mw, wind_share_pct, design_target_pct,
    design_reliability_pct, consequence_value, reference_capex_million,
    fixed_opex_million_per_year, variable_opex_per_mwh, asset_life_years,
    discount_rate_pct, degradation_pct, availability_pct,
):
    frontier, selected, row, break_even, max_capex = _risk_value_analysis(
        portfolio_type, capacity_mw, wind_share_pct, design_target_pct,
        design_reliability_pct, consequence_value, reference_capex_million,
        fixed_opex_million_per_year, variable_opex_per_mwh, asset_life_years,
        discount_rate_pct, degradation_pct, availability_pct,
    )
    payload = {
        "schema_version": "1.0",
        "stage": "6A_risk_value_pre_feasibility",
        "portfolio": {"type": portfolio_type, "capacity_mw": float(capacity_mw), "wind_share_pct": float(wind_share_pct)},
        "design_gate": {"firming_target_pct": float(design_target_pct), "reliability_pct": float(design_reliability_pct)},
        "selected_design": {"power_mw": float(selected["power_mw"]), "duration_hours": float(selected["duration_hours"]), "energy_mwh": float(selected["energy_mwh"])},
        "assumptions": {
            "consequence_value_gbp_per_mwh": float(consequence_value), "selected_design_capex_gbp": float(reference_capex_million) * 1e6,
            "selected_design_fixed_opex_gbp_per_year": float(fixed_opex_million_per_year) * 1e6, "variable_opex_gbp_per_mwh_throughput": float(variable_opex_per_mwh),
            "asset_life_years": int(asset_life_years), "discount_rate_pct": float(discount_rate_pct), "annual_degradation_pct": float(degradation_pct),
            "expected_availability_pct": float(availability_pct), "candidate_cost_scaling": "CAPEX and fixed OPEX proportional to MWh relative to selected design",
        },
        "selected_results": {key: (None if pd.isna(row[key]) else float(row[key])) for key in ["annual_avoided_exposure_mwh", "annual_throughput_mwh", "pv_avoided_loss_gbp", "lifecycle_cost_gbp", "npv_gbp", "benefit_cost_ratio"]},
        "switching_values": {"break_even_consequence_value_gbp_per_mwh": break_even, "maximum_capex_for_zero_npv_gbp": max_capex},
        "frontier": frontier.to_dict(orient="records"),
        "limitations": ["scenario assumptions, not observed market prices", "pre-feasibility screening, not bankable valuation", "economic efficiency does not override the selected technical firming gate"],
    }
    return dcc.send_string(json.dumps(payload, indent=2), "risk_value_scenario.json")


@app.callback(
    Output("downside-risk-note", "children"),
    Output("downside-risk-kpi-grid", "children"),
    Output("downside-risk-chart", "figure"),
    Output("downside-stress-chart", "figure"),
    Output("downside-risk-store", "data"),
    Input("downside-risk-button", "n_clicks"),
    State("portfolio-input", "value"), State("capacity-input", "value"),
    State("wind-share-input", "value"), State("design-target-input", "value"),
    State("design-reliability-input", "value"), State("risk-consequence-input", "value"),
    State("risk-capex-input", "value"), State("risk-fixed-opex-input", "value"),
    State("risk-variable-opex-input", "value"), State("risk-life-input", "value"),
    State("risk-discount-input", "value"), State("risk-degradation-input", "value"),
    State("risk-availability-input", "value"), State("downside-simulations-input", "value"),
    State("downside-block-input", "value"), State("downside-seed-input", "value"),
    prevent_initial_call=True,
)
def run_downside_risk(
    _clicks, portfolio_type, capacity_mw, wind_share_pct, design_target_pct,
    design_reliability_pct, consequence_value, reference_capex_million,
    fixed_opex_million_per_year, variable_opex_per_mwh, asset_life_years,
    discount_rate_pct, degradation_pct, availability_pct, simulations,
    block_days, seed,
):
    try:
        draws, summary, stress, selected, distributions = _downside_risk_analysis(
            portfolio_type, capacity_mw, wind_share_pct, design_target_pct,
            design_reliability_pct, consequence_value, reference_capex_million,
            fixed_opex_million_per_year, variable_opex_per_mwh, asset_life_years,
            discount_rate_pct, degradation_pct, availability_pct, simulations,
            block_days, seed,
        )
    except (TypeError, ValueError, KeyError) as error:
        message = f"Downside-risk analysis could not be calculated: {error}"
        return message, [], _empty_figure(message), _empty_figure(message), None

    cards = [
        _kpi_card("P10 NPV", f"£{summary['npv_p10_gbp']/1e6:.2f}m", "Lower NPV quantile"),
        _kpi_card("P50 NPV", f"£{summary['npv_p50_gbp']/1e6:.2f}m", "Median simulated NPV"),
        _kpi_card("P90 NPV", f"£{summary['npv_p90_gbp']/1e6:.2f}m", "Upper NPV quantile"),
        _kpi_card("Probability NPV < 0", f"{summary['probability_negative_npv_pct']:.1f}%", "Share of simulations with negative NPV"),
        _kpi_card("95% CVaR loss", f"£{summary['cvar_expected_shortfall_gbp']/1e6:.2f}m", "Average investment loss in worst 5% tail"),
        _kpi_card(
            "Fail design gate",
            f"{summary['probability_failing_firming_gate_pct']:.1f}%",
            f"Bootstrap years failing {design_target_pct:.0f}% firming on {design_reliability_pct:.0f}% of days",
        ),
    ]
    note = html.Div([
        html.Div(
            f"Selected design: {selected['power_mw']:.0f} MW / {selected['energy_mwh']:.0f} MWh ({selected['duration_hours']:.0f} h). "
            f"The analysis resamples {int(summary['sample_days'])}-day years in {int(summary['block_days'])}-day contiguous historical blocks using seed {int(summary['seed'])}.",
            className="scenario-note-line",
        ),
        html.Div(
            "Scenario multipliers are triangular and independently sampled across consequence value, CAPEX, OPEX, availability and degradation. "
            "Chronological forecast-error dependence is retained within the sampled day blocks. Conditional on the sampled availability fraction, daily outage states are independently drawn; cross-parameter correlations are not modelled.",
            className="scenario-note-line uncertainty-line",
        ),
        html.Div(
            "Loss convention: investment loss = -NPV. These are pre-feasibility uncertainty results based on transparent assumptions, not calibrated market distributions or a bankable valuation.",
            className="scenario-note-line",
        ),
    ])
    payload = {
        "schema_version": "1.0",
        "stage": "6B_quantitative_downside_risk",
        "selected_design": {
            "power_mw": float(selected["power_mw"]),
            "duration_hours": float(selected["duration_hours"]),
            "energy_mwh": float(selected["energy_mwh"]),
        },
        "summary": summary,
        "distributions": distributions,
        "stress_scenarios": stress.to_dict(orient="records"),
        "simulation_settings": {
            "simulations": int(simulations), "block_days": int(block_days), "seed": int(seed),
        },
    }
    return note, cards, _npv_distribution_figure(draws, summary), _stress_scenario_figure(stress), payload


@app.callback(
    Output("downside-risk-download", "data"),
    Input("downside-risk-download-button", "n_clicks"),
    State("downside-risk-store", "data"),
    prevent_initial_call=True,
)
def download_downside_risk(_clicks, payload):
    if not payload:
        return no_update
    return dcc.send_string(
        json.dumps(payload, indent=2), "downside_risk_summary.json"
    )


@app.callback(
    Output("generation-chart", "figure"),
    Output("battery-chart", "figure"),
    Output("kpi-grid", "children"),
    Output("scenario-note", "children"),
    Output("scenario-store", "data"),
    Input("run-button", "n_clicks"),
    State("date-input", "value"),
    State("portfolio-input", "value"),
    State("capacity-input", "value"),
    State("wind-share-input", "value"),
    State("power-input", "value"),
    State("duration-input", "value"),
    State("soc-input", "value"),
    State("efficiency-input", "value"),
)
def run_scenario(
    _clicks: int,
    date_value: str,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    battery_power_mw: float,
    duration_hours: float,
    initial_soc_pct: float,
    efficiency_pct: float,
):
    try:
        simulation, config, metrics, uncertainty = _scenario(
            date_value,
            portfolio_type,
            capacity_mw,
            wind_share_pct,
            battery_power_mw,
            duration_hours,
            initial_soc_pct,
            efficiency_pct,
        )
    except (TypeError, ValueError, KeyError) as error:
        message = f"Scenario could not be calculated: {error}"
        return _empty_figure(message), _empty_figure(message), [], message, None

    portfolio_label = portfolio_type.title()
    if portfolio_type == "mixed":
        portfolio_label += f" ({wind_share_pct:.0f}% wind / {100-wind_share_pct:.0f}% solar)"
    archive_portfolio = build_virtual_portfolio(
        HISTORICAL_DATA,
        portfolio_type=portfolio_type,  # type: ignore[arg-type]
        capacity_mw=float(capacity_mw),
        wind_share=float(wind_share_pct) / 100,
    )
    archive_mae = float((archive_portfolio["actual_mw"] - archive_portfolio["forecast_mw"]).abs().mean())
    day_delta_pct = 100.0 * (metrics["mae_before_mw"] / archive_mae - 1.0) if archive_mae > 0 else 0.0
    quality = "higher" if day_delta_pct >= 0 else "lower"
    note_lines: list[Any] = [
        html.Div(
            f"{date_value} · {capacity_mw:.0f} MW {portfolio_label} · selected-day forecast MAE {metrics['mae_before_mw']:.2f} MW "
            f"({abs(day_delta_pct):.0f}% {quality} than the 450-day out-of-sample average of {archive_mae:.2f} MW).",
            className="scenario-note-line",
        ),
        html.Div(
            f"Battery: {config.power_mw:.0f} MW / {config.energy_capacity_mwh:.0f} MWh · starts with {config.initial_soc_mwh:.1f} MWh stored "
            f"({initial_soc_pct:.0f}% SOC), assumed available from prior periods.",
            className="scenario-note-line",
        ),
    ]
    if uncertainty.get("available"):
        inside_periods = int(uncertainty["period_count"]) - int(uncertainty["outside_periods"])
        note_lines.append(
            html.Div(
                f"Forecast uncertainty: nominal {uncertainty['nominal_coverage_pct']:.0f}% rolling expected range, calibrated only from the previous "
                f"{uncertainty['history_days']} out-of-sample days ({uncertainty['calibration_start']} to {uncertainty['calibration_end']}). "
                f"Average band width {uncertainty['mean_interval_width_mw']:.2f} MW; actual output fell inside the range for "
                f"{inside_periods}/{uncertainty['period_count']} periods ({uncertainty['observed_day_coverage_pct']:.0f}%).",
                className="scenario-note-line uncertainty-line",
            )
        )
        if int(uncertainty["outside_periods"]) > 0:
            note_lines.append(
                html.Div(
                    f"Actual output was outside the expected range in {uncertainty['outside_periods']} periods; those points are marked × on the chart.",
                    className="scenario-note-line uncertainty-warning",
                )
            )
    else:
        note_lines.append(
            html.Div(
                f"Forecast uncertainty band unavailable: only {uncertainty.get('history_days', 0)} prior days are available; "
                f"at least {uncertainty.get('minimum_history_days', 30)} are required.",
                className="scenario-note-line uncertainty-warning",
            )
        )
    note = html.Div(note_lines)
    store_columns = [
        "settlement_date",
        "settlement_period",
        "valid_time_utc",
        "portfolio_type",
        "portfolio_capacity_mw",
        "wind_share",
        "actual_mw",
        "forecast_mw",
        "forecast_error_mw",
        "charge_mw",
        "discharge_mw",
        "soc_start_mwh",
        "soc_end_mwh",
        "soc_fraction",
        "firmed_delivery_mw",
        "residual_error_mw",
        "conversion_loss_mwh",
        "power_limited",
        "energy_limited",
    ]
    for optional_column in (
        "prediction_interval_lower_mw",
        "prediction_interval_upper_mw",
        "actual_inside_prediction_interval",
    ):
        if optional_column in simulation.columns:
            store_columns.append(optional_column)
    stored = simulation[store_columns].to_json(orient="split", date_format="iso")
    return (
        _generation_figure(simulation),
        _battery_figure(simulation),
        _kpi_cards(metrics),
        note,
        stored,
    )


@app.callback(
    Output("imbalance-note", "children"),
    Output("imbalance-kpi-grid", "children"),
    Output("imbalance-chart", "figure"),
    Input("scenario-store", "data"),
    State("date-input", "value"),
)
def update_imbalance_settlement(stored: str | None, date_value: str):
    if not stored:
        message = "Run a historical scenario above to calculate BSC-style imbalance settlement."
        return message, [], _empty_figure(message)
    try:
        simulation = pd.read_json(StringIO(stored), orient="split")
        simulation["valid_time_utc"] = pd.to_datetime(simulation["valid_time_utc"], utc=True)
        prices = select_system_prices(SYSTEM_PRICES, date_value)
        settled = apply_imbalance_settlement(simulation, prices)
        summary = summarise_imbalance_settlement(settled)
    except (TypeError, ValueError, KeyError) as error:
        message = f"Imbalance settlement could not be calculated: {error}"
        return message, [], _empty_figure(message)

    def cashflow(value: float) -> str:
        sign = "+" if value >= 0 else "−"
        return f"{sign}£{abs(value):,.0f}"

    cards = [
        _kpi_card("Gross cash-out exposure", f"£{summary['gross_exposure_before_gbp']:,.0f}", "Absolute BSC-style imbalance cashflow before battery"),
        _kpi_card("After battery", f"£{summary['gross_exposure_after_gbp']:,.0f}", "Absolute residual cash-out exposure"),
        _kpi_card("Exposure reduction", f"{summary['gross_exposure_reduction_pct']:.1f}%", "Reduction in absolute cash-out exposure; not the same as profit"),
        _kpi_card("Signed cashflow before", cashflow(summary['signed_cashflow_before_gbp']), "Positive = payment by portfolio; negative = receipt to portfolio"),
        _kpi_card("Signed cashflow after", cashflow(summary['signed_cashflow_after_gbp']), "Same Elexon sign convention after battery firming"),
        _kpi_card("System Price range", f"£{summary['min_system_price_gbp_per_mwh']:.0f}–£{summary['max_system_price_gbp_per_mwh']:.0f}/MWh", "Official Elexon single imbalance price on this day"),
    ]
    note = html.Div([
        html.Div(
            f"GB system state: short in {summary['system_short_periods']} periods and long in {summary['system_long_periods']} periods. "
            f"Before battery, the portfolio deviation was directionally supportive of the system in {summary['direction_helpful_before_periods']}/{summary['period_count']} periods.",
            className="scenario-note-line",
        ),
        html.Div(
            "Interpretation: the point forecast is only an illustrative contracted schedule. Gross cash-out exposure measures settlement-risk magnitude. "
            "It is not profit, avoided cost, or a trading recommendation because we have not yet included the contracted/day-ahead reference price.",
            className="scenario-note-line uncertainty-warning",
        ),
    ])
    return note, cards, _imbalance_figure(settled)


@app.callback(
    Output("quick-reserve-note", "children"),
    Output("quick-reserve-kpi-grid", "children"),
    Output("quick-reserve-chart", "figure"),
    Input("quick-reserve-button", "n_clicks"),
    State("date-input", "value"),
    State("portfolio-input", "value"),
    State("capacity-input", "value"),
    State("wind-share-input", "value"),
    State("design-target-input", "value"),
    State("design-reliability-input", "value"),
    State("market-throughput-cost-input", "value"),
    State("quick-reserve-guard-input", "value"),
)
def run_quick_reserve_stacking(
    _clicks: int,
    date_value: str,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
    throughput_cost: float,
    guard_windows: int,
):
    try:
        analysis = _quick_reserve_day_analysis(
            date_value, portfolio_type, capacity_mw, wind_share_pct,
            design_target_pct, design_reliability_pct, throughput_cost, guard_windows,
        )
    except (TypeError, ValueError, KeyError, RuntimeError) as error:
        message = f"Quick Reserve stacking could not be calculated: {error}"
        return message, [], _empty_figure(message)
    selected = analysis["selected"]
    arb = analysis["arbitrage"]
    firm_arb = analysis["firm_arb"]
    qr_only = analysis["qr_only"]
    stacked = analysis["stacked"]
    triple = analysis["triple"]
    hours = len(analysis["market"]) * analysis["battery"].interval_hours
    independent_sum = float(arb["net_arbitrage_margin_gbp"]) + float(qr_only["net_stacked_value_gbp"])
    double_count = independent_sum - float(stacked["net_stacked_value_gbp"])
    triple_independent_sum = float(firm_arb["net_cooptimised_value_gbp"]) + float(qr_only["net_stacked_value_gbp"])
    triple_double_count = triple_independent_sum - float(triple["net_triple_stacked_value_gbp"])
    mean_pqr = float(triple["pqr_contracted_mw_hours"]) / hours
    mean_nqr = float(triple["nqr_contracted_mw_hours"]) / hours
    cards = [
        _kpi_card("Installed design", f"{selected['power_mw']:.0f} MW / {selected['energy_mwh']:.0f} MWh", "Stage A selected battery"),
        _kpi_card("Arbitrage-only value", f"?{arb['net_arbitrage_margin_gbp']:,.0f}", "Perfect-information APX MIP benchmark"),
        _kpi_card("Firming + arbitrage", f"?{firm_arb['net_cooptimised_value_gbp']:,.0f}", "Renewable firming plus wholesale"),
        _kpi_card("QR-only availability", f"?{qr_only['net_stacked_value_gbp']:,.0f}", "PQR + NQR availability only"),
        _kpi_card("Arbitrage + QR", f"?{stacked['net_stacked_value_gbp']:,.0f}", "Two-use shared-battery stack"),
        _kpi_card("Firming + market + QR", f"?{triple['net_triple_stacked_value_gbp']:,.0f}", "Three uses sharing one battery"),
        _kpi_card("Triple-stack firming", f"{triple['error_reduction_pct']:.1f}%", "Renewable forecast-error reduction retained"),
        _kpi_card("QR availability in triple", f"?{triple['quick_reserve_availability_payment_gbp']:,.0f}", "Utilisation revenue excluded"),
        _kpi_card("Triple independent-sum overstatement", f"?{triple_double_count:,.0f}", "Double-count avoided by shared-battery optimisation"),
        _kpi_card("Mean PQR / NQR", f"{mean_pqr:.1f} / {mean_nqr:.1f} MW", "Positive / negative reserve commitment"),
    ]
    default_reference = (
        portfolio_type == "mixed"
        and abs(float(capacity_mw) - 100.0) < 1e-9
        and abs(float(wind_share_pct) - 50.0) < 1e-9
        and abs(float(design_target_pct) - 90.0) < 1e-9
        and abs(float(design_reliability_pct) - 90.0) < 1e-9
        and abs(float(throughput_cost) - 2.0) < 1e-9
    )
    note_lines = [
        html.Div(
            "Quick Reserve value shown here is availability only. Utilisation revenue and activation energy are excluded, and the asset is treated as a price taker accepted at the observed EAC clearing price.",
            className="scenario-note-line uncertainty-warning",
        ),
        html.Div(
            f"The {int(guard_windows)}-window guard requires enough stored-energy/headroom to sustain consecutive 30-minute QR windows while the wholesale schedule and PQR/NQR commitments share one physical battery.",
            className="scenario-note-line",
        ),
        html.Div(
            "This is not proof of NESO prequalification, auction acceptance, telemetry compliance or actual earned revenue.",
            className="scenario-note-line uncertainty-line",
        ),
    ]
    if default_reference:
        ref = QUICK_RESERVE_SUMMARY["guard_sensitivity"][str(int(guard_windows))]
        note_lines.append(html.Div(
            f"Frozen Apr?Jun 2026 default reference: full firming + arbitrage + QR ?{ref['triple_stacked_annualised_gbp']/1e6:.2f}m/yr versus firming + arbitrage ?{ref['firming_arbitrage_annualised_gbp']/1e6:.2f}m/yr. The na?ve independent sum overstates triple-stack value by about ?{ref['triple_double_count_avoided_annualised_gbp']/1e6:.2f}m/yr, while mean renewable-error reduction remains {ref['mean_triple_error_reduction_pct']:.1f}%. This annualisation describes that 90-day regime only.",
            className="scenario-note-line",
        ))
    return html.Div(note_lines), cards, _quick_reserve_figure(analysis)


@app.callback(
    Output("quick-reserve-predelivery-note", "children"),
    Output("quick-reserve-predelivery-kpi-grid", "children"),
    Output("quick-reserve-predelivery-chart", "figure"),
    Input("date-input", "value"),
)
def update_quick_reserve_predelivery(date_value: str):
    try:
        return _quick_reserve_predelivery_view(date_value)
    except (TypeError, ValueError, KeyError) as error:
        message = f"Pre-delivery Quick Reserve evidence could not be calculated: {error}"
        return message, [], _empty_figure(message)


@app.callback(
    Output("pre-delivery-note", "children"),
    Output("pre-delivery-kpi-grid", "children"),
    Output("pre-delivery-price-chart", "figure"),
    Input("date-input", "value"),
)
def update_pre_delivery_strategy(date_value: str):
    try:
        return _pre_delivery_strategy_view(date_value)
    except (TypeError, ValueError, KeyError) as error:
        message = f"Pre-delivery strategy evidence could not be calculated: {error}"
        return message, [], _empty_figure(message)


@app.callback(
    Output("market-optimisation-note", "children"),
    Output("market-optimisation-kpi-grid", "children"),
    Output("market-optimisation-chart", "figure"),
    Input("market-optimisation-button", "n_clicks"),
    State("date-input", "value"),
    State("portfolio-input", "value"),
    State("capacity-input", "value"),
    State("wind-share-input", "value"),
    State("design-target-input", "value"),
    State("design-reliability-input", "value"),
    State("market-throughput-cost-input", "value"),
)
def run_market_optimisation(
    _clicks: int,
    date_value: str,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
    throughput_cost: float,
):
    try:
        analysis = _market_day_analysis(
            date_value, portfolio_type, capacity_mw, wind_share_pct,
            design_target_pct, design_reliability_pct, throughput_cost,
        )
    except (TypeError, ValueError, KeyError, RuntimeError) as error:
        message = f"Market optimisation could not be calculated: {error}"
        return message, [], _empty_figure(message)
    selected = analysis["selected"]
    settlement_aware = analysis["settlement_aware"]
    reactive = analysis["reactive"]
    arbitrage = analysis["arbitrage"]
    coopt = analysis["coopt"]
    cards = [
        _kpi_card(
            "Installed design",
            f"{selected['power_mw']:.0f} MW / {selected['energy_mwh']:.0f} MWh",
            "Selected by the current Stage A technical design gate",
        ),
        _kpi_card(
            "APX market VWAP",
            f"£{analysis['restoration_price']:.2f}/MWh",
            "Open Elexon short-term wholesale reference; not day-ahead auction price",
        ),
        _kpi_card(
            "Settlement-aware value",
            f"£{settlement_aware['net_settlement_value_improvement_gbp']:,.0f}",
            "Selected-day improvement after SOC restoration and throughput cost",
        ),
        _kpi_card(
            "Wholesale arbitrage",
            f"£{arbitrage['net_arbitrage_margin_gbp']:,.0f}",
            "Perfect-foresight Market Index arbitrage with terminal SOC restored",
        ),
        _kpi_card(
            "Co-optimised value",
            f"£{coopt['net_cooptimised_value_gbp']:,.0f}",
            "Shared MW/SOC allocated jointly between firming and wholesale arbitrage",
        ),
        _kpi_card(
            "Co-opt error reduction",
            f"{coopt['error_reduction_pct']:.1f}%",
            "Forecast-error energy still absorbed after financial co-optimisation",
        ),
        _kpi_card(
            "Reactive firming value",
            f"£{reactive['net_value_improvement_gbp']:,.0f}",
            f"Error-minimising strategy absorbs {reactive['error_reduction_pct']:.1f}% on this day",
        ),
        _kpi_card(
            "Settlement-aware error reduction",
            f"{settlement_aware['error_reduction_pct']:.1f}%",
            "Lower physical firming can be financially preferable",
        ),
    ]
    annual_coopt = float(MARKET_BACKTEST.get("cooptimised_annualised_net_value_gbp", 0.0))
    annual_arb = float(MARKET_BACKTEST.get("arbitrage_annualised_net_margin_gbp", 0.0))
    annual_settlement = float(MARKET_BACKTEST.get("market_aware_annualised_net_value_improvement_gbp", 0.0))
    annual_reactive = float(MARKET_BACKTEST.get("reactive_annualised_net_value_improvement_gbp", 0.0))
    note = html.Div([
        html.Div(
            f"Historical target {date_value}. This is an ex-post perfect-information benchmark: realised renewable error, System Price and Market Index Price are all known to the optimiser. It is an upper-bound diagnostic, not an executable day-ahead trading instruction.",
            className="scenario-note-line uncertainty-warning",
        ),
        html.Div(
            f"Frozen 450-day default reference at £{MARKET_BACKTEST['throughput_cost_gbp_per_mwh']:.0f}/MWh throughput cost: co-optimised value £{annual_coopt/1e6:.2f}m/year; wholesale-arbitrage-only £{annual_arb/1e6:.2f}m/year; settlement-aware firming £{annual_settlement/1e6:.2f}m/year; error-minimising reactive firming £{annual_reactive/1e6:.2f}m/year.",
            className="scenario-note-line",
        ),
        html.Div(
            "The co-optimiser does not add separate revenue streams independently: firming and arbitrage share one physical battery power limit, SOC trajectory and throughput budget. A licensed day-ahead auction feed can later replace or complement the Market Index reference through the prepared data contract.",
            className="scenario-note-line",
        ),
    ])
    return note, cards, _market_optimisation_figure(analysis)

@app.callback(
    Output("forecast-market-note", "children"),
    Output("forecast-market-kpi-grid", "children"),
    Output("forecast-market-chart", "figure"),
    Input("portfolio-input", "value"), Input("capacity-input", "value"),
    Input("wind-share-input", "value"), Input("design-target-input", "value"),
    Input("design-reliability-input", "value"), Input("tomorrow-soc-input", "value"),
    Input("market-throughput-cost-input", "value"),
)
def update_forecast_market_schedule(
    portfolio_type, capacity_mw, wind_share_pct, design_target_pct,
    design_reliability_pct, current_soc_pct, throughput_cost,
):
    try:
        return _forecast_day_market_schedule(
            portfolio_type, capacity_mw, wind_share_pct,
            design_target_pct, design_reliability_pct, current_soc_pct, throughput_cost,
        )
    except (TypeError, ValueError, KeyError) as error:
        message = f"Forecast-day market schedule could not be calculated: {error}"
        return message, [], _empty_figure(message)


@app.callback(
    Output("tomorrow-note", "children"),
    Output("tomorrow-kpi-grid", "children"),
    Output("tomorrow-forecast-chart", "figure"),
    Output("tomorrow-reserve-chart", "figure"),
    Output("grid-demand-chart", "figure"),
    Input("tomorrow-button", "n_clicks"),
    State("portfolio-input", "value"),
    State("capacity-input", "value"),
    State("wind-share-input", "value"),
    State("design-target-input", "value"),
    State("design-reliability-input", "value"),
    State("tomorrow-soc-input", "value"),
)
def run_tomorrow_planning(
    _clicks: int,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    design_target_pct: float,
    design_reliability_pct: float,
    current_soc_pct: float,
):
    try:
        design_grid = scaled_design_grid(
            DESIGN_GRID, portfolio_type, float(capacity_mw), float(wind_share_pct)
        )
        selected_design = select_stable_design(
            design_grid, design_target_pct, design_reliability_pct
        )
        if selected_design is None:
            raise ValueError("No stable future design exists for the selected target/reliability gate.")
        forecast, config, planning = _tomorrow_planning_data(
            portfolio_type, capacity_mw, wind_share_pct,
            selected_design["power_mw"], selected_design["duration_hours"],
            current_soc_pct, 90.0,
        )
    except (TypeError, ValueError, KeyError) as error:
        message = f"Forecast-day planning could not be calculated: {error}"
        empty = _empty_figure(message)
        return message, [], empty, empty, empty

    uncertainty = planning["uncertainty"]
    reserve = planning.get("reserve")
    cards = [
        _kpi_card(
            "Installed design",
            f"{selected_design['power_mw']:.0f} MW / {selected_design['energy_mwh']:.0f} MWh",
            f"Selected by the {design_target_pct:.0f}% firming / {design_reliability_pct:.0f}% days design gate",
        ),
        _kpi_card("Current SOC", f"{float(current_soc_pct):.0f}%", "Operator-entered SOC before the forecast day"),
        _kpi_card("Forecast energy", f"{planning['forecast_energy_mwh']:.1f} MWh", "V2 scheduled renewable export"),
        _kpi_card("Peak forecast", f"{planning['peak_forecast_mw']:.1f} MW", "Highest scheduled renewable export"),
    ]

    if reserve:
        recommended = float(reserve["recommended_start_soc_pct"])
        if reserve["energy_band_feasible"]:
            safe_band = f"{reserve['safe_soc_lower_pct']:.1f}–{reserve['safe_soc_upper_pct']:.1f}%"
        else:
            safe_band = "No full safe band"
        if reserve["preparation_action"] == "hold current SOC":
            prep_value = f"Hold {recommended:.0f}%"
            prep_help = "Current SOC already lies inside the safe reserve band"
        elif reserve["preparation_action"] == "charge before target day":
            prep_value = f"Charge +{reserve['grid_import_to_recommendation_mwh']:.1f} MWh"
            prep_help = f"Move to {recommended:.1f}% SOC before the forecast day"
        else:
            prep_value = f"Export {reserve['grid_export_to_recommendation_mwh']:.1f} MWh"
            prep_help = f"Reduce to {recommended:.1f}% SOC before the forecast day"
        cards.extend([
            _kpi_card("Recommended start SOC", f"{recommended:.1f}%", "Minimum adjustment needed for reserve sufficiency"),
            _kpi_card("Safe SOC band", safe_band, f"Based on a {reserve['reserve_horizon_hours']:.0f} h rolling reserve window"),
            _kpi_card("Preparation", prep_value, prep_help),
            _kpi_card("Reserve coverage", f"{reserve['overall_reserve_coverage_pct']:.0f}%", "Minimum of energy and MW coverage for both directions"),
            _kpi_card("Downward reserve need", f"{reserve['downward_reserve_required_mwh']:.1f} MWh", "Largest rolling discharge-energy requirement"),
            _kpi_card("Upward headroom need", f"{reserve['upward_headroom_required_mwh']:.1f} MWh", "Largest rolling renewable-surplus absorption requirement"),
        ])

    forecast_figure = _tomorrow_forecast_figure(forecast)
    reserve_figure = (
        _reserve_plan_figure(forecast, reserve)
        if reserve else _empty_figure("Directional reserve evidence is unavailable.")
    )
    issue = pd.Timestamp(LATEST_FORECAST["forecast_created_utc"].iloc[0]).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    note_parts: list[Any] = [
        html.Div(
            f"Future design in use: {selected_design['power_mw']:.0f} MW / {selected_design['energy_mwh']:.0f} MWh "
            f"({selected_design['duration_hours']:.0f} h), selected by the {design_target_pct:.0f}% firming / "
            f"{design_reliability_pct:.0f}% days stability gate.",
            className="scenario-note-line",
        ),
    ]
    if reserve:
        if reserve["energy_band_feasible"]:
            action_text = (
                f"Operational recommendation: {reserve['preparation_action']}. Current SOC {reserve['current_soc_pct']:.0f}% → "
                f"recommended {reserve['recommended_start_soc_pct']:.1f}%. The safe starting-SOC band is "
                f"{reserve['safe_soc_lower_pct']:.1f}–{reserve['safe_soc_upper_pct']:.1f}% for a "
                f"{reserve['reserve_horizon_hours']:.0f} h rolling reserve horizon."
            )
        else:
            action_text = (
                f"No starting SOC can fully cover both directional energy requirements over the "
                f"{reserve['reserve_horizon_hours']:.0f} h horizon. The planner therefore holds the current "
                f"{reserve['current_soc_pct']:.0f}% SOC and reports {reserve['overall_reserve_coverage_pct']:.0f}% reserve coverage instead of forcing an unvalidated SOC shift."
            )
        note_parts.append(html.Div(action_text, className="scenario-note-line uncertainty-line"))

        down_start = pd.Timestamp(reserve["critical_down_start_utc"]).strftime("%d %b %H:%M")
        down_end = pd.Timestamp(reserve["critical_down_end_utc"]).strftime("%d %b %H:%M")
        up_start = pd.Timestamp(reserve["critical_up_start_utc"]).strftime("%d %b %H:%M")
        up_end = pd.Timestamp(reserve["critical_up_end_utc"]).strftime("%d %b %H:%M")
        note_parts.append(html.Div(
            f"Critical downside window: {down_start}–{down_end} UTC, requiring {reserve['downward_reserve_required_mwh']:.1f} MWh discharge reserve. "
            f"Critical upside window: {up_start}–{up_end} UTC, requiring {reserve['upward_headroom_required_mwh']:.1f} MWh charging headroom. "
            f"Peak directional MW needs are {reserve['peak_downward_reserve_mw']:.1f} MW down and {reserve['peak_upward_headroom_mw']:.1f} MW up.",
            className="scenario-note-line",
        ))

    note_parts.append(html.Div(
        f"Renewable forecast target {LATEST_TARGET_DATE}; V2 bundle created {issue}. This is reserve planning only: no actual future generation or dispatch path is assumed.",
        className="scenario-note-line",
    ))
    if uncertainty.get("available"):
        note_parts.append(html.Div(
            f"Directional uncertainty range: empirical q{uncertainty['lower_quantile_pct']:.0f}–q{uncertainty['upper_quantile_pct']:.0f} residual bounds "
            f"calibrated from {uncertainty['history_days']} earlier out-of-sample days "
            f"({uncertainty['calibration_start']} to {uncertainty['calibration_end']}); mean width "
            f"{uncertainty['mean_interval_width_mw']:.2f} MW. This is not yet a weather-ensemble probabilistic forecast.",
            className="scenario-note-line uncertainty-line",
        ))
    else:
        note_parts.append(html.Div(
            "Directional uncertainty is unavailable because the verified historical archive does not contain enough prior calibration days.",
            className="scenario-note-line uncertainty-warning",
        ))

    try:
        grid = fetch_day_ahead_demand(LATEST_TARGET_DATE)
        grid_figure = _grid_demand_figure(grid)
        merged = forecast[["settlement_period", "forecast_mw"]].merge(
            grid[["settlement_period", "national_demand_mw"]],
            on="settlement_period", validate="one_to_one",
        )
        max_share = float(
            (100.0 * merged["forecast_mw"] / merged["national_demand_mw"]).max()
        )
        publish = grid["publish_time_utc"].max().strftime("%Y-%m-%d %H:%M UTC")
        context_status = str(grid["grid_context_status"].iloc[0]) if "grid_context_status" in grid else "complete_day"
        period_count = int(grid["grid_context_period_count"].iloc[0]) if "grid_context_period_count" in grid else len(grid)
        if context_status == "partial_remaining_day":
            first_sp = int(grid["settlement_period"].min())
            last_sp = int(grid["settlement_period"].max())
            note_parts.append(html.Div(
                f"Grid context is a live remaining-day NESO forecast: {period_count} periods (SP{first_sp}?SP{last_sp}) are currently published for {LATEST_TARGET_DATE}. Earlier settlement periods have already elapsed and are not returned by this endpoint.",
                className="scenario-note-line uncertainty-warning",
            ))
        note_parts.append(html.Div(
            f"Grid context: official National Demand Forecast ranges {grid['national_demand_mw'].min()/1000:.1f}–"
            f"{grid['national_demand_mw'].max()/1000:.1f} GW; latest included publication {publish}. "
            f"At its largest relative point, this {float(capacity_mw):.0f} MW virtual portfolio schedule is about "
            f"{max_share:.2f}% of GB National Demand over the periods currently available from NESO.",
            className="scenario-note-line",
        ))
    except Exception as error:
        grid_figure = _empty_figure(f"Official grid context unavailable: {error}")
        note_parts.append(html.Div(
            "Official grid-demand context could not be loaded; the renewable reserve plan remains available.",
            className="scenario-note-line uncertainty-warning",
        ))

    return html.Div(note_parts), cards, forecast_figure, reserve_figure, grid_figure

@app.callback(
    Output("sizing-recommendation", "children"),
    Output("sizing-chart", "figure"),
    Input("size-button", "n_clicks"),
    State("date-input", "value"),
    State("portfolio-input", "value"),
    State("capacity-input", "value"),
    State("wind-share-input", "value"),
    State("soc-input", "value"),
    State("efficiency-input", "value"),
    State("target-input", "value"),
    prevent_initial_call=True,
)
def run_sizing(
    _clicks: int,
    date_value: str,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    initial_soc_pct: float,
    efficiency_pct: float,
    target_pct: float,
):
    try:
        evidence = select_date(HISTORICAL_DATA, date_value)
        portfolio = build_virtual_portfolio(
            evidence,
            portfolio_type=portfolio_type,  # type: ignore[arg-type]
            capacity_mw=float(capacity_mw),
            wind_share=float(wind_share_pct) / 100,
        )
        power_candidates = [float(capacity_mw) * value for value in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)]
        best, comparison = find_minimum_battery(
            portfolio,
            target_absorbed_pct=float(target_pct),
            power_candidates_mw=power_candidates,
            duration_candidates_hours=(1, 2, 4),
            round_trip_efficiency=float(efficiency_pct) / 100,
            initial_soc_fraction=float(initial_soc_pct) / 100,
        )
    except (TypeError, ValueError, KeyError) as error:
        message = f"Sizing search could not be calculated: {error}"
        return message, _empty_figure(message)

    pivot = comparison.pivot(index="power_mw", columns="duration_hours", values="error_reduction_pct")
    figure = go.Figure(
        data=go.Heatmap(
            x=[f"{value:g} h" for value in pivot.columns],
            y=pivot.index,
            z=pivot.to_numpy(),
            text=[[f"{value:.1f}%" for value in row] for row in pivot.to_numpy()],
            texttemplate="%{text}",
            hovertemplate="Duration %{x}<br>Power %{y:.1f} MW<br>Error absorbed %{z:.1f}%<extra></extra>",
            colorbar={"title": "Absorbed %"},
        )
    )
    figure.update_layout(
        title="Firming performance across battery power and duration",
        xaxis_title="Battery duration",
        yaxis_title="Battery power (MW)",
        margin=dict(l=55, r=30, t=55, b=50),
        height=410,
    )

    if best is not None:
        recommendation = html.Div(
            [
                html.Strong("Smallest tested configuration meeting the target"),
                html.P(
                    f"{best['power_mw']:.1f} MW / {best['energy_mwh']:.1f} MWh "
                    f"({best['duration_hours']:.0f}h) absorbed {best['error_reduction_pct']:.1f}% "
                    f"of absolute forecast deviations for this day."
                ),
                html.P(
                    f"Power-limited periods: {int(best['power_limited_periods'])}; "
                    f"energy-limited periods: {int(best['energy_limited_periods'])}."
                ),
            ]
        )
    else:
        strongest = comparison.sort_values("error_reduction_pct", ascending=False).iloc[0]
        recommendation = html.Div(
            [
                html.Strong("No tested configuration met the selected target"),
                html.P(
                    f"The strongest tested case was {strongest['power_mw']:.1f} MW / "
                    f"{strongest['energy_mwh']:.1f} MWh and absorbed "
                    f"{strongest['error_reduction_pct']:.1f}%."
                ),
            ]
        )
    return recommendation, figure


@app.callback(
    Output("scenario-download", "data"),
    Input("download-button", "n_clicks"),
    State("scenario-store", "data"),
    prevent_initial_call=True,
)
def download_scenario(_clicks: int, stored: str | None):
    if not stored:
        return no_update
    frame = pd.read_json(StringIO(stored), orient="split")
    if "valid_time_utc" in frame.columns:
        frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True)
    return dcc.send_data_frame(frame.to_csv, "renewable_flexibility_scenario.csv", index=False)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
