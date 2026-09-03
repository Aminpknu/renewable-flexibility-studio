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
