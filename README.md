# Renewable Flexibility Studio

A standalone, interactive decision-support prototype that converts historical wind and solar forecast deviations into transparent battery-firming and storage-sizing results.

The site is deliberately independent from the earlier GB renewable forecasting website. It does not import that dashboard, open it in a tab, use an iframe, or require it to be awake. The two projects exchange only compact, versioned data bundles.

## What the current V2-backed prototype does

A user can:

- select a wind, solar or mixed virtual renewable portfolio;
- change portfolio capacity and the wind/solar mix;
- change battery power, duration, initial state of charge and efficiency;
- simulate a deployable **reactive firming** strategy for any of 450 out-of-sample historical days;
- inspect renewable delivery, charge/discharge and state of charge;
- compare forecast error before and after the battery;
- inspect a leakage-safe rolling **80% prediction interval** and see which historical periods fell outside the expected range;
- size a battery for **future operation** using a 2,541-cell stability grid across 450 out-of-sample days, with 80/90/95% firming and reliability targets;
- inspect the latest V2 **forecast-day** renewable schedule with a directional empirical uncertainty range;
- inspect a 10-zone weather-informed spatial allocation of the GB wind/solar forecast, plus a sourced spatial underlying-demand/net-load proxy reconciled to NESO National Demand;
- carry the selected future battery into an operational reserve planner that checks current SOC, calculates a safe starting-SOC band, recommends only the minimum necessary pre-day adjustment, and identifies critical downside/upside reserve windows;
- place that schedule in real GB grid context using the official half-hourly NESO National Demand Forecast served by Elexon Insights;
- translate each historical forecast deviation into a BSC-style imbalance volume and official Elexon System-Price cashflow, before and after battery firming;
- inspect gross imbalance-settlement exposure separately from signed settlement cashflow, without labelling exposure reduction as profit;
- identify power-limited and energy-limited periods;
- search a controlled 1h/2h/4h battery grid for the smallest tested configuration meeting a target;
- download every half-hourly calculation as CSV;
- run a separate 450-day **continuous-SOC** benchmark and extended storage-duration diagnostic from the command line.

The application now uses a **450-day out-of-sample V2 bundle** from 1 April 2025 to 30 June 2026: 360 expanding-window out-of-fold development days plus 90 locked-test days. The original one-day file is retained only as a compact unit-test fixture.

## Product boundary

This is a **virtual portfolio-level firming benchmark**. It is not:

- a site-specific battery design;
- a physical battery capable of correcting all GB renewable output;
- a live electricity-trading execution system or guaranteed revenue model;
- an investment recommendation;
- direct control software for a battery management system.

National forecast and actual capacity factors are scaled to a user-selected virtual portfolio. The value is comparative: it shows how battery power, duration, efficiency and starting SOC affect the ability to absorb forecast deviations.

## Architecture

```text
Versioned historical forecast bundle
                ↓
        adapters/forecast_data.py
                ↓
        engine/portfolio.py
                ↓
        engine/battery.py
                ↓
   engine/metrics.py + engine/sizing.py
                ↓
        standalone Dash interface
```

The `engine/` package contains no Dash code. This makes the equations independently testable and leaves a clean path to a future API or alternative frontend.

## Reactive firming strategy

For each half-hour:

- actual output above forecast creates a renewable surplus and the battery charges;
- actual output below forecast creates a renewable deficit and the battery discharges;
- charge/discharge power is limited by battery MW;
- energy movement is limited by SOC headroom and round-trip efficiency;
- grid charging and simultaneous charge/discharge are excluded;
- the strategy sees the current deviation but has no future settlement-period knowledge.

Battery energy capacity is:

```text
energy capacity (MWh) = power (MW) × duration (hours)
```

## Forecast uncertainty

The historical generation chart includes a nominal **80% rolling prediction interval** around the point forecast. For each selected day, the interval is calibrated only from earlier out-of-sample forecast residuals, using a 90-day lookback and forecast-level-local residual matching. The selected day's actual output is never used to construct its own band; actuals are used only afterward to assess coverage and mark periods outside the expected range.

Backtesting over eligible dates gives about **80.6% wind**, **77.0% solar** and **79.9% mixed** overall coverage. On the locked Apr–Jun 2026 period, coverage is **80.7%**, **81.1%** and **80.8%**, respectively. This is a residual-based uncertainty band, not yet an ECMWF weather-ensemble or dedicated P10/P50/P90 probabilistic forecast.

## GB imbalance-settlement context

