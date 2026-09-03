"""Models, Data & Validation guide for the Renewable Flexibility Studio."""

from __future__ import annotations

from typing import Any

from dash import dcc, html


def _equation(title: str, formula: str, explanation: str) -> html.Div:
    return html.Div([
        html.H4(title),
        dcc.Markdown(f"$${formula}$$", mathjax=True),
        html.P(explanation, className="section-copy"),
    ], className="guide-equation")


def _details(title: str, children: list[Any], open_by_default: bool = False) -> html.Details:
    return html.Details(
        [html.Summary(title), html.Div(children, className="guide-detail-body")],
        open=open_by_default,
        className="guide-details",
    )
def _assumption_table() -> html.Table:
    rows = [
        ("Virtual portfolio", "User-selected wind / solar / mixed; 10–500 MW", "User scenario", "National V2 capacity-factor evidence is scaled to a transparent virtual portfolio."),
        ("Battery round-trip efficiency", "90% default", "User scenario", "Split symmetrically between charge/discharge efficiencies in the physical model."),
        ("SOC operating band", "10–90%", "Model assumption", "Used for sizing, reserve, market and service co-optimisation."),
        ("Stage 14 central interval", "P10–P90 / nominal 80%", "Model target", "Conditional residual quantiles plus prior-date conformal calibration."),
        ("Historical practical sizing", "50% restored starting SOC", "Model convention", "Daily restoration isolates repeatable firming capability."),
        ("Wholesale throughput cost", "£2/MWh", "Screening assumption", "Already embedded in historical Stage 9/10 dispatch value."),
        ("Reference CAPEX", "£25m", "User scenario", "Default 25 MW / 200 MWh screening case; not a supplier quote."),
        ("Fixed OPEX", "£0.5m/year", "User scenario", "Lifecycle screening input."),
        ("Asset life / discount / degradation", "15 y / 8% / 2%", "User scenario", "Stage 10/12 default reference."),
        ("Availability", "95%", "User scenario", "Applied as operational uncertainty in Monte Carlo."),
        ("Debt structure", "60% debt, 6%, 10 y", "User scenario", "Constant-annuity Stage 12 screening convention."),
        ("Tax / equity hurdle / DSCR", "25% / 12% / 1.20×", "User scenario", "Simplified financing screen, not tax or lending advice."),
    ]
    return html.Table([
        html.Thead(html.Tr([html.Th("Input / convention"), html.Th("Default"), html.Th("Class"), html.Th("Interpretation")])),
        html.Tbody([html.Tr([html.Td(value) for value in row]) for row in rows]),
    ], className="guide-table")
def _source_table() -> html.Table:
    rows = [
        ("NESO", "Embedded wind/solar generation and capacity; National Demand Forecast; GSP boundaries", "Authoritative GB system / renewable context"),
        ("Elexon Insights", "System Price, Net Imbalance Volume, APX Market Index, GSP Group Take", "Settlement, wholesale-reference and regional-load evidence"),
        ("NESO Enduring Auction Capability", "QR/SR/BR/Dynamic Response clearing results and Sell Orders", "Ancillary-service price and acceptance evidence"),
        ("ECMWF IFS HRES via the V2 forecasting project", "Issue-time weather predictors at ten representative locations", "Base deterministic renewable forecast"),
        ("DESNZ Renewable Energy Planning Database", "Operational wind/solar project capacity and location", "Spatial renewable-capacity proxy only"),
        ("DESNZ subnational electricity consumption", "Local Authority annual domestic/non-domestic electricity", "Spatial demand weights"),
    ]
    return html.Table([
        html.Thead(html.Tr([html.Th("Source"), html.Th("Used for"), html.Th("Role / boundary")])),
        html.Tbody([html.Tr([html.Td(value) for value in row]) for row in rows]),
    ], className="guide-table")


