# GB Market Optimisation Methodology

## Scope

This stage adds market-linked battery decision evidence to the Renewable Flexibility Studio. It remains a virtual portfolio benchmark and is not a live trading system, investment recommendation, or representation of an actual registered market position.

The public implementation deliberately separates three concepts:

1. **System Price**: realised GB imbalance-settlement price from Elexon.
2. **Market Index Price (MIP)**: open short-term wholesale market reference from Elexon Market Index Data.
3. **Day-ahead auction price**: a separate licensed NEMO data product. No licensed Nord Pool/EPEX day-ahead data are redistributed by this repository.

Elexon MIP is therefore never labelled `day-ahead price` in the application.

## Market data contract

The versioned public archive uses APX Market Index Data (`APXMIDP`) from Elexon Insights for exactly the same 450 V2 target days and 21,600 settlement periods as the forecast-error and System Price evidence.

Per settlement period it stores:

```text
settlement_date
settlement_period
valid_time_utc
market_index_provider
market_index_price_gbp_per_mwh
market_index_volume_mwh
```

A separate `load_licensed_day_ahead_prices()` adapter defines the future licensed-feed contract:

```text
settlement_date
settlement_period
valid_time_utc
publication_time_utc
day_ahead_price_gbp_per_mwh
source
```

It rejects duplicate/incomplete GB days and can enforce an issue-time publication cutoff. This means licensed day-ahead data can later be connected without changing the optimisation engine.

## A. Error-minimising reactive benchmark

The existing battery reacts to every observed renewable forecast deviation whenever power and SOC allow. This maximises physical firming, not financial value.

For a fair market comparison, the Stage 9 backtest prices the energy required to restore the battery to its starting 50% SOC using that day's APX Market Index volume-weighted average price. A transparent throughput-cost assumption is also deducted.

This exposes a key distinction: a strategy can remove almost all forecast error while still have poor market value once restoring stored energy is priced.

## B. Settlement-aware directional firming

The settlement-aware optimiser may only reduce the observed renewable deviation. It cannot reverse or deliberately amplify the imbalance.
For renewable error `e_t = actual_t - forecast_t`, firming charge/discharge is bounded by the deviation direction:

```text
surplus (e_t > 0):  0 <= charge_t <= min(e_t, P)
deficit (e_t < 0):  0 <= discharge_t <= min(-e_t, P)
```

The optimiser minimises the realised settlement-payment change plus battery throughput cost and terminal SOC-restoration cost. System Price determines the marginal value of correcting a deviation; the APX daily MIP VWAP prices terminal grid restoration.

SOC follows the same charge/discharge efficiency and 10–90% bounds as the existing physical battery model. Terminal restoration is modelled with mutually exclusive grid import/export variables. A binary restoration mode prevents simultaneous import/export, including on negative-price days.

The output reports:

- settlement-value improvement before battery costs;
- throughput and throughput cost;
- grid import/export required to restore starting SOC;
- restoration net cost;
- net settlement-value improvement;
- physical forecast-error reduction retained by the financially selective strategy.

This is a **perfect-information upper-bound benchmark** because realised forecast error and realised System Price are known to the optimiser.

## C. Wholesale arbitrage upper bound

The arbitrage benchmark uses the full realised APX Market Index price path for a target day. It may grid-charge at low/negative prices and discharge at higher prices, subject to the same MW, MWh, efficiency and SOC constraints.
Charge and discharge are mutually exclusive in every settlement period through binary mode variables. Terminal SOC is constrained to equal starting SOC, so the arbitrage margin contains no one-time free-energy benefit.

```text
gross arbitrage margin = discharge revenue - charging cost
net arbitrage margin = gross margin - throughput cost
```

Because the full realised price path is known, this is also a perfect-foresight upper bound, not a deployable revenue forecast.

## D. Co-optimised firming + arbitrage

The co-optimiser allocates one battery between two uses:

- **firming charge/discharge**, which changes the renewable imbalance and is valued at System Price;
- **arbitrage charge/discharge**, treated as a separately nominated wholesale transaction valued at Market Index Price.