For historical dates, the point forecast is treated as an illustrative contracted/scheduled renewable export. The portfolio imbalance is actual minus scheduled energy for each 30-minute settlement period. The Studio joins the matching official Elexon System Price and Net Imbalance Volume and calculates the corresponding BSC-style signed settlement cashflow. Positive cashflow means a payment by the virtual portfolio; negative means a receipt to it.

The UI also reports **gross cash-out exposure**, defined as the absolute size of those settlement cashflows. This is a risk/volatility measure, not profit or avoided cost. The separate Risk & Value layer monetises physical exposure only through visible user/scenario assumptions; it does not relabel System Price exposure as battery revenue.

The frozen Elexon archive covers the same 450 target days and all 21,600 half-hours as the V2 forecast-error bundle.

## Future battery sizing benchmark

This is now the main design layer. The practical sizing mode assumes a **grid-connected reserve BESS**: SOC is restored to 50% before each operating day, then the battery reacts only to renewable forecast deviations during that day. Grid energy used to restore SOC is measured explicitly and is not treated as free. Intraday grid charging remains excluded.

The design grid tests 11 power levels (5–100% of portfolio MW) and 11 durations (1–72 h) for every 5% wind-share step. A candidate must meet the selected overall firming target and the selected percentage-of-days reliability target in both Apr 2025–Mar 2026 and Apr–Jun 2026. The minimum-energy tested candidate is selected, then lower MW and duration break ties. Because the later period has already been examined in this project, it is described as a second-period stability check, not a new sealed battery-sizing holdout.

For the default **90% firming / 90% of days** gate on a 100 MW portfolio:

| Portfolio | Minimum stable tested design | Development overall / days | Apr–Jun 2026 overall / days |
|---|---:|---:|---:|
| Solar | 25 MW / 150 MWh (6 h) | 95.4% / 93.9% | 96.1% / 91.1% |
| Mixed 50/50 | **25 MW / 200 MWh (8 h)** | **96.3% / 93.3%** | **97.5% / 95.6%** |
| Wind | 15 MW / 360 MWh (24 h) | 95.1% / 91.1% | 98.3% / 95.6% |

Power and energy scale linearly with portfolio nameplate capacity; duration and percentage performance do not. Mixed-portfolio evidence is precomputed at every 5% wind-share value supported by the UI. Durations above 12 h are labelled **long-duration storage territory** rather than conventional short-duration BESS.

## Forecast-day reserve and SOC planning

The Stage B planner carries the selected future design into the latest V2 forecast day. It builds an asymmetric empirical **q10–q90 signed-residual range** using only earlier out-of-sample dates, then converts the distance below/above the scheduled export into downward discharge-reserve and upward charging-headroom requirements.

Reserve energy is evaluated over a rolling horizon equal to the installed battery duration. These requirements define an energy-feasible starting-SOC band. If the operator-entered current SOC is already inside that band, the planner recommends **hold current SOC**. If it is outside, the planner moves only to the nearest safe boundary and reports the grid energy needed for that preparation. If no starting SOC can cover both directional energy requirements simultaneously, it does not force an unvalidated compromise: it holds current SOC and reports the reserve-coverage shortfall.

For the default 100 MW 50/50 portfolio and 25 MW / 200 MWh (8 h) design, the current 3 September forecast gives a safe starting-SOC band around **33.6–76.6%**; therefore a current 50% SOC requires no adjustment. The largest rolling downside requirement is about **44.8 MWh** and the largest upward headroom requirement about **28.3 MWh**. This is a reserve-readiness calculation, not a simulated future dispatch trajectory.

A formal prior-data-only backtest covers 420 eligible dates. At a 50% baseline SOC, the solar and mixed designs remain inside their calculated safe bands on all eligible dates, so the conservative policy makes no unnecessary adjustments. The directional interval achieves about **88.7% solar, 83.3% mixed and 81.9% wind coverage** on Apr–Jun 2026. Wind is explicitly flagged when its 24 h two-sided energy envelope cannot fit inside the installed usable SOC range.


## Spatial renewable allocation zones

The forecast-day view now exposes ten indicative spatial zones aligned with the V2 weather sampling locations: Inverness, Edinburgh, Newcastle, Manchester, Leeds, Birmingham, Norwich, Cardiff, Bristol and London. The national V2 wind/solar forecast remains authoritative. Each half-hour is allocated across the ten zones using **DESNZ REPD operational wind/solar capacity as a fixed spatial proxy** multiplied by the corresponding issue-time V2 weather signal, then normalised so the ten zones sum exactly back to the national wind and solar MW totals.

