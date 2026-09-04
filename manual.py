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


def _definition_grid(items: tuple[tuple[str, str], ...]) -> html.Dl:
    children = []
    for term, definition in items:
        children.extend([html.Dt(term), html.Dd(definition)])
    return html.Dl(children, className="guide-definition-grid")
CORE_TERMS = (
    ("GB", "Great Britain: England, Scotland and Wales. The Studio uses GB electricity-system evidence; it is not an all-UK market model."),
    ("V2 forecast", "The second validated release of the companion GB renewable forecasting model and its frozen out-of-sample evidence contract."),
    ("BESS", "Battery Energy Storage System: the battery represented by explicit MW power, MWh energy, efficiency and state-of-charge limits."),
    ("MW", "Megawatt: a unit of instantaneous power or capacity. 1 MW equals 1,000 kW."),
    ("GW", "Gigawatt: a unit of power or capacity equal to 1,000 MW."),
    ("kW", "Kilowatt: a unit of power equal to 0.001 MW."),
    ("kWh", "Kilowatt-hour: a unit of energy equal to 0.001 MWh."),
    ("MWh", "Megawatt-hour: a unit of energy. 1 MW sustained for one hour equals 1 MWh."),
    ("SOC", "State of charge: the energy currently stored in the battery, normally shown as a percentage of the applicable energy capacity."),
    ("SOH", "State of health: the assumed remaining battery energy capability relative to its new or nameplate condition."),
    ("DoD", "Depth of discharge: the fraction of stored energy removed during a battery cycle."),
    ("EFC", "Equivalent full cycle: charge-plus-discharge throughput normalised to one complete cycle of the usable battery energy."),
    ("POC", "Point of Connection: the site-to-grid boundary whose import and export limits constrain battery operation."),
    ("P10 / P50 / P90", "10th, 50th and 90th percentiles of a predictive distribution. P50 is the median; P10 to P90 is a nominal 80% central interval."),
    ("CF", "Capacity factor: generation divided by installed capacity, expressed as a unitless fraction."),
    ("OOF", "Out-of-fold: validation predictions generated from model folds where the evaluated observations were not used to fit that fold."),
    ("MAE", "Mean absolute error: the average absolute difference between predicted and observed values."),
    ("R²", "Coefficient of determination: a unitless measure of how much observed variation is explained by the model relative to a mean benchmark."),
)

MARKET_TERMS = (
    ("NESO", "National Energy System Operator: the Great Britain electricity-system operator and a primary source for demand, renewable and balancing-service data used by the Studio."),
    ("BSC", "Balancing and Settlement Code: the GB electricity balancing and settlement framework administered by Elexon."),
    ("BM", "Balancing Mechanism: the market used by NESO to accept bids and offers that help balance the GB electricity system close to real time."),
    ("BMU", "Balancing Mechanism Unit: a registered unit used for Balancing Mechanism submissions, instructions and settlement reporting."),
    ("BOD", "Bid-Offer Data: submitted bid and offer price/volume data for Balancing Mechanism Units."),
    ("BOA", "Bid-Offer Acceptance: a formal accepted bid or offer instruction in the Balancing Mechanism."),
    ("BOALF", "Bid-Offer Acceptance Level Flagged: the Elexon dataset that records accepted operating levels associated with bid-offer acceptances."),
    ("BMRS", "Balancing Mechanism Reporting Service: the legacy name still used in some Elexon data/API references; current public data is served through the Elexon Insights Solution."),
    ("NIV", "Net Imbalance Volume: the net balancing-energy volume for a settlement period used in GB imbalance pricing context."),
    ("MIP", "Market Index Price: the price reported in Elexon Market Index Data. The Studio uses it as a public short-term wholesale reference, not as a licensed day-ahead auction price."),
    ("APX Market Index", "The APX-labelled Market Index Data series used by the Studio as a public short-term wholesale reference."),
    ("EAC", "Enduring Auction Capability: NESO's auction platform/data framework for reserve and response services used in the Studio's ancillary-service evidence."),
    ("QR", "Quick Reserve: a NESO reserve service designed to respond rapidly to system imbalances."),
    ("SR", "Slow Reserve: a NESO reserve service with a slower delivery profile than Quick Reserve."),
    ("BR", "Balancing Reserve: a NESO reserve service available to eligible Balancing Mechanism participants."),
    ("PQR / NQR", "Positive Quick Reserve / Negative Quick Reserve: the upward and downward Quick Reserve products."),
    ("PSR / NSR", "Positive Slow Reserve / Negative Slow Reserve: the upward and downward Slow Reserve products."),
    ("PBR / NBR", "Positive Balancing Reserve / Negative Balancing Reserve: the upward and downward Balancing Reserve products."),
    ("DCL / DCH", "Dynamic Containment Low / Dynamic Containment High: low- and high-frequency Dynamic Containment products."),
    ("DML / DMH", "Dynamic Moderation Low / Dynamic Moderation High: low- and high-frequency Dynamic Moderation products."),
    ("DRL / DRH", "Dynamic Regulation Low / Dynamic Regulation High: low- and high-frequency Dynamic Regulation products."),
    ("EFA block", "Electricity Forward Agreement block: one of the standard four-hour GB electricity trading blocks."),
    ("VWAP", "Volume-weighted average price: an average price weighted by the corresponding traded or cleared volumes."),
)

