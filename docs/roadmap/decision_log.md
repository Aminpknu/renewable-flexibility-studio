# Decision log

## Stage 6A — Risk & Value deterministic layer

Stage: 6A Risk & Value deterministic layer
Decision: EVIDENCE READY
Decision date: 2026-09-03
Branch/commit: feature/stage6-risk-value / 7727b85
Data snapshot: 450-day V2 out-of-sample archive, 2025-04-01 to 2026-06-30; Stage A precomputed design grid
Primary metrics: physical baseline/residual exposure; avoided exposure; NPV; BCR; payback; break-even consequence value; maximum CAPEX; risk-value frontier
Acceptance gate result: PASS for deterministic pre-feasibility implementation
Production impact: none; feature branch only
Reason: physical-risk equations, discounted cash-flow calculations, switching values, CAPEX/consequence sensitivity, availability assumption and frontier are implemented with offline tests and explicit scenario labels
Known limitations: monetary assumptions are user scenarios; candidate CAPEX/fixed OPEX are scaled by MWh; expected availability is a scalar; no tax/financing/revenue stacking; not bankable valuation
Next allowed stage: Stage 6B quantitative downside risk

## Stage 6B — Quantitative downside risk

Stage: 6B Quantitative downside risk
Decision: EVIDENCE READY
Decision date: 2026-09-03
Branch/commit: feature/stage6-risk-value / 76823d5
Data snapshot: 450-day V2 out-of-sample archive, 2025-04-01 to 2026-06-30; daily-restored-SOC BESS evidence
Primary metrics: P10/P50/P90 NPV; probability NPV < 0; 95% VaR/CVaR; probability of failing firming/reliability gate; stress NPV/BCR; simulation-convergence differences
Acceptance gate result: PASS for quantitative pre-feasibility downside-risk implementation
Production impact: none; feature branch only
Reason: complete-day block bootstrap, fixed-seed reproducibility, visible distributions, availability-outage sampling, tail-risk metrics, convergence evidence and required stress cases are implemented and tested
Known limitations: scenario distributions are not market-calibrated; financial/technical multipliers are sampled independently; daily outage states are independent conditional on availability; no tax/financing/revenue stacking; not bankable valuation
Next allowed stage: Stage 6 promotion review, then dedicated probabilistic forecast / deployment work

## Stage 9 — GB market-linked battery optimisation

Stage: 9 Market-linked BESS optimisation
Decision: EVIDENCE READY
Decision date: 2026-09-03
Branch/commit: feature/stage9-market-optimisation / f6db0c5
Data snapshot: 450-day V2 out-of-sample forecast archive plus aligned Elexon System Price/NIV and APXMIDP Market Index Data, 21,600 settlement periods
Primary metrics: annualised net market value and mean daily physical error reduction for reactive, settlement-aware, wholesale-arbitrage and co-optimised strategies
Acceptance gate result: PASS for ex-post perfect-information market upper-bound layer
Production impact: none; feature branch only
Reason: open GB wholesale reference is checksum-locked; terminal SOC, negative prices, efficiency, shared MW/SOC, mutual charge/discharge exclusion and throughput costs are explicitly enforced and tested
Known limitations: realised future error/prices are known; APX MIP is not a day-ahead auction price; £2/MWh throughput cost is a scenario assumption; no ancillary-service stacking, transaction costs, site constraints, tax or financing
Next allowed stage: connect an authorised day-ahead auction feed or issue-time-correct price forecast, then evaluate a deployable co-optimised strategy without future-price/error leakage

## Stage 9 Packet 2 — Pre-delivery price forecast and reserve-aware scheduling

Stage: 9 Market optimisation, Packet 2
Decision: EVIDENCE READY
Decision date: 2026-09-03
Branch/commit: feature/stage9-market-optimisation / 0745370
Data snapshot: 450-day APX Market Index archive; 420 forecast-eligible days after 30-day warm-up; V2 renewable archive and Stage B reserve evidence
Primary metrics: price MAE/RMSE/R²; forecast-vs-naive MAE improvement; realised forecast-strategy margin; perfect-information capture rate; reserve-aware capture rate; positive-margin days
Acceptance gate result: PASS for public Market Index strategy benchmark
Production impact: feature branch only
Reason: target-day price leakage is excluded, DST days are supported, forecast-selected schedules are scored only after delivery, perfect-information upper bounds remain separate, and the reserve corridor quantifies the value/resilience trade-off
Known limitations: APX MIP is not a licensed day-ahead auction price; realised MIP scoring does not prove trade execution; no fees/spread/site grid limit; current 3 Sep latest bundle is an as-if reconstruction generated after target start
Next allowed stage: automate pre-delivery bundle issuance/freshness; authorised day-ahead feed comparison; ancillary-service eligibility/commitment modelling