def _source_links() -> html.Ul:
    return html.Ul([
        html.Li(html.A("NESO Open Data", href="https://www.neso.energy/data-portal", target="_blank")),
        html.Li(html.A("Elexon Insights / BMRS API", href="https://bmrs.elexon.co.uk/api-documentation", target="_blank")),
        html.Li(html.A("DESNZ Renewable Energy Planning Database", href="https://www.gov.uk/government/publications/renewable-energy-planning-database-monthly-extract", target="_blank")),
        html.Li(html.A("DESNZ subnational electricity consumption", href="https://www.gov.uk/government/collections/sub-national-electricity-consumption-data", target="_blank")),
        html.Li(html.A("ECMWF", href="https://www.ecmwf.int/", target="_blank")),
    ])
def build_models_data_validation_guide(
    stage14_summary: dict[str, Any],
    stage14_comparison: dict[str, Any],
    stage13_summary: dict[str, Any],
) -> html.Section:
    mixed = stage14_summary["locked_reference"]["mixed_50_50"]
    comparison = stage14_comparison["by_wind_share"]["0.50"]
    stage13 = stage13_summary["scenarios"]["non_bm"]
    workflow = html.Ol([
        html.Li("Start with V2 deterministic wind/solar forecast evidence."),
        html.Li("Quantify P10/P50/P90 uncertainty and size / prepare BESS reserve."),
        html.Li("Simulate physical firming under explicit MW, MWh, efficiency and SOC constraints."),
        html.Li("Optimise the same BESS across wholesale and NESO ancillary services."),
        html.Li("Translate operating evidence into lifecycle risk, NPV and project-finance screens."),
        html.Li("Inspect spatial supply, underlying demand and net-load proxies across ten zones."),
    ], className="guide-workflow")
    probabilistic = _details("1. Forecast evidence and Stage 14 P10/P50/P90", [
        html.P("The deterministic V2 forecast remains the scheduled renewable export. Stage 14 is a statistical post-processor of V2 errors; it does not replace the V2 point model and is not an ECMWF ensemble forecast.", className="section-copy"),
        _equation("Virtual portfolio", r"\widehat{CF}_{p,t}=w\widehat{CF}_{wind,t}+(1-w)\widehat{CF}_{solar,t}", "w is the user-selected wind capacity share. The same mixing rule is used for observed capacity factor during historical calibration."),
        _equation("Residual target", r"r_t=CF_{p,t}-\widehat{CF}_{p,t}", "The quantile regressors learn the conditional distribution of V2 out-of-sample residuals from issue-time-known predictors."),
        _equation("Conditional quantiles", r"P_q(t)=clip\left(\widehat{CF}_{p,t}+\widehat{Q}_q(r_t\mid x_t)\pm c,0,1\right)", "Separate q=0.10, 0.50 and 0.90 regressors are fitted. The conformal correction c expands only the outer interval; P50 is not shifted."),
        _equation("Conformal score", r"s_i=max(\widehat{P}_{10,i}-y_i,\;y_i-\widehat{P}_{90,i},\;0)", "The rolling correction uses only earlier observed days in locked evaluation. Production corrections are frozen by 5%-step wind-share after the locked metrics are recorded."),
        html.P(f"Locked 50/50 evidence: {mixed['observed_p10_p90_coverage_pct']:.1f}% P10–P90 coverage over {int(mixed['days'])} days; mean interval width {mixed['mean_p10_p90_width_cf']:.4f} CF. The prior Stage B 180-day residual envelope gives {comparison['old_directional_residual']['coverage_pct']:.1f}% coverage on the same period.", className="section-copy"),
    ], True)
    battery = _details("2. Battery physics, firming and SOC", [
        html.P("All optimisation layers use the same physical battery conventions: finite MW, finite MWh, 10–90% SOC, round-trip efficiency and no simultaneous physical charge/discharge.", className="section-copy"),
        _equation("Energy capacity", r"E_{BESS}=P_{BESS}\times h", "Power is in MW, duration h is in hours and energy capacity is in MWh."),
        _equation("SOC balance", r"E_t=E_{t-1}+\eta_c P^{ch}_t\Delta t-\frac{P^{dis}_t\Delta t}{\eta_d}", "Charge adds stored energy after charging losses; discharge removes more stored energy than delivered because of discharge losses."),
        _equation("Renewable forecast deviation", r"e_t=P^{actual}_t-P^{schedule}_t", "Positive deviation means excess renewable generation and is absorbed by charging; negative deviation requires discharge to firm the schedule."),
        _equation("Residual deviation", r"e^{res}_t=e_t-P^{ch}_t+P^{dis}_t", "Physical firming is measured from the reduction in absolute forecast-error energy after constrained battery response."),
        html.P("The selected-day historical scenario is diagnostic. The Stage A design benchmark restores SOC to 50% before each evidence day so repeated daily firming capability can be compared consistently.", className="section-copy"),
    ])

    reserve = _details("3. Sizing, reserve and starting-SOC formulation", [
        html.P("Future battery sizing requires a tested MW/MWh design to meet the selected daily firming target on at least the selected share of historical days. The default stability gate is 90% firming on 90% of days.", className="section-copy"),
        _equation("Rolling downside reserve", r"R^{down}_t=\sum_{k=t}^{t+H}(P^{schedule}_k-P10_k)^+\Delta t", "H is the reserve horizon, normally equal to installed battery duration. This is the discharge energy that may be needed if generation falls toward P10."),
        _equation("Rolling upward headroom", r"R^{up}_t=\sum_{k=t}^{t+H}(P90_k-P^{schedule}_k)^+\Delta t", "This is the charging headroom that may be needed if generation rises toward P90."),
        _equation("Safe starting-SOC band", r"E_{min}+\frac{max(R^{down})}{\eta_d}\le E_0\le E_{max}-max(R^{up})\eta_c", "If the current SOC already lies inside this band, the operational rule is to hold it. If the band is infeasible, the planner does not force an unvalidated compromise shift."),
    ])
    market = _details("4. Wholesale, imbalance and NESO service optimisation", [
        html.P("The market layers use one physical battery. Wholesale arbitrage, renewable firming and ancillary-service commitments compete for the same MW, MWh and SOC; their values are not added as independent revenue streams.", className="section-copy"),
        _equation("Wholesale arbitrage", r"\max\sum_t \left[\pi_t(P^{dis}_t-P^{ch}_t)\Delta t-c_{thr}(P^{dis}_t+P^{ch}_t)\Delta t\right]", "π is the relevant wholesale price/reference and c_thr is the transparent throughput-cost assumption. Perfect-information and forecast-selected strategies are reported separately."),
        _equation("Shared ancillary nameplate", r"\sum_{s\in S_t}P^{service}_{s,t}\le P_{BESS}", "The conservative generic service framework does not sell the same physical MW into multiple simultaneous ancillary products."),
        _equation("Directional headroom", r"P^{dis}_t+P^{up\ service}_t\le P_{BESS},\qquad P^{ch}_t+P^{down\ service}_t\le P_{BESS}", "Upward services reserve discharge headroom; downward services reserve charging headroom. Service-specific energy guards also protect SOC."),
        html.P("Quick Reserve, Slow Reserve and Dynamic Response use their actual EAC delivery windows. Balancing Reserve is enabled only under an explicit BM-eligibility scenario. Utilisation payments and performance penalties remain outside the current availability-value screen.", className="section-copy"),
    ])

    acceptance = _details("5. Stage 13 issue-time bids and auction acceptance", [
        html.P("Stage 13 removes service-price perfect foresight. Clearing prices are forecast from earlier dates, capacity is chosen before delivery, and an opportunity-cost bid floor is calculated from forecast wholesale value.", className="section-copy"),
        _equation("Opportunity-cost bid", r"b_s=\frac{V^{wholesale}_{base}-V^{wholesale}_{with\ service\ s}}{MW_s\times h_s}", "The bid floor reflects forecast wholesale value displaced by reserving battery capacity for the ancillary contract."),
        _equation("Acceptance-calibrated expected MW", r"E[MW^{acc}_s]=min(MW^{offer}_s,MW^{cleared}_s)\times \hat p^{acc}_s\times I(b_s\le \pi^{clear}_s)", "The acceptance probability is estimated from earlier comparable NESO EAC parent orders. Realised clearing price/volume enter only in ex-post scoring."),
        html.P(f"The non-BM Stage 13 screen annualises to about £{stage13['annualised_acceptance_calibrated_total_gbp']/1e6:.2f}m/year on 60 eligible May–Jun 2026 dates. This is counterfactual expected-acceptance evidence, not a claim that the virtual asset actually cleared those historical auctions.", className="section-copy"),
    ])
    economics = _details("6. Risk, lifecycle value and Monte Carlo", [
        html.P("The Studio keeps three economic evidence levels separate: Stage 6 consequence-value screening, Stage 10 market-backed wholesale evidence, and ancillary-service upside/calibrated screens. None is labelled bankable revenue.", className="section-copy"),
        _equation("Lifecycle NPV", r"NPV=-C_0+\sum_{y=1}^{N}\frac{V_1(1-g)^{y-1}-O_y-R_y}{(1+r)^y}", "C0 is upfront CAPEX; V1 is year-one operating value; g is annual degradation; O is OPEX; R is optional replacement cost; r is the discount rate."),
        _equation("Benefit-cost ratio", r"BCR=\frac{PV(operating\ benefit)}{PV(CAPEX+OPEX+replacement)}", "BCR is a screening ratio. The app also reports break-even annual operating value and maximum CAPEX compatible with zero NPV."),
        _equation("Tail-loss convention", r"Loss=-NPV,\qquad CVaR_{95\%}=E[Loss\mid Loss\ge VaR_{95\%}]", "Monte Carlo resamples contiguous historical day blocks and varies transparent cost/availability/degradation assumptions. P10/P50/P90 are distribution quantiles, not confidence intervals on a fitted mean."),
    ])

    finance = _details("7. Project-finance screening", [
        html.P("Stage 12 converts operating evidence into a simplified project/debt/equity screen. The conservative finance base remains the forecast-selected wholesale evidence; Stage 13 and Stage 11 are shown as separately labelled ancillary-service cases.", className="section-copy"),
        _equation("Constant debt service", r"DS=\frac{D\,i}{1-(1+i)^{-n}}", "D is initial debt, i is annual debt interest rate and n is debt tenor. Principal equals debt service less interest on opening debt."),
        _equation("DSCR", r"DSCR_y=\frac{CFADS_y}{Debt\ Service_y}", "Cash flow available for debt service is operating cash flow after the simplified tax scenario and before debt service."),
        _equation("LLCR", r"LLCR=\frac{PV_{debt\ rate}(CFADS\ during\ loan\ life)}{Initial\ debt}", "LLCR and minimum DSCR are lender-style screening indicators, not a lender credit decision."),
        html.P("Tax, capital allowances, refinancing, hedging, debt sculpting, reserve accounts, VAT and loss carry-forward are deliberately simplified or excluded. The finance layer is not tax, accounting, lending or investment advice.", className="section-copy"),
    ])
    spatial = _details("8. Spatial renewable supply, demand and net load", [
        html.P("The ten named locations are broad allocation zones represented by the V2 weather points. They are not municipal-city metering boundaries and are not independently trained city-generation models.", className="section-copy"),
        _equation("Renewable spatial allocation", r"G_{z,t}=G_{GB,t}\frac{C^{proxy}_z\,W_{z,t}}{\sum_j C^{proxy}_j\,W_{j,t}}", "The national V2 total stays authoritative. DESNZ REPD operational-capacity proxy weights are combined with the local weather signal and normalised so every half-hour sums exactly to GB."),
        _equation("Underlying-demand proxy", r"D^{under}_{GB,t}=NDF_t+G^{wind,emb}_{GB,t}+G^{solar,emb}_{GB,t}", "NESO National Demand is already suppressed by embedded renewables, so embedded generation is added back before spatial demand allocation to avoid double-subtraction."),
        _equation("Zone net load", r"L_{z,t}=D^{under}_{z,t}-G^{wind,emb}_{z,t}-G^{solar,emb}_{z,t}", "The ten zone net-load proxies reconcile to NESO National Demand every half-hour. They are planning proxies, not feeder measurements or congestion studies."),
    ])

    controls = _details("9. Practical manual: how to use the Studio", [
        html.Ol([
            html.Li("Choose wind, solar or mixed portfolio, capacity and wind share. These define the virtual portfolio only; they do not change official GB system data."),
            html.Li("Use Future battery sizing for the main MW/MWh design decision. The selected-day sizing button is exploratory only."),
            html.Li("Use Forecast-day operational planning for the current P10/P50/P90 range, safe SOC band and reserve/headroom requirements."),
            html.Li("Use market and NESO sections to compare perfect-information upper bounds, forecast-selected strategies and acceptance-calibrated evidence. Do not add their values independently."),
            html.Li("Use Stage 10/12 for investment and financing screening. Change CAPEX/OPEX/debt/tax assumptions visibly and treat outputs as pre-feasibility evidence."),
            html.Li("Use spatial zones for supply/demand/net-load context only. Do not interpret a zone result as measured city demand or a site-specific BESS recommendation."),
            html.Li("Download CSV/JSON outputs when an audit trail is needed; the repository also stores frozen evidence summaries and checksums."),
        ], className="guide-workflow"),
    ])
    provenance = _details("10. Data sources and references", [
        html.P("The table distinguishes authoritative system/settlement data from modelling proxies. Source links are provided for traceability; exact downloaded artefacts are checksum-locked in the repository manifests where applicable.", className="section-copy"),
        _source_table(),
        html.H4("Reference links"),
        _source_links(),
    ])

    assumptions = _details("11. Assumption register", [
        html.P("Inputs are deliberately classified as user scenarios, model conventions or evidence targets. A number appearing in the app is not automatically an observed market or supplier value.", className="section-copy"),
        html.Div(_assumption_table(), className="guide-table-wrap"),
    ])

    limits = _details("12. Boundaries and what the Studio does not claim", [
        html.Ul([
            html.Li("The portfolio is virtual and based on national V2 forecast-error behaviour; it is not a site-specific battery design."),
            html.Li("Stage 14 P10/P50/P90 are conditional statistical quantiles calibrated from V2 residual evidence, not ECMWF ensemble-member probabilities."),
            html.Li("APX Market Index is a public short-term wholesale reference and is not relabelled as a licensed day-ahead auction price."),
            html.Li("Stage 11 is a perfect-information price-taker upper bound; Stage 13 is acceptance-calibrated counterfactual evidence, not actual historical asset revenue."),
            html.Li("The ancillary-service model excludes utilisation/performance settlement that is not supported by the current evidence contract."),
            html.Li("Spatial zones are reconciled allocation proxies; no distribution-network power flow, connection study or municipal demand metering is claimed."),
            html.Li("Financial outputs are pre-feasibility screens and not investment, tax, legal or lending advice."),
        ], className="guide-limit-list"),
    ])
    reproducibility = _details("13. Validation and reproducibility", [
        html.Ul([
            html.Li("Historical renewable evidence is out-of-sample V2 OOF plus locked-test output; target-day realised values are not used in future/issue-time decisions."),
            html.Li("Stage 14 model selection uses development OOF only. Locked Apr–Jun 2026 metrics are recorded before the production conformal-width calibration is frozen."),
            html.Li("Battery equations, reserve rules, market value, service stacking, acceptance calibration and finance equations have automated tests."),
            html.Li("Market/acceptance evidence keeps explicit issue-time versus realised-scoring boundaries and stores compact manifests/checksums."),
            html.Li("Stage 16 validates the imported V2 forecast schema, period completeness, target date and freshness before atomic publication; the prior valid bundle is archived before replacement."),
            html.Li("The app is presentation/inference. Long-running evidence builders and model training are reproducible scripts outside normal page callbacks."),
            html.Li("DST settlement days are handled as 46/48/50 periods; incomplete evidence is rejected or explicitly labelled partial where appropriate."),
        ], className="guide-limit-list"),
    ])

    return html.Section([
        html.Div([
            html.Div("TECHNICAL TRANSPARENCY", className="eyebrow"),
            html.H2("Models, Data & Validation Guide"),
            html.P("A practical manual for the Studio: what each layer calculates, its equations, evidence, assumptions, references and limits.", className="section-copy"),
        ], className="guide-heading"),
        html.Div(workflow, className="guide-workflow-wrap"),
        probabilistic, battery, reserve, market, acceptance, economics, finance,
        spatial, controls, provenance, assumptions, limits, reproducibility,
    ], id="models-data-validation-guide", className="download-section methodology-guide")