FINANCE_TERMS = (
    ("NPV", "Net present value: discounted project benefits minus discounted project costs, including upfront capital expenditure."),
    ("PV", "Present value: a future cash flow converted into today's money using the selected discount rate."),
    ("GBP", "Pounds sterling: the currency used for monetary values in the Studio; the interface normally displays the £ symbol."),
    ("CAPEX", "Capital expenditure: upfront investment cost used in the pre-feasibility battery screening."),
    ("OPEX", "Operating expenditure: recurring operating cost. The Studio separates fixed annual OPEX from throughput-related costs where applicable."),
    ("BCR", "Benefit-cost ratio: present value of operating benefit divided by present value of lifecycle cost."),
    ("IRR", "Internal rate of return: the discount rate that makes the relevant cash-flow NPV equal to zero."),
    ("DSCR", "Debt service coverage ratio: cash flow available for debt service divided by scheduled debt service for the same year."),
    ("LLCR", "Loan life coverage ratio: present value of cash flow available for debt service during the loan life divided by initial debt."),
    ("CFADS", "Cash flow available for debt service: project cash flow available to meet interest and principal payments in the finance screen."),
    ("VaR", "Value at risk: the loss threshold associated with a selected tail probability in the simulated distribution."),
    ("CVaR", "Conditional value at risk, also called expected shortfall: the average loss beyond the selected VaR threshold."),
    ("VAT", "Value Added Tax: a tax category explicitly excluded from the simplified project-finance screen."),
)

DATA_TERMS = (
    ("DESNZ", "Department for Energy Security and Net Zero: UK government source for renewable planning and subnational electricity-consumption data used by the spatial layer."),
    ("REPD", "Renewable Energy Planning Database: DESNZ dataset used as a spatial renewable-capacity proxy."),
    ("GSP", "Grid Supply Point: a transmission-to-distribution interface used in regional electricity-data context."),
    ("DNO", "Distribution Network Operator: the company responsible for operating a regional electricity distribution network."),
    ("TO", "Transmission Owner: the company responsible for owning and maintaining transmission assets in its licensed area."),
    ("ECMWF", "European Centre for Medium-Range Weather Forecasts: the weather-forecast provider behind the deterministic weather input used by the companion forecasting project."),
    ("IFS HRES", "Integrated Forecasting System High Resolution: the deterministic ECMWF weather forecast configuration used by the companion GB forecasting project."),
    ("UTC", "Coordinated Universal Time: the time standard used for reproducible issue-time, valid-time and settlement alignment."),
    ("PWA", "Progressive Web App: the installable web-app form of the Studio, including a manifest, home-screen icon and service worker."),
    ("API", "Application Programming Interface: a structured way for software to retrieve or exchange data."),
    ("CSV", "Comma-separated values: a plain-text tabular file format used for downloadable evidence and data contracts."),
    ("JSON", "JavaScript Object Notation: a structured text format used for manifests, assumptions and downloadable summaries."),
    ("LLM", "Large language model: an external generative language model. The deployed evidence analyst does not use one in this release."),
)

