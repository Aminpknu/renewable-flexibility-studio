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
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.metrics import calculate_firming_metrics
from engine.portfolio import build_virtual_portfolio
from engine.sizing import find_minimum_battery

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "historical_backtest.csv"
FULL_BACKTEST_PATH = ROOT / "outputs" / "full_backtest_summary.json"
EXTENDED_SIZING_PATH = ROOT / "outputs" / "extended_sizing.csv"
HISTORICAL_DATA = load_historical_predictions(DATA_PATH)
FULL_BACKTEST = json.loads(FULL_BACKTEST_PATH.read_text(encoding="utf-8"))
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
    figure.add_trace(
        go.Scatter(
            x=simulation["valid_time_utc"],
            y=simulation["forecast_mw"],
            mode="lines",
            name="Day-ahead forecast",
            line={"dash": "dash", "width": 2.4},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=simulation["valid_time_utc"],
            y=simulation["actual_mw"],
            mode="lines",
            name="Actual renewable output",
            line={"width": 2.4},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=simulation["valid_time_utc"],
            y=simulation["firmed_delivery_mw"],
            mode="lines",
            name="Delivery after battery",
            line={"width": 2.8},
        )
    )
    figure.update_layout(
        xaxis_title="Settlement time (UTC)",
        yaxis_title="Power (MW)",
        hovermode="x unified",
        margin=dict(l=45, r=20, t=58, b=45),
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0, "xanchor": "left", "bgcolor": "rgba(255,255,255,0.94)", "bordercolor": "#dbe3e8", "borderwidth": 1, "font": {"size": 12}},
        height=430,
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
    return [
        html.Div(cards, className="kpi-grid"),
        html.P("First tested configurations reaching 80% in the conservative start-at-minimum-SOC no-grid diagnostic: " + "; ".join(recommendations) + ".", className="section-copy"),
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


def _scenario(
    date_value: str,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
    battery_power_mw: float,
    duration_hours: float,
    initial_soc_pct: float,
    round_trip_efficiency_pct: float,
) -> tuple[pd.DataFrame, BatteryConfig, dict[str, Any]]:
    evidence = select_date(HISTORICAL_DATA, date_value)
    portfolio = build_virtual_portfolio(
        evidence,
        portfolio_type=portfolio_type,  # type: ignore[arg-type]
        capacity_mw=float(capacity_mw),
        wind_share=float(wind_share_pct) / 100,
    )
    config = BatteryConfig(
        power_mw=float(battery_power_mw),
        duration_hours=float(duration_hours),
        round_trip_efficiency=float(round_trip_efficiency_pct) / 100,
        initial_soc_fraction=float(initial_soc_pct) / 100,
    )
    simulation = simulate_reactive_firming(portfolio, config)
    metrics = calculate_firming_metrics(simulation, config)
    return simulation, config, metrics


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
                                html.Div("Renewable delivery before and after battery firming", className="chart-title"),
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
                                html.H2("Find a practical battery size"),
                                html.P(
                                    "The search compares 1h, 2h and 4h systems over a controlled power grid and returns the smallest candidate that meets the selected firming target.",
                                    className="section-copy",
                                ),
                                html.Div(id="sizing-recommendation", className="recommendation-box"),
                            ],
                            className="sizing-copy",
                        ),
                        dcc.Graph(id="sizing-chart", figure=_empty_figure("Click ‘Find minimum’ to run the sizing comparison."), config={"displaylogo": False}),
                    ],
                    className="sizing-section",
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
                            "The full 450-day out-of-sample archive is installed for historical analysis. P10/P50/P90 forecasts will later support a separate uncertainty-aware tomorrow-planning mode without making this site dependent on the forecasting dashboard.",
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
        simulation, config, metrics = _scenario(
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
    note = (
        f"{date_value} · {capacity_mw:.0f} MW {portfolio_label} · selected-day forecast MAE {metrics['mae_before_mw']:.2f} MW "
        f"({abs(day_delta_pct):.0f}% {quality} than the 450-day out-of-sample average of {archive_mae:.2f} MW) · "
        f"{config.power_mw:.0f} MW / {config.energy_capacity_mwh:.0f} MWh battery · "
        f"starts with {config.initial_soc_mwh:.1f} MWh stored ({initial_soc_pct:.0f}% SOC), assumed available from prior periods."
    )
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
    stored = simulation[store_columns].to_json(orient="split", date_format="iso")
    return (
        _generation_figure(simulation),
        _battery_figure(simulation),
        _kpi_cards(metrics),
        note,
        stored,
    )


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