All four dispatch components share:

- one total battery MW limit;
- one SOC trajectory;
- one 10–90% usable energy range;
- one efficiency model;
- one throughput-cost assumption;
- a terminal SOC equality.

The model prevents simultaneous total charging and discharging. Firming dispatch remains bounded by the renewable forecast error, while arbitrage dispatch may use otherwise available battery capability.

The objective maximises:

```text
firming settlement value
+ wholesale arbitrage value
- battery throughput cost
```

## Frozen 450-day default evidence

For the default 100 MW 50/50 renewable portfolio, Stage A 25 MW / 200 MWh battery, 90% round-trip efficiency, 50% starting/terminal SOC and a **£2/MWh scenario throughput cost**:

| Strategy | Annualised market value | Mean daily error reduction |
|---|---:|---:|
| Error-minimising reactive firming | **-£0.061m/yr** | **98.3%** |
| Settlement-aware firming | **£0.270m/yr** | **47.8%** |
| Wholesale arbitrage only | **£1.904m/yr** | n/a |
| Co-optimised firming + arbitrage | **£2.049m/yr** | **40.1%** |

The co-optimised result exceeds arbitrage-only by about **£0.145m/year** on this evidence, while preserving some renewable-imbalance reduction. This is a value-stacking upper bound under realised prices, not a forecast of obtainable revenue.

## Scientific boundary

The current market layer does **not** claim:

- deployable day-ahead dispatch;
- actual historical revenue earned by a registered asset;
- licensed NEMO day-ahead auction prices;
- Balancing Mechanism or ancillary-service stacking;
- grid-connection, metering or site-specific operational constraints;
- taxes, financing, transaction fees or bid/offer execution risk.

The next deployable step requires an issue-time-correct price forecast or an authorised day-ahead auction feed. Perfect-foresight results remain clearly separated as upper-bound evidence.

## E. Issue-time-correct Market Index price forecast

The first forecast-based strategy removes price perfect foresight without introducing licensed auction data. For every target day after 30 prior Market Index days, an expanding ridge model is refit using **settlement dates strictly earlier than the target date**.

Features are deliberately compact and inspectable: local-time harmonics, day-of-week/year harmonics, previous observed daily price level, 7/28-day prior means, previous observed same-settlement-period price and 7/28-observation same-period means. No target-day Market Index price or volume is used as an input.

Across 420 eligible target days the model achieves **£20.01/MWh MAE**, versus **£22.53/MWh** for a previous-observed-same-period baseline, an **11.2% MAE improvement**. The model is a forecast of the public APX Market Index reference, not a forecast of a licensed day-ahead auction clearing price.

## F. Forecast-selected arbitrage and capture gap

For each eligible historical target day, the battery schedule is optimised using only the **forecast Market Index price path**. The schedule is then frozen and valued afterwards at the realised APX Market Index Price. This separates the information used to choose dispatch from the price used to score the result.

On the default 25 MW / 200 MWh battery with £2/MWh throughput cost, the forecast-selected strategy annualises to about **£1.13m/year**, compared with **£1.89m/year** for the same 420-day perfect-foresight arbitrage upper bound. The resulting realised-value capture ratio is **60.0%** overall and **63.4%** on Apr-Jun 2026. About **89.3%** of eligible days have positive realised net margin.

A reserve-aware variant constrains the wholesale schedule inside the Stage B uncertainty-derived SOC corridor. It remains feasible on all 420 mixed-portfolio target days and captures about **49.6%** of the perfect-information arbitrage value while increasing positive-margin days slightly to **90.7%**. The mean market opportunity cost of preserving that reserve corridor is about **£537/day** on this benchmark.

This is closer to a deployable information set but is still a **strategy benchmark**, not realised tradable revenue. Market Index Price is a short-term settlement reference, and the backtest assumes the forecast-selected schedule can be scored at realised MIP. Bid/offer execution, spread, fees and an authorised day-ahead trading product remain outside this packet.

## G. Forecast-day market schedule