def _assumption_table() -> html.Table:
    rows = [
        ("Virtual portfolio", "User-selected wind / solar / mixed; 10–500 MW", "User scenario", "National V2 capacity-factor evidence is scaled to a transparent virtual portfolio."),
        ("Battery round-trip efficiency", "90% default", "User scenario", "Split symmetrically between charge/discharge efficiencies in the physical model."),
        ("State of charge (SOC) operating band", "10–90%", "Model assumption", "Used for sizing, reserve, market and service co-optimisation."),
        ("Probabilistic central interval", "P10–P90 / nominal 80%", "Model target", "Conditional residual quantiles plus prior-date conformal calibration."),
        ("Historical practical sizing", "50% restored starting SOC", "Model convention", "Daily restoration isolates repeatable firming capability."),
        ("Wholesale throughput cost", "£2/MWh", "Screening assumption", "Already embedded in the historical dispatch evidence used for market appraisal."),
        ("Reference capital expenditure (CAPEX)", "£25m", "User scenario", "Default 25 MW / 200 MWh screening case; not a supplier quote."),
        ("Fixed operating expenditure (OPEX)", "£0.5m/year", "User scenario", "Lifecycle screening input."),
        ("Asset life / discount / degradation", "15 y / 8% / 2%", "User scenario", "Default market and finance screening reference."),
        ("Availability", "95%", "User scenario", "Applied as operational uncertainty in Monte Carlo."),
        ("Debt structure", "60% debt, 6%, 10 y", "User scenario", "Constant-annuity finance-screening convention."),
        ("Tax / equity hurdle / debt service coverage ratio (DSCR)", "25% / 12% / 1.20×", "User scenario", "Simplified financing screen, not tax or lending advice."),
        ("Cycle life / reference depth of discharge (DoD)", "6,000 cycles / 80%", "User scenario", "Generic throughput-wear screening default, not a supplier warranty curve."),
        ("Calendar fade / replacement cost", "1.5%/y / £100/kWh", "User scenario", "Used only to derive screening SOH and marginal wear cost."),
        ("Stochastic market screen", "7 scenarios; Balancing Mechanism (BM) incidence seeded from bounded battery Balancing Mechanism Unit (BMU) evidence and editable", "User scenario", "Finite-scenario decision experiment; BM activation is not a BOA forecast."),
    ]
    return html.Table([
        html.Thead(html.Tr([html.Th("Input / convention"), html.Th("Default"), html.Th("Class"), html.Th("Interpretation")])),
        html.Tbody([html.Tr([html.Td(value) for value in row]) for row in rows]),
    ], className="guide-table")
def _source_table() -> html.Table:
    rows = [
        ("National Energy System Operator (NESO)", "Embedded wind/solar generation and capacity; National Demand Forecast; Grid Supply Point (GSP) boundaries", "Authoritative GB system / renewable context"),
        ("Elexon Insights", "System Price, Net Imbalance Volume, APX Market Index, GSP Group Take", "Settlement, wholesale-reference and regional-load evidence"),
        ("NESO Enduring Auction Capability (EAC)", "Quick Reserve (QR), Slow Reserve (SR), Balancing Reserve (BR) and Dynamic Response clearing results and Sell Orders", "Ancillary-service price and acceptance evidence"),
        ("European Centre for Medium-Range Weather Forecasts (ECMWF) IFS HRES via the V2 forecasting project", "Issue-time weather predictors at ten representative locations", "Base deterministic renewable forecast"),
        ("Department for Energy Security and Net Zero (DESNZ) Renewable Energy Planning Database (REPD)", "Operational wind/solar project capacity and location", "Spatial renewable-capacity proxy only"),
        ("Department for Energy Security and Net Zero (DESNZ) subnational electricity consumption", "Local Authority annual domestic/non-domestic electricity", "Spatial demand weights"),
    ]
    return html.Table([
        html.Thead(html.Tr([html.Th("Source"), html.Th("Used for"), html.Th("Role / boundary")])),
        html.Tbody([html.Tr([html.Td(value) for value in row]) for row in rows]),
    ], className="guide-table")


