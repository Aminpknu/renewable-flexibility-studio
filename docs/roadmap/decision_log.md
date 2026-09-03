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