The same prior-data-only price model can be applied to the latest renewable forecast target. The public schedule compares a price-only wholesale plan with a reserve-aware plan constrained by the Stage B SOC corridor and the Stage A selected battery. The latter therefore makes the market-versus-resilience trade-off explicit before delivery.

The frozen 3 September 2026 market-price validation file was regenerated after the target day had already started. Its manifest therefore records `operational_status = as_if_reconstruction_after_target_start`; it is **not** presented as an actually issued pre-delivery trading forecast. All target-day MIP observations remain excluded from its features. A future automated pipeline should generate this bundle before the target delivery day begins.

## G. Automated forecast-bundle publication

The operational market-price bundle is published atomically. A refresh is first written to temporary CSV/manifest files, then checked for one complete 46/48/50-period target day, finite values, target consistency and SHA-256 integrity. The live files are replaced only after all checks pass.

Before replacement, the previous valid bundle is copied to `last_valid_market_price_forecast.*`. A failed API/model refresh therefore cannot corrupt the current public bundle. `market_forecast_pipeline_status.json` records whether a candidate was published, a previous bundle was retained/restored, or the renewable target itself was stale.

Bundle health is shown explicitly in the Studio:

- **LIVE**: target matches the renewable bundle and the price forecast was issued before target start;
- **RECONSTRUCTED**: target matches, but the file was generated after delivery had begun;
- **STALE_TARGET**: price and renewable bundle target dates differ;
- **STALE_TIME**: the target delivery window is already materially past.

A scheduled GitHub Actions workflow runs at 18:15 UTC each day and may also be triggered manually. It refreshes the validated bundle and commits only changed `data/` evidence. A reconstruction is never allowed to overwrite an already-valid pre-delivery issue for the same target.

## H. Quick Reserve availability stacking

The first ancillary-service packet adds NESO Quick Reserve to the wholesale battery benchmark. It uses the EAC Results Summary for Positive Quick Reserve (PQR) and Negative Quick Reserve (NQR), with one 30-minute auction window per settlement period and clearing prices in £/MW/h.

The screening model encodes whole-MW QR contracts with a 1 MW minimum positive commitment. PQR and NQR split one battery nameplate capacity, so `PQR + NQR <= BESS MW`: the same MW is not sold twice. Wholesale charging/discharging, QR commitments and SOC therefore share one physical battery.

Availability payment is:

```text
contracted MW * clearing price (£/MW/h) * 0.5 h
```

Only availability value is included. QR utilisation is dispatched separately and paid on a pay-as-bid basis, so neither utilisation payment nor activation energy is inferred from the availability-clearing archive.

A configurable state-of-energy guard requires enough stored energy/headroom to sustain one or more consecutive QR windows without breaching the 10–90% SOC limits. The baseline uses two consecutive windows (1 hour), while one- and four-window cases are retained as sensitivities. This is a conservative screening approximation of the service energy/crossover requirement, not proof of NESO prequalification.

The historical value calculation is an **ex-post price-taker upper bound**. It assumes the virtual asset could contract integer MW at the observed clearing price up to the system cleared volume. It does not model the asset's submitted bid price, auction merit order, acceptance probability, telemetry, operational notifications or commercial unavailability penalties.

The benchmark also calculates the incorrect independent sum of `arbitrage-only + QR-only`. The gap between that sum and the shared-battery optimum is reported as **double-count avoided**, making the opportunity cost of using the same MW/SOC for multiple revenue streams explicit.

### Frozen Apr–Jun 2026 QR evidence

For the default 100 MW 50/50 portfolio, 25 MW / 200 MWh battery and £2/MWh throughput cost, the **two-window (1 h) guard** gives an Apr–Jun 2026 regime annualisation of about **£2.38m/yr arbitrage-only**, **£1.35m/yr QR availability-only**, and **£3.13m/yr physically stacked**. QR therefore adds about **£0.75m/yr** above the arbitrage-only upper bound in this regime.

