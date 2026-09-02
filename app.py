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

from adapters.forecast_data import available_dates, load_historical_predictions, select_date
from adapters.grid_context import fetch_day_ahead_demand
from adapters.imbalance_settlement import load_system_price_history, select_system_prices
from adapters.latest_forecast import latest_target_date, load_latest_forecast
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.imbalance import apply_imbalance_settlement, summarise_imbalance_settlement
from engine.metrics import calculate_firming_metrics
from engine.portfolio import build_virtual_forecast, build_virtual_portfolio
from engine.sizing import find_minimum_battery
from engine.uncertainty import (
    PredictionIntervalConfig,
    build_forecast_only_prediction_interval,
    build_rolling_prediction_interval,
)

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "historical_backtest.csv"
FULL_BACKTEST_PATH = ROOT / "outputs" / "full_backtest_summary.json"
EXTENDED_SIZING_PATH = ROOT / "outputs" / "extended_sizing.csv"
IMBALANCE_SUMMARY_PATH = ROOT / "outputs" / "imbalance_backtest_summary.json"
LATEST_FORECAST_PATH = ROOT / "data" / "latest_forecast.csv"
SYSTEM_PRICES_PATH = ROOT / "data" / "elexon_system_prices.csv"
HISTORICAL_DATA = load_historical_predictions(DATA_PATH)
SYSTEM_PRICES = load_system_price_history(SYSTEM_PRICES_PATH)
LATEST_FORECAST = load_latest_forecast(LATEST_FORECAST_PATH)
LATEST_TARGET_DATE = latest_target_date(LATEST_FORECAST)
FULL_BACKTEST = json.loads(FULL_BACKTEST_PATH.read_text(encoding="utf-8"))
IMBALANCE_BACKTEST = json.loads(IMBALANCE_SUMMARY_PATH.read_text(encoding="utf-8"))
EXTENDED_SIZING = pd.read_csv(EXTENDED_SIZING_PATH)
DATE_OPTIONS = available_dates(HISTORICAL_DATA)
DEFAULT_DATE = DATE_OPTIONS[-1]

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