REPD is used only as a spatial weighting proxy: it tracks projects above 150 kW and had a 1 MW threshold before 2021, so it is not treated as a complete embedded-capacity census. The Studio therefore labels these outputs as **spatial allocation / flexibility zones**, not independently trained or observed city-generation forecasts. The city-level BESS card is a proportional allocation of the national Stage A design, not independent local sizing; local forecast-error histories and distribution-network constraints are not available at this resolution.

The same ten zones now have a separate **underlying-demand and net-load proxy**. DESNZ 2024 local-authority electricity consumption sets annual spatial weights; Elexon CDCA-I029 GSP Group Take history supplies regional within-day shape. Because embedded wind/solar suppress NESO National Demand, the national underlying-demand proxy is constructed as `NDF + V2 embedded wind + V2 embedded solar`. It is spatially allocated and then the identical zone embedded-renewable forecast is subtracted. Consequently, zone underlying demand sums to the national underlying proxy, while the ten zone net loads sum back exactly to NESO National Demand every half-hour. This is modelled system-zone demand, not measured municipal-city demand.

The GSP shape model is trained only through March 2026 for its Apr-Jun 2026 validation check. On 1,267 GSP-days it reduces mean within-day profile error from 0.415 to 0.268 percentage points of daily energy, a **35.4% improvement versus a flat half-hour profile**.

The GB demand panel also accepts a contiguous **remaining-day** NESO forecast after delivery has started. A partial series is shown with an explicit warning instead of being rejected as an incomplete day.

## Risk & Value decision layer

Stage 6 converts the 450-day BESS firming evidence into a transparent pre-feasibility intervention decision. It reports baseline/residual physical exposure, monetised risk reduction, NPV, BCR, simple payback, break-even consequence value, maximum CAPEX, CAPEX/consequence sensitivity and a risk-value frontier. Monetary inputs are explicit scenario assumptions, not observed market revenues or bankable project costs.

Stage 6B adds complete-day block-resampled Monte Carlo with uncertainty in consequence value, CAPEX, OPEX, battery availability and degradation. It reports P10/P50/P90 NPV, probability of negative NPV, 95% VaR/CVaR using `investment loss = -NPV`, probability of failing the selected firming/reliability gate, and named downside stress cases. The default 100 MW 50/50, 25 MW / 200 MWh case is economically negative under the illustrative default assumptions, while smaller batteries can have better NPV but fail the technical 90/90 gate.

## GB market-linked optimisation

Stage 9 connects the battery evidence to real public GB market references. The repository now carries a 450-day / 21,600-period Elexon APX Market Index archive aligned to the V2 forecast-error and System Price evidence. Market Index Price is explicitly labelled **short-term wholesale market reference**, not a day-ahead auction price.

Three ex-post upper-bound strategies are separated: settlement-aware firming using realised System Price plus priced SOC restoration; perfect-foresight wholesale arbitrage using Market Index Price; and a co-optimiser that shares one physical battery MW/SOC/throughput budget between firming and arbitrage. Under the frozen default 100 MW 50/50, 25 MW / 200 MWh case and a £2/MWh scenario throughput cost, annualised values are about **-£0.061m reactive firming**, **£0.270m settlement-aware firming**, **£1.904m arbitrage-only**, and **£2.049m co-optimised**. These are realised-price upper bounds, not deployable revenue forecasts.

A separate adapter validates user-supplied licensed day-ahead prices with publication timestamps and issue-time cutoffs, so an authorised Nord Pool/EPEX feed can be added later without changing the optimisation architecture.

The pre-delivery price forecast is now operationalised as an atomic bundle pipeline. A scheduled GitHub Actions job builds a candidate from prior APX days, validates period count/target/checksum, archives the previous valid bundle and publishes only after validation. The Studio labels the result **LIVE**, **RECONSTRUCTED** or **STALE** and exposes fallback status instead of silently using an invalid refresh.

The forecast-based market layer now removes price perfect foresight using an expanding ridge forecast trained only on earlier Market Index settlement dates. Across 420 eligible days, price MAE is **£20.0/MWh**, 11.2% better than the previous-observed-same-period baseline. A 25 MW / 200 MWh forecast-selected arbitrage schedule captures about **60.0%** of the perfect-information upper bound overall and **63.4%** on Apr-Jun 2026. Preserving the Stage B SOC reserve corridor reduces capture to **49.6%**, quantifying the market opportunity cost of maintaining renewable-risk headroom.