## Stage 9C — Automated market forecast publication

Stage: 9C operational market forecast pipeline
Decision: EVIDENCE READY
Decision date: 2026-09-03
Branch: feature/stage9-market-optimisation
Primary evidence: atomic candidate validation, SHA-256 manifest, scheduled workflow, LIVE/RECONSTRUCTED/STALE health states, last-valid fallback
Acceptance result: PASS
Production impact: feature branch pending promotion to main
Reason: failed refreshes cannot corrupt the published market bundle; valid pre-delivery issues are protected from later reconstructions; stale targets are surfaced explicitly
Validation: 114 offline tests pass; current target correctly classified as RECONSTRUCTED
Known limitations: scheduler depends on the renewable latest-forecast target being updated upstream; GitHub-hosted publication does not itself generate the V2 renewable forecast
Next allowed stage: promote Stage 9 to main, then begin first ancillary/reserve-service stacking model

## Stage 9D — Quick Reserve availability stacking

Stage: 9D Quick Reserve availability stacking
Decision: EVIDENCE READY
Decision date: 2026-09-03
Branch: feature/stage9-quick-reserve
Primary evidence: NESO EAC PQR/NQR clearing-price archive, 90-day Apr–Jun 2026 stacking backtest, selected-day Studio view
Acceptance result: PASS for perfect-information availability-value screening
Production impact: none; feature branch pending promotion
Reason: the model encodes whole-MW contracts, PQR/NQR splitting within one nameplate, shared wholesale/reserve headroom, SOC/terminal constraints and consecutive-window energy protection; utilisation is excluded rather than inferred
Default two-window evidence: £2.38m/yr arbitrage-only; £1.35m/yr QR-only; £3.13m/yr stacked; £0.61m/yr independent-sum double-count avoided on the 90-day regime
Validation: 122 offline tests pass; `git diff --check` clean
Known limitations: realised clearing prices; price-taker acceptance; no utilisation dispatch/payment; energy guard is screening not prequalification proof; no site/telemetry/bid-execution model
Next allowed stage: pre-delivery QR bid/acceptance modelling and market-backed investment integration

## Stage 9E — Firming + arbitrage + Quick Reserve co-optimisation

Stage: 9E three-use revenue stacking
Decision: EVIDENCE READY
Decision date: 2026-09-03
Branch: feature/stage9-quick-reserve
Primary evidence: 90-day Apr–Jun 2026 triple-stack backtest and selected-day Studio comparison
Acceptance result: PASS for perfect-information shared-battery screening
Production impact: none; feature branch pending promotion
Reason: renewable firming, wholesale arbitrage and PQR/NQR now share one charge/discharge mode, MW nameplate, SOC trajectory, terminal SOC and QR crossover-energy constraints
Default two-window evidence: £2.51m/yr firming+arbitrage; £3.27m/yr full triple stack; +£0.76m/yr QR increment; ~£0.60m/yr independent-sum double-count avoided; 37.0% mean renewable-error reduction retained
Validation: 124 offline tests pass; `git diff --check` clean
Known limitations: realised forecast error/prices and observed EAC clearing prices; price-taker acceptance; QR utilisation excluded; no site/telemetry/bid-execution model
Next allowed stage: issue-time-correct Quick Reserve bid/acceptance modelling, then market-backed lifecycle NPV/Monte Carlo

## Stage 9F — Pre-delivery Quick Reserve capacity signal

Stage: 9F prior-date QR price forecasting and capacity allocation
Decision: EVIDENCE READY WITH ACCEPTANCE BOUNDARY
Decision date: 2026-09-03
Branch: feature/stage9-qr-predelivery
Primary evidence: stitched FY2025/current QR price history; 242-day price forecast backtest; 90 locked-date PQR/NQR allocation backtest; Apr–Jun Sell Orders execution diagnostic
Acceptance result: PASS for issue-time clearing-price/capacity allocation; asset-specific auction acceptance remains unresolved
Production impact: none; feature branch pending promotion
Reason: QR price features use earlier dates only and improve MAE by ~14%; forecast-selected capacity retains 93.1% of perfect-information QR availability value under system-volume-capped price-taker scoring
Acceptance boundary: a simple bid<=clearing rule has only 28.9% precision across 2.06m Apr–Jun QR Sell Orders, so no unsupported acceptance probability is applied
Known limitations: not an acceptance-adjusted revenue forecast; utilisation excluded; current-rule value validation is the 90 Apr–Jun V2 locked dates
Next allowed stage: structured EAC bid/acceptance modelling or market-backed lifecycle NPV using market value as base and QR as separately labelled upside until acceptance is identified