def _tomorrow_planning_data(
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    battery_power_mw: float,
    duration_hours: float,
    initial_soc_pct: float,
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
    interval, uncertainty = build_forecast_only_prediction_interval(
        history, forecast, LATEST_TARGET_DATE,
        PredictionIntervalConfig(lookback_days=180, minimum_history_days=30, neighbour_count=600),
    )
    config = BatteryConfig(
        power_mw=float(battery_power_mw), duration_hours=float(duration_hours),
        round_trip_efficiency=float(efficiency_pct) / 100,
        initial_soc_fraction=float(initial_soc_pct) / 100,
    )
    planning: dict[str, Any] = {"uncertainty": uncertainty}
    if uncertainty.get("available"):
        down = interval["forecast_mw"] - interval["prediction_interval_lower_mw"]
        up = interval["prediction_interval_upper_mw"] - interval["forecast_mw"]
        peak_deviation = float(max(down.max(), up.max()))
        planning.update({
            "peak_downward_reserve_mw": float(down.max()),
            "peak_upward_headroom_mw": float(up.max()),
            "peak_interval_deviation_mw": peak_deviation,
            "battery_power_coverage_pct": min(100.0, 100.0 * config.power_mw / peak_deviation) if peak_deviation > 0 else 100.0,
        })
    planning["forecast_energy_mwh"] = float(interval["forecast_mw"].sum() * 0.5)
    planning["peak_forecast_mw"] = float(interval["forecast_mw"].max())
    planning["discharge_reserve_mwh"] = float(
        max(config.initial_soc_mwh - config.minimum_soc_mwh, 0.0) * config.discharge_efficiency
    )
    planning["charge_headroom_mwh"] = float(
        max(config.maximum_soc_mwh - config.initial_soc_mwh, 0.0) / config.charge_efficiency
    )
    return interval, config, planning


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
            fillcolor="rgba(99,110,250,0.16)", name="Nominal 80% expected range",
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
                                html.Label("Battery power (MW)"),
                                dcc.Input(id="power-input", type="number", min=1, max=250, step=1, value=25),
                                html.Label("Battery duration"),
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
                                html.Label("Initial battery SOC at start of selected day (%)"),
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
                                html.Label("Round-trip efficiency (%)"),
                                dcc.Slider(
                                    id="efficiency-input",
                                    min=80,
                                    max=100,
                                    step=1,
                                    value=90,
                                    marks={80: "80", 90: "90", 100: "100"},
                                    tooltip={"placement": "bottom", "always_visible": False},
                                ),
                                html.Label("Sizing target: deviations absorbed"),
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
                                        html.Button("Find minimum", id="size-button", n_clicks=0, className="secondary-button"),
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
                        html.Div(
                            [
                                html.H2("Selected-day battery sizing (exploratory)"),
                                html.P(
                                    "This quick search applies only to the historical day selected above. It tests 1h, 2h and 4h batteries across a controlled MW grid and returns the smallest tested candidate that reaches your chosen deviation-absorption target. It is not the long-run battery recommendation; use the 450-day continuous-SOC evidence below for that.",
                                    className="section-copy",
                                ),
                                html.Div(
                                    "No sizing result yet. Choose a historical date and target, then click ‘Find minimum’ in the left-hand controls.",
                                    id="sizing-recommendation",
                                    className="recommendation-box sizing-placeholder",
                                ),
                            ],
                            className="sizing-copy",
                        ),
                        dcc.Graph(id="sizing-chart", figure=_empty_figure("Click ‘Find minimum’ to run the sizing comparison."), config={"displaylogo": False}),
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
                        html.H2(f"Tomorrow planning & GB grid context · {LATEST_TARGET_DATE}"),
                        html.P(
                            "Tomorrow mode uses the latest V2 wind/solar point forecast as an illustrative scheduled export. Actual generation is not known yet, so the Studio does not simulate a future charge/discharge path. Instead it shows the expected forecast range and the battery reserve/headroom available against that uncertainty.",
                            className="section-copy",
                        ),
                        html.Button("Refresh tomorrow planning", id="tomorrow-button", n_clicks=0, className="primary-button"),
                        html.Div(id="tomorrow-note", className="scenario-note"),
                        html.Div(id="tomorrow-kpi-grid", className="kpi-grid"),
                        html.Div("Tomorrow renewable schedule and expected range", className="chart-title"),
                        html.Div("The dashed line is the planned renewable export from the V2 forecast. The shaded range comes from prior out-of-sample forecast errors; tomorrow's actual output is unknown.", className="chart-subtitle"),
                        dcc.Graph(id="tomorrow-forecast-chart", figure=_empty_figure("Tomorrow planning will load automatically."), config={"displaylogo": False}),
                        html.Div("Official GB day-ahead demand context", className="chart-title"),
                        html.Div("National Demand Forecast is official NESO data served through Elexon Insights. It provides system-scale context; the virtual portfolio is not claimed to be a physical national battery.", className="chart-subtitle"),
                        dcc.Graph(id="grid-demand-chart", figure=_empty_figure("GB demand context will load automatically."), config={"displaylogo": False}),
                    ],
                    className="download-section",
                ),
                html.Section(
                    [
                        html.H2("450-day continuous-SOC benchmark"),
                        html.P(
                            "The cards below use the full out-of-sample V2 archive with one initial SOC only. SOC carries across midnight and is never reset each day. The fixed benchmark uses a 100 MW virtual portfolio, 25 MW / 50 MWh battery, 90% round-trip efficiency and no grid charging.",
                            className="section-copy",
                        ),
                        *_long_run_benchmark_content(),
                        html.P(
                            "The selected-day controls above remain useful for operational interpretation, but a single day should not be treated as the long-run storage-sizing conclusion.",
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
    Output("tomorrow-note", "children"),
    Output("tomorrow-kpi-grid", "children"),
    Output("tomorrow-forecast-chart", "figure"),
    Output("grid-demand-chart", "figure"),
    Input("tomorrow-button", "n_clicks"),
    State("portfolio-input", "value"),
    State("capacity-input", "value"),
    State("wind-share-input", "value"),
    State("power-input", "value"),
    State("duration-input", "value"),
    State("soc-input", "value"),
    State("efficiency-input", "value"),
)
def run_tomorrow_planning(
    _clicks: int, portfolio_type: str, capacity_mw: float, wind_share_pct: float,
    battery_power_mw: float, duration_hours: float, initial_soc_pct: float,
    efficiency_pct: float,
):
    try:
        forecast, config, planning = _tomorrow_planning_data(
            portfolio_type, capacity_mw, wind_share_pct, battery_power_mw,
            duration_hours, initial_soc_pct, efficiency_pct,
        )
    except (TypeError, ValueError, KeyError) as error:
        message = f"Tomorrow planning could not be calculated: {error}"
        empty = _empty_figure(message)
        return message, [], empty, empty
    uncertainty = planning["uncertainty"]
    cards = [
        _kpi_card("Forecast energy", f"{planning['forecast_energy_mwh']:.1f} MWh", "Tomorrow's virtual portfolio schedule"),
        _kpi_card("Peak forecast", f"{planning['peak_forecast_mw']:.1f} MW", "Highest scheduled renewable export"),
        _kpi_card("Discharge reserve", f"{planning['discharge_reserve_mwh']:.1f} MWh", "Deliverable energy above the 10% SOC reserve"),
        _kpi_card("Charge headroom", f"{planning['charge_headroom_mwh']:.1f} MWh", "Renewable surplus energy absorbable before 90% SOC"),
    ]
    if uncertainty.get("available"):
        cards.extend([
            _kpi_card("Peak expected deviation", f"{planning['peak_interval_deviation_mw']:.1f} MW", "Largest one-sided distance from schedule to expected range"),
            _kpi_card("Single-period MW coverage", f"{planning['battery_power_coverage_pct']:.0f}%", "Battery MW divided by the peak expected one-period deviation; this does not prove sufficient MWh for the whole day"),
        ])
    forecast_figure = _tomorrow_forecast_figure(forecast)

    issue = pd.Timestamp(LATEST_FORECAST["forecast_created_utc"].iloc[0]).strftime("%Y-%m-%d %H:%M UTC")
    note_parts: list[Any] = [html.Div(
        f"Renewable forecast target {LATEST_TARGET_DATE}; V2 bundle created {issue}. Planning only: no actual generation or future battery dispatch is assumed.",
        className="scenario-note-line",
    )]
    if uncertainty.get("available"):
        note_parts.append(html.Div(
            f"Uncertainty band: nominal {uncertainty['nominal_coverage_pct']:.0f}% range calibrated from {uncertainty['history_days']} earlier out-of-sample days "
            f"({uncertainty['calibration_start']} to {uncertainty['calibration_end']}); mean width {uncertainty['mean_interval_width_mw']:.2f} MW.",
            className="scenario-note-line uncertainty-line",
        ))
    else:
        note_parts.append(html.Div(
            "Uncertainty band is unavailable because the verified historical archive does not contain enough prior calibration days.",
            className="scenario-note-line uncertainty-warning",
        ))

    try:
        grid = fetch_day_ahead_demand(LATEST_TARGET_DATE)
        grid_figure = _grid_demand_figure(grid)
        merged = forecast[["settlement_period", "forecast_mw"]].merge(
            grid[["settlement_period", "national_demand_mw"]], on="settlement_period", validate="one_to_one"
        )
        max_share = float((100.0 * merged["forecast_mw"] / merged["national_demand_mw"]).max())
        publish = grid["publish_time_utc"].max().strftime("%Y-%m-%d %H:%M UTC")
        note_parts.append(html.Div(
            f"Grid context: official National Demand Forecast ranges {grid['national_demand_mw'].min()/1000:.1f}–{grid['national_demand_mw'].max()/1000:.1f} GW; "
            f"latest included publication {publish}. At its largest relative point, this {float(capacity_mw):.0f} MW virtual portfolio schedule is about {max_share:.2f}% of GB National Demand.",
            className="scenario-note-line",
        ))
    except Exception as error:
        grid_figure = _empty_figure(f"Official grid context unavailable: {error}")
        note_parts.append(html.Div(
            "Official grid-demand context could not be loaded; the renewable planning result remains available.",
            className="scenario-note-line uncertainty-warning",
        ))
    return html.Div(note_parts), cards, forecast_figure, grid_figure


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