The current 3 September forecast-day market bundle is explicitly marked as an **as-if reconstruction generated after delivery began**, while still excluding all target-day Market Index observations. Future automation should generate this bundle before the target day starts.

### Quick Reserve availability stacking

The first ancillary-service layer adds NESO Positive/Negative Quick Reserve using real EAC clearing prices while keeping utilisation separate. PQR/NQR are whole-MW commitments that split the same BESS nameplate, and wholesale scheduling plus reserve share one SOC/power trajectory. Under the default two-window energy guard, the Apr–Jun 2026 regime annualises to about **£2.38m arbitrage-only**, **£1.35m QR availability-only** and **£3.13m arbitrage + QR**. Naively adding the first two would overstate value by about **£0.61m/yr**.

The full three-use optimiser then lets renewable firming compete with wholesale arbitrage and Quick Reserve for the same battery. It annualises to about **£3.27m/yr**, versus **£2.51m/yr** for firming + arbitrage without QR, while retaining about **37.0%** mean renewable forecast-error reduction. Adding QR-only independently to firming + arbitrage would overstate the triple-stack value by about **£0.60m/yr**. These are perfect-information, price-taker screening values for that 90-day regime, not guaranteed auction acceptance or earned revenue.

A prior-date-only QR clearing-price forecast now turns that upper bound into a pre-delivery **capacity-allocation signal**. On the 90 locked Apr–Jun 2026 dates it retains about **93.1%** of perfect-information QR-only availability value (**£1.26m/yr** under the same price-taker scoring assumption), versus **88.0%** for a previous-same-product/period baseline. This is deliberately not called acceptance-adjusted revenue: an aggregate diagnostic over **2.06 million** Apr–Jun QR Sell Orders finds that `bid price ≤ clearing price` has only **28.9% precision** for actual execution, so the project does not invent a bid-acceptance probability from clearing price alone.


## Market-backed investment case (Stage 10)

Stage 10 connects the pre-delivery wholesale operating evidence to lifecycle investment appraisal. The core case uses the **realised value of the 420-day forecast-selected APX Market Index schedule**, not the Stage 6 abstract consequence-value assumption. A separate reserve-aware case uses the Stage B SOC-corridor-constrained wholesale schedule. Quick Reserve is kept as an **Apr–Jun aligned price-taker upside sensitivity** and is excluded from the probabilistic base until asset-specific EAC bid acceptance is identified.

Under the illustrative default assumptions of £25m CAPEX, £0.5m/year fixed OPEX, 15-year life, 8% discount rate and 2% annual revenue degradation, the 420-day wholesale case provides about **£1.13m/year** operating value, **NPV ≈ -£20.6m** and **BCR ≈ 0.30**. The year-one break-even operating value is about **£3.82m/year** and the maximum upfront CAPEX consistent with zero NPV is about **£4.42m**. The aligned Apr–Jun wholesale + QR price-taker upside raises the screening operating value to about **£2.77m/year**, but remains negative at roughly **-£8.0m NPV** under the same cost assumptions.

A 5,000-run reference Monte Carlo resamples contiguous 7-day blocks of realised forecast-selected daily market value and varies CAPEX, fixed OPEX, availability and degradation. The frozen default gives **P10/P50/P90 NPV ≈ -£24.18m / -£21.46m / -£19.00m**, with 95% CVaR loss about **£25.42m**. Quick Reserve is deliberately excluded from these draws. These are pre-feasibility screening results, not a bankable valuation.

### NESO multi-service availability stacking

Stage 11 generalises the ancillary-service engine across the current NESO EAC products: Quick Reserve (PQR/NQR), Slow Reserve (PSR/NSR), Dynamic Containment/Moderation/Regulation and, under an explicit BM-eligibility switch, Balancing Reserve (PBR/NBR). All products share the same physical battery MW, SOC and energy-headroom constraints. Dynamic Response remains a real 4-hour EFA commitment and the current Positive Slow Reserve linked-window rule is enforced with identical MW across each linked local-time block.

The frozen Apr-Jun 2026 default 25 MW / 200 MWh screen annualises to about **£3.38m/yr** for firming + wholesale + Quick/Slow Reserve, **£4.80m/yr** for the full non-BM stack, and **£4.82m/yr** when BM eligibility also enables Balancing Reserve. Dynamic Regulation supplies about **£2.41m/yr** of availability value in the non-BM screen. Renewable forecast-error reduction falls from about **36.7%** in the QR+SR case to **30.1%** in the broader non-BM stack, quantifying the opportunity cost of reserving more battery capacity for ancillary markets.