def _source_links() -> html.Ul:
    return html.Ul([
        html.Li(html.A("NESO Open Data", href="https://www.neso.energy/data-portal", target="_blank", rel="noopener noreferrer")),
        html.Li(html.A("Elexon Insights / Balancing Mechanism Reporting Service (BMRS) API", href="https://bmrs.elexon.co.uk/api-documentation", target="_blank", rel="noopener noreferrer")),
        html.Li(html.A("DESNZ Renewable Energy Planning Database", href="https://www.gov.uk/government/publications/renewable-energy-planning-database-monthly-extract", target="_blank", rel="noopener noreferrer")),
        html.Li(html.A("DESNZ subnational electricity consumption", href="https://www.gov.uk/government/collections/sub-national-electricity-consumption-data", target="_blank", rel="noopener noreferrer")),
        html.Li(html.A("European Centre for Medium-Range Weather Forecasts (ECMWF)", href="https://www.ecmwf.int/", target="_blank", rel="noopener noreferrer")),
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
        html.Li("Quantify 10th / 50th / 90th percentile (P10/P50/P90) uncertainty and size / prepare battery energy storage system (BESS) reserve."),
        html.Li("Simulate physical firming under explicit megawatt (MW), megawatt-hour (MWh), efficiency and state-of-charge (SOC) constraints."),
        html.Li("Optimise the same BESS across wholesale and National Energy System Operator (NESO) ancillary services."),
        html.Li("Translate operating evidence into lifecycle risk, net present value (NPV) and project-finance screens."),
        html.Li("Inspect spatial supply, underlying demand and net-load proxies across ten zones."),
    ], className="guide-workflow")
    terminology_intro = html.Div([
        html.H3("Terminology and abbreviations"),
        html.P(
            "The Studio uses the same pattern as the companion GB forecasting website: technical abbreviations are expanded in a compact terminology guide, while important first mentions in the interface also show the full words.",
            className="section-copy",
        ),
    ], className="guide-terminology-heading", id="terminology-abbreviations")
    core_terms = _details("Battery and forecasting terminology", [_definition_grid(CORE_TERMS)], True)
    market_terms = _details("GB market and system terminology", [_definition_grid(MARKET_TERMS)])
    finance_terms = _details("Investment and finance terminology", [_definition_grid(FINANCE_TERMS)])
    data_terms = _details("Data, spatial and deployment terminology", [_definition_grid(DATA_TERMS)])
    probabilistic = _details("1. Forecast evidence and probabilistic percentiles (P10/P50/P90)", [
        html.P("The deterministic V2 forecast remains the scheduled renewable export. The probabilistic layer is a statistical post-processor of V2 errors; it does not replace the point model and is not an ECMWF ensemble forecast.", className="section-copy"),
        _equation("Virtual portfolio", r"\widehat{CF}_{p,t}=w\widehat{CF}_{wind,t}+(1-w)\widehat{CF}_{solar,t}", "w is the user-selected wind capacity share. The same mixing rule is used for observed capacity factor during historical calibration."),
        _equation("Residual target", r"r_t=CF_{p,t}-\widehat{CF}_{p,t}", "The quantile regressors learn the conditional distribution of V2 out-of-sample residuals from issue-time-known predictors."),
        _equation("Conditional quantiles", r"P_q(t)=clip\left(\widehat{CF}_{p,t}+\widehat{Q}_q(r_t\mid x_t)\pm c,0,1\right)", "Separate q=0.10, 0.50 and 0.90 regressors are fitted. The conformal correction c expands only the outer interval; P50 is not shifted."),
        _equation("Conformal score", r"s_i=max(\widehat{P}_{10,i}-y_i,\;y_i-\widehat{P}_{90,i},\;0)", "The rolling correction uses only earlier observed days in locked evaluation. Production corrections are frozen by 5%-step wind-share after the locked metrics are recorded."),
        html.P(f"Locked 50/50 evidence: {mixed['observed_p10_p90_coverage_pct']:.1f}% P10–P90 coverage over {int(mixed['days'])} days; mean interval width {mixed['mean_p10_p90_width_cf']:.4f} CF. The prior Stage B 180-day residual envelope gives {comparison['old_directional_residual']['coverage_pct']:.1f}% coverage on the same period.", className="section-copy"),
    ], True)
    battery = _details("2. Battery physics, firming and state of charge (SOC)", [
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
    market = _details("4. Wholesale, imbalance and National Energy System Operator (NESO) service optimisation", [
        html.P("The market layers use one physical battery. Wholesale arbitrage, renewable firming and ancillary-service commitments compete for the same MW, MWh and SOC; their values are not added as independent revenue streams.", className="section-copy"),
        _equation("Wholesale arbitrage", r"\max\sum_t \left[\pi_t(P^{dis}_t-P^{ch}_t)\Delta t-c_{thr}(P^{dis}_t+P^{ch}_t)\Delta t\right]", "π is the relevant wholesale price/reference and c_thr is the transparent throughput-cost assumption. Perfect-information and forecast-selected strategies are reported separately."),
        _equation("Shared ancillary nameplate", r"\sum_{s\in S_t}P^{service}_{s,t}\le P_{BESS}", "The conservative generic service framework does not sell the same physical MW into multiple simultaneous ancillary products."),
        _equation("Directional headroom", r"P^{dis}_t+P^{up\ service}_t\le P_{BESS},\qquad P^{ch}_t+P^{down\ service}_t\le P_{BESS}", "Upward services reserve discharge headroom; downward services reserve charging headroom. Service-specific energy guards also protect SOC."),
        html.P("Quick Reserve, Slow Reserve and Dynamic Response use their actual EAC delivery windows. Balancing Reserve is enabled only under an explicit BM-eligibility scenario. Utilisation payments and performance penalties remain outside the current availability-value screen.", className="section-copy"),
    ])

    acceptance = _details("5. Issue-time bids and auction acceptance", [
        html.P("The issue-time service screen removes service-price perfect foresight. Clearing prices are forecast from earlier dates, capacity is chosen before delivery, and an opportunity-cost bid floor is calculated from forecast wholesale value.", className="section-copy"),
        _equation("Opportunity-cost bid", r"b_s=\frac{V^{wholesale}_{base}-V^{wholesale}_{with\ service\ s}}{MW_s\times h_s}", "The bid floor reflects forecast wholesale value displaced by reserving battery capacity for the ancillary contract."),
        _equation("Acceptance-calibrated expected MW", r"E[MW^{acc}_s]=min(MW^{offer}_s,MW^{cleared}_s)\times \hat p^{acc}_s\times I(b_s\le \pi^{clear}_s)", "The acceptance probability is estimated from earlier comparable NESO EAC parent orders. Realised clearing price/volume enter only in ex-post scoring."),
        html.P(f"The non-BM issue-time screen annualises to about £{stage13['annualised_acceptance_calibrated_total_gbp']/1e6:.2f}m/year on 60 eligible May–Jun 2026 dates. This is counterfactual expected-acceptance evidence, not a claim that the virtual asset actually cleared those historical auctions.", className="section-copy"),
    ])
    economics = _details("6. Risk, lifecycle value and Monte Carlo", [
        html.P("The Studio keeps three economic evidence levels separate: Stage 6 consequence-value screening, Stage 10 market-backed wholesale evidence, and ancillary-service upside/calibrated screens. None is labelled bankable revenue.", className="section-copy"),
        _equation("Lifecycle NPV", r"NPV=-C_0+\sum_{y=1}^{N}\frac{V_1(1-g)^{y-1}-O_y-R_y}{(1+r)^y}", "C0 is upfront CAPEX; V1 is year-one operating value; g is annual degradation; O is OPEX; R is optional replacement cost; r is the discount rate."),
        _equation("Benefit-cost ratio", r"BCR=\frac{PV(operating\ benefit)}{PV(CAPEX+OPEX+replacement)}", "BCR is a screening ratio. The app also reports break-even annual operating value and maximum CAPEX compatible with zero NPV."),
        _equation("Tail-loss convention", r"Loss=-NPV,\qquad CVaR_{95\%}=E[Loss\mid Loss\ge VaR_{95\%}]", "Monte Carlo resamples contiguous historical day blocks and varies transparent cost/availability/degradation assumptions. P10/P50/P90 are distribution quantiles, not confidence intervals on a fitted mean."),
    ])

    finance = _details("7. Project-finance screening", [
        html.P("The finance layer converts operating evidence into a simplified project/debt/equity screen. The conservative finance base remains the forecast-selected wholesale evidence; the issue-time and perfect-information service cases are shown as separately labelled ancillary-service cases.", className="section-copy"),
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
            html.Li("Use the market-backed investment and project-finance sections for screening. Change CAPEX/OPEX/debt/tax assumptions visibly and treat outputs as pre-feasibility evidence."),
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
            html.Li("P10/P50/P90 are conditional statistical quantiles calibrated from V2 residual evidence, not ECMWF ensemble-member probabilities."),
            html.Li("APX Market Index is a public short-term wholesale reference and is not relabelled as a licensed day-ahead auction price."),
            html.Li("The service upper bound uses perfect information; the issue-time screen is acceptance-calibrated counterfactual evidence, not actual historical asset revenue."),
            html.Li("The ancillary-service model excludes utilisation/performance settlement that is not supported by the current evidence contract."),
            html.Li("Spatial zones are reconciled allocation proxies; no distribution-network power flow, connection study or municipal demand metering is claimed."),
            html.Li("Financial outputs are pre-feasibility screens and not investment, tax, legal or lending advice."),
        ], className="guide-limit-list"),
    ])
    reproducibility = _details("13. Validation and reproducibility", [
        html.Ul([
            html.Li("Historical renewable evidence is out-of-sample V2 OOF plus locked-test output; target-day realised values are not used in future/issue-time decisions."),
            html.Li("Probabilistic model selection uses development OOF only. Locked Apr–Jun 2026 metrics are recorded before the production conformal-width calibration is frozen."),
            html.Li("Battery equations, reserve rules, market value, service stacking, acceptance calibration and finance equations have automated tests."),
            html.Li("Market/acceptance evidence keeps explicit issue-time versus realised-scoring boundaries and stores compact manifests/checksums."),
            html.Li("The forecast handoff validates the imported V2 schema, period completeness, target date and freshness before atomic publication; the prior valid bundle is archived before replacement."),
            html.Li("The app is presentation/inference. Long-running evidence builders and model training are reproducible scripts outside normal page callbacks."),
            html.Li("DST settlement days are handled as 46/48/50 periods; incomplete evidence is rejected or explicitly labelled partial where appropriate."),
        ], className="guide-limit-list"),
    ])

    asset_workspace = _details("14. Asset / site workspace", [
        html.P("A saved asset is browser-local technical scenario metadata: name, location label, MW, duration, grid import/export limits and SOH. Saving a site does not create local forecast or metering evidence.", className="section-copy"),
        _equation("Nameplate and available energy", r"E_{nameplate}=P_{BESS}h,\qquad E_{available}=E_{nameplate}\times SOH", "Grid import/export limits are retained explicitly; the generic symmetric BatteryConfig uses the conservative minimum of charge/discharge/site power when a single MW limit is required."),
    ])
    degradation = _details("15. Degradation and state of health (SOH) screening", [
        html.P("The degradation layer converts transparent cycle-life, DoD, calendar-fade and replacement-cost assumptions into an indicative annual SOH trajectory and marginal throughput wear cost.", className="section-copy"),
        _equation("Equivalent full cycles", r"EFC=\frac{Throughput_{charge+discharge}}{2E_{usable}}", "Throughput counts charge plus discharge energy. This is a generic energy-throughput measure, not chemistry-specific rainflow counting."),
        _equation("Marginal wear cost", r"c_{wear}=\frac{Replacement\ cost}{2E_{usable}\,DoD_{ref}\,N_{cycles}}", "The result is carried into the stochastic dispatch screen as an incremental £/MWh throughput penalty."),
    ])
    stochastic = _details("16. Stochastic wholesale + Balancing Mechanism screen", [
        html.P("One pre-delivery wholesale schedule and one set of BM upward/downward reserve offers are selected before a finite realised scenario is known. Scenario-wise SOC includes only the BM activations accepted in that scenario.", className="section-copy"),
        _equation("Risk-adjusted objective", r"\max\;E[V]-\lambda\,CVaR_{\alpha}(Loss)", "All scenarios share the same offered MW and base schedule. SOC and terminal-restoration cost are checked separately in each scenario."),
        html.P("The generic UI's BM activation probabilities and activation values are user assumptions. They are not BOA acceptance probabilities, utilisation instructions or BM settlement forecasts.", className="section-copy"),
    ])
    analyst = _details("17. Explainable evidence analyst", [
        html.P("Ask the Studio performs deterministic natural-language evidence retrieval over curated current outputs and scenario stores. It returns the supporting evidence keys, provenance and limitations with each answer.", className="section-copy"),
        html.P("No external generative model or web search is used inside this release. An unsupported question returns a low-confidence evidence-gap response instead of inventing an answer.", className="section-copy"),
    ])

    competitive = _details("18. Product structure and release history", [
        html.P("Release A restructures the Studio around Overview, Assets, Forecast & Risk, Markets, Investment and Evidence. Scenario A/B snapshots are browser-local and share links serialise the principal scenario controls into the URL.", className="section-copy"),
        html.P("Release B adds point-of-connection import/export limits, ramp limits, auxiliary load, grid-charging permission, daily-cycle and annual-throughput warranty screens, plus co-location scenario fields. These are user constraints, not a connection study.", className="section-copy"),
        _equation("Connection-limited capability", r"P^{dis}_{site}=min(P_{BESS},P_{export}),\qquad P^{ch}_{site}=min(P_{BESS},P_{import})", "Grid charging can be disabled explicitly; SOH scales available energy but does not invent a chemistry-specific power derate."),
        _equation("Warranty throughput cap", r"E^{yr}_{throughput}\le min(365\times 2E_{usable}N_{cycle/day},\ E^{warranty}_{annual})", "This is a transparent operating envelope used for screening."),
        html.P("Release C builds a bounded battery-BMU evidence set from Elexon BM Unit reference names, BOD submissions and BOALF accepted instructions. The stochastic screen uses the observed directional activation incidence as its default, while keeping the control editable.", className="section-copy"),
        html.P("The current BM diagnostic is not a causal acceptance model: the frozen sample is recent, identity is based on explicit battery/storage/BESS unit names, and the fitted logistic result is an in-sample diagnostic only.", className="section-copy"),
        html.P("Release D aggregates browser-saved assets and compares technical capability using one reference-normalised value basis. Reference-scaled value is not a site revenue forecast because local prices, grid constraints, availability, metering and bidding behaviour are not inferred.", className="section-copy"),
    ])

    assurance = _details("19. Model assurance and interpreting negative net present value (NPV)", [
        html.P(
            "A negative NPV is treated as an economic outcome that requires checking, not as automatic proof that the model is correct. The Studio separately reports calculation integrity and investment outcome.",
            className="section-copy",
        ),
        _equation(
            "Independent net present value (NPV) reconciliation",
            r"NPV=PV(operating\ value)-CAPEX-PV(fixed\ OPEX)-PV(replacement)",
            "The public result is independently recalculated from the annual evidence series and checked against the detailed yearly cash-flow output.",
        ),
        html.Ul([
            html.Li("Daily operating evidence must have one finite value per unique date before it can be annualised."),
            html.Li("The NPV accounting identity is recalculated independently from the application result."),
            html.Li("Break-even annual value and maximum zero-NPV CAPEX are back-solved and checked."),
            html.Li("Revenue and CAPEX monotonicity are checked: more revenue must increase NPV and more CAPEX must reduce it."),
            html.Li("Project-finance checks reconcile the annual cash-flow NPV, debt principal, closing balance, tax signs and DSCR rows."),
        ], className="guide-limit-list"),
        html.P(
            "A calculation PASS does not validate the commercial completeness of revenue, CAPEX, OPEX, warranties, taxes or financing. The current values remain transparent pre-feasibility assumptions and public-data evidence, not bankable forecasts.",
            className="section-copy",
        ),
    ])

    return html.Section([
        html.Div([
            html.Div("TECHNICAL TRANSPARENCY", className="eyebrow"),
            html.H2("Models, Data & Validation Guide"),
            html.P("A practical manual for the Studio: what each layer calculates, its equations, evidence, assumptions, references and limits.", className="section-copy"),
        ], className="guide-heading"),
        html.Div(workflow, className="guide-workflow-wrap"),
        terminology_intro, core_terms, market_terms, finance_terms, data_terms,
        probabilistic, battery, reserve, market, acceptance, economics, finance,
        spatial, controls, provenance, assumptions, limits, reproducibility,
        asset_workspace, degradation, stochastic, analyst, competitive, assurance,
    ], id="models-data-validation-guide", className="download-section methodology-guide")
