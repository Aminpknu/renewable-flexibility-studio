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