Simply adding the two independent strategies would imply about **£3.73m/yr**. The shared-battery optimisation reduces this by about **£0.61m/yr**, which is the estimated double-count avoided. Mean stacked commitments are about **13.0 MW PQR** and **8.6 MW NQR**, with their sum constrained within the 25 MW nameplate in every window.

Changing the crossover guard from one to four windows reduces the stacked regime annualisation from roughly **£3.17m/yr to £3.08m/yr**. These values describe the 90-day Apr–Jun 2026 price regime and must not be substituted for a full-year forecast or guaranteed service revenue.

### Three-use co-optimisation

A second QR formulation adds renewable imbalance firming to the same optimisation. Firming charge/discharge remains bounded by the observed renewable forecast error and is valued at System Price; arbitrage is valued at Market Index Price; PQR/NQR earn availability clearing value only. All three uses share charge/discharge mode, battery MW, SOC, terminal SOC and the QR energy guard.

With the baseline two-window guard on Apr–Jun 2026, **firming + arbitrage without QR annualises to about £2.51m/yr**, while **firming + arbitrage + QR annualises to about £3.27m/yr**. The QR layer therefore adds about **£0.76m/yr** above the firming/arbitrage upper bound in this regime. Mean physical renewable-error reduction changes from **35.8% to 37.0%**.

The independent sum of firming+arbitrage and QR-only would be about **£3.86m/yr**, so the triple co-optimiser removes roughly **£0.60m/yr** of double-counted value. This is the preferred headline revenue-stacking benchmark because it explicitly allocates one BESS across renewable-risk management, energy trading and ancillary-service availability.

## I. Pre-delivery Quick Reserve capacity signal

The first deployable-style QR packet forecasts PQR/NQR clearing prices from EAC results that were available on strictly earlier delivery dates. The forecast history stitches the NESO FY2025 Results Summary archive to the current Results Summary resource, giving 28,992 PQR/NQR rows across 14,496 half-hour windows from 2 September 2025 to 30 June 2026. Apr–Jun 2026 remains the current-rule economic validation regime.

A ridge model uses product, settlement-period/calendar harmonics, prior same-product/period prices and prior system-cleared volumes. It never uses target-day clearing price. Across 242 eligible dates its MAE is about **£2.09/MW/h** versus **£2.44/MW/h** for the previous-same-product/period baseline, a **14.2%** improvement. On Apr–Jun 2026, MAE is about **£2.18/MW/h** versus **£2.56/MW/h** naive.

The price forecast is converted into an integer PQR/NQR capacity split before each target date using the same 25 MW nameplate and two-window state-of-energy guard. The capacity decision is then frozen. Ex-post scoring uses the subsequently realised clearing price and caps accepted capacity at the realised system-cleared volume.

On the 90 V2 locked Apr–Jun 2026 dates, perfect-information QR-only availability annualises to about **£1.35m/yr** under the existing price-taker benchmark. The prior-date forecast allocation retains about **93.1%** of that value (**£1.26m/yr**), compared with **88.0%** (**£1.19m/yr**) for the naive lag allocation. Forecast allocation therefore adds roughly **£69k/yr** over the naive signal in this regime. Mean PQR/NQR allocations are about **13.4 / 8.5 MW**, close to the perfect-information **13.0 / 8.6 MW** split.

### Acceptance boundary

This capacity-capture result is **not an acceptance-adjusted asset-revenue forecast**. EAC Sell Orders expose price limit, status, acceptance ratio, executed quantity and clearing price. Across 2.06 million Apr–Jun 2026 Quick Reserve sell orders, the simple classifier `priceLimit <= clearingPrice` has only about **28.9% precision** for actual execution, despite high recall. Many below-clearing orders are rejected because auction baskets, substitution/flexible-order constraints and other optimisation conditions matter.

The project therefore does not infer an asset-specific acceptance probability from clearing price alone. The current pre-delivery QR result is labelled a **capacity-allocation signal under a system-volume-capped price-taker assumption**. A future bid/acceptance model must use unit/order structure or an explicitly validated auction-acceptance model before its outputs can be described as obtainable QR revenue.