These are **perfect-information, price-taker availability screening values**, not earned revenue forecasts. Utilisation instructions/payments, performance penalties and asset-specific bid acceptance are excluded. The current generic release also uses a conservative rule that one physical MW cannot be sold into multiple simultaneous ancillary products.

## Issue-time multi-service strategy (Stage 13)

Stage 13 removes Stage 11 service-price perfect foresight. It forecasts clearing prices for all 12 EAC products from earlier service dates only, uses the Stage B SOC reserve corridor and prior-date wholesale-price forecast, and chooses service capacity before delivery. A standalone wholesale opportunity-cost calculation sets each ancillary bid floor. Acceptance is estimated from earlier NESO EAC Sell Orders using a hierarchy of comparable non-looped parent orders; participant and unit identity fields are not retained.

Across the **60 eligible May-Jun 2026 dates** (24 June is excluded because it is absent from the V2 historical forecast-error bundle), the non-BM strategy annualises to about **£2.22m/yr**, comprising about **£1.05m/yr realised frozen-wholesale value** plus **£1.17m/yr acceptance-calibrated ancillary availability value**. This is about **47.9%** of the matching Stage 11 perfect-information upper bound and adds about **£1.08m/yr** versus reserve-aware wholesale only. The BM-eligible screen is slightly lower at about **£2.21m/yr**, because Balancing Reserve displaces other opportunities without enough calibrated acceptance value to compensate.

The 12-product clearing-price forecast has **£1.65/MW/h MAE**, 13.1% better than a previous-same-product/window lag across May-Jun. The acceptance calibration is validated on **514,583 held-out May/June standalone-parent orders** and improves Brier score by **22.8%** versus a product-average acceptance baseline. This remains a counterfactual expected-acceptance screen: the exact merit-order outcome for a battery that was not actually submitted to the historical auction is unknowable, and utilisation/performance payments remain excluded.

## Project-finance screening (Stage 12)

Stage 12 converts the market-backed operating evidence into a transparent debt/equity screening model. The finance base remains the Stage 10 prior-date forecast-selected wholesale strategy. Stage 13 is now shown as the intermediate issue-time/acceptance-calibrated ancillary screen, while Stage 11 remains the perfect-information upper bound. Neither ancillary case is treated as bankable contracted revenue.

Under the illustrative default assumptions of £25m CAPEX, £0.5m/year fixed OPEX, 60% debt, 6% debt interest, 10-year debt tenor, 25% corporation-tax scenario, 12% equity hurdle, 15-year asset life and 2% annual revenue degradation, the wholesale base gives project NPV about **-£20.9m**, equity IRR about **-31%**, minimum DSCR about **0.22x** and LLCR about **0.27x**. The Stage 13 non-BM calibrated case improves to project NPV about **-£13.1m**, equity IRR about **-10.4%**, minimum DSCR about **0.66x** and LLCR about **0.75x**, but it still fails the financing screen. The Stage 11 non-BM perfect-information upper bound reaches project NPV about **+£3.3m**, equity IRR about **15.7%**, minimum DSCR about **1.61x** and LLCR about **1.79x**.

The finance Monte Carlo resamples the Stage 10 daily wholesale evidence only and varies CAPEX, fixed OPEX, availability, degradation and debt rate. The tax layer is deliberately simplified: user-defined corporation tax and capital-allowance assumptions, interest deductibility and no tax-loss carry-forward. It is a project-finance screening tool, not tax, accounting, lending or investment advice.

## Renewable-only continuous-SOC stress test

For a 100 MW virtual portfolio with a 25 MW / 50 MWh battery, 90% round-trip efficiency, 10–90% SOC limits and no grid charging, continuous operation absorbs about **33.5% of wind**, **50.2% of solar** and **44.4% of 50/50 mixed** absolute forecast-deviation energy. SOC ends at its minimum bound, showing that energy availability and conversion losses matter across long horizons.

The initial 1h/2h/4h sizing grid does **not** reach an 80% long-run target. With the standard 50% starting SOC, the first tested 80% solutions use about **1,800 MWh wind**, **400 MWh solar** and **800 MWh mixed**. A conservative sensitivity that starts at the 10% minimum SOC removes the one-time initial-energy reserve: wind and solar remain about **1,800 MWh** and **400 MWh**, while mixed rises modestly to **900 MWh**. These are virtual benchmark results, not site-design recommendations.

## Run locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m pytest -q
python app.py
```

Open `http://127.0.0.1:8050`.

## Deploy separately on Render

1. Create a new GitHub repository for this directory.
2. Push the project to the default branch.
3. Create a new Render Blueprint or web service from that repository.
4. Render reads `render.yaml` and starts `gunicorn app:server`.

The resulting service has its own URL and deployment lifecycle. It does not call the earlier website.

## Data replacement contract

The application reads `data/historical_backtest.csv`. The adapter accepts CSV or Parquet and requires:

```text
settlement_date
settlement_period
valid_time_utc
wind_cf
solar_cf
wind_pred_cf
solar_pred_cf
```

A valid GB target day has 46, 48 or 50 settlement periods. Duplicate or incomplete days are rejected.

## Product interface direction

Stage 17 moves the Studio from a generic dashboard aesthetic toward a compact GB power/quant decision workspace. The interface uses a six-step decision path (Forecast → Uncertainty → Reserve → Market → Value → Evidence), tighter information density, restrained square-edged panels, tabular numerics and clearer hierarchy for recommendations and validation state. Libraries.dev was used as a reference for contemporary interaction patterns, but no React-only visual dependency is introduced into the Dash runtime. Decorative effects are deliberately limited so the analytical product remains credible and fast.

## Roadmap

### Stage 17 - product interface refinement (implemented)

- decision-led navigation and stronger analytical hierarchy;
- reduced generic gradient/pill/card styling;
- denser desktop layout and improved two-column mobile KPI presentation;
- explicit validated-release status and methodology path;
- no change to validated modelling engines or evidence contracts.

### Stage 14 - probabilistic uncertainty (implemented)

- mix-aware conditional P10/P50/P90 renewable forecast intervals around the frozen V2 schedule;
- conformal calibration using development-only evidence, with locked Apr-Jun 2026 validation;
- direct comparison against the prior rolling residual envelope;
- forecast-day reserve/headroom and safe-SOC planning driven by P10/P90 tails.

### Stage 16 - validated cross-repository forecast handoff (implemented)

- schema/period/target-date validation before a V2 bundle is accepted;
- explicit CURRENT / STALE_TARGET / STALE_ISSUE health status;
- atomic latest-bundle publication with a last-valid archive and checksum manifest;
- app-level display of the active handoff status and bundle checksum prefix.

### Stage 15 - seasonal and forecast-defined regimes (implemented)

- interactive date-range comparison across calendar seasons and forecast-defined wind, solar and ramp-stress regimes;
- frozen regime thresholds derived from development-OOF forecast quantities only;
- regime-level firming, Stage 14 interval and market-value diagnostics;
- explicit warning that these are operational forecast regimes, not formal meteorological weather-regime classifications.

### Stage 18 - asset / site workspace (implemented)

- browser-local saved technical asset profiles with MW, MWh/duration, location label, grid import/export limits and SOH;
- explicit separation between site assumptions and national/proxy evidence;
- conservative conversion to the common physical battery contract when a symmetric limit is required.

### Stage 19 - degradation and SOH (implemented)

- usable-energy tracking from nameplate capacity and state of health;
- equivalent-full-cycle, calendar-fade and replacement-cost screening;
- marginal £/MWh throughput wear cost passed into the Stage 20 dispatch objective.

### Stage 20 - stochastic wholesale + BM bidding (implemented)

- finite pre-delivery wholesale-price and BM-activation scenarios;
- one common wholesale schedule and BM reserve offer across all scenarios;
- scenario-wise SOC feasibility, terminal restoration cost and CVaR risk penalty;
- BM activation probabilities/values remain explicit user scenarios, not a BOA forecast.

### Stage 21 - explainable evidence analyst (implemented)

- natural-language retrieval over current Studio evidence and saved scenario state;
- answers expose supporting evidence keys, internal source artefacts/formulations and limitations;
- no external generative model is used; evidence gaps are returned explicitly.

### Release 4

- automated versioned bundle publishing from the forecasting pipeline;
- stale-data and schema checks;
- last-valid-bundle fallback;
- data/model version display.

The remaining roadmap focuses on automated cross-repository bundle handoff, optional weather-ensemble comparison, shareable URL state and final product/deployment verification rather than adding another broad commercial module.

## Learning checkpoints

The project includes `docs/LEARNING_CHECKPOINT_1.md`. It asks the project owner to verify four settlement periods manually, identify power versus energy constraints and explain the result in interview-ready language.
