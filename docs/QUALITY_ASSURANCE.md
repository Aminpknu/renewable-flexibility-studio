# Quality Assurance

**Audit date:** 4 September 2026  
**Scope:** Renewable Flexibility Studio application, analytical engines, data contracts, deployment configuration, PWA shell, export paths and user-facing documentation.

## Assurance position

The Studio is a research-grade decision-support demonstrator. Quality assurance is designed to answer two different questions:

1. **Did the stated calculation run and reconcile correctly?**
2. **Is the resulting scenario commercially attractive and complete enough for a real investment decision?**

These are not the same. A negative NPV can be a correct economic result. A positive NPV can still be commercially incomplete. The interface therefore reports calculation integrity separately from the investment outcome.

## Negative-NPV reconciliation

The default market-backed screen uses 420 unique forecast-selected wholesale decision days, annualised with 365.25 days/year. Under the frozen default assumptions, the independent check gives approximately:

| Component | Present value |
|---|---:|
| Forecast-selected operating value | £8.69m |
| Upfront CAPEX | £25.00m |
| Fixed OPEX | £4.28m |
| Replacement | £0.00m |
| **NPV** | **-£20.58m** |

The negative result is therefore driven by the revenue-to-cost gap under the selected assumptions, not by a sign reversal or a duplicated OPEX charge.

The same assurance layer also reports:

- break-even year-one operating value of about **£3.82m/year**;
- zero-NPV CAPEX of about **£4.42m** under the same OPEX/life/discount/degradation assumptions;
- current operating value coverage of about **29.7%** of the break-even requirement.

These switching values are back-solved and then checked by substituting them into the independent NPV equation.

## Automated calculation checks

The release checks:

- one finite market-value observation per unique evidence date;
- daily-to-annual conversion;
- NPV accounting identity and reported-versus-independent PV components;
- break-even annual-value and maximum-CAPEX back-solves;
- expected monotonicity with revenue and CAPEX;
- project-finance NPV from the complete annual cash-flow series;
- debt principal repayment and zero closing balance;
- non-negative tax cash flows under the stated no-refund convention;
- DSCR row calculations;
- forecast settlement-period completeness and capacity-factor bounds;
- spatial allocation and demand reconciliation;
- sizing-grid rectangularity and unique scenario keys;
- unique Dash component IDs and PWA endpoint contracts.

The checks are covered by unit/integration tests and a reproducible professional-audit script.

## Data-freshness controls

The national renewable forecast, market-price forecast and spatial context have separate target dates and quality states. The application does not silently treat them as one current bundle.

- A national bundle is accepted only after schema, target-date, settlement-period, freshness and checksum validation.
- Market output is labelled LIVE, RECONSTRUCTED, STALE_TARGET or STALE_TIME from its manifest.
- Spatial supply/demand charts are withheld when their target date does not match the national forecast.
- The Overview reports module-level readiness so a current national forecast cannot hide stale supporting context.
- Previous valid bundles are retained for controlled fallback and are labelled as fallback/stale when used.

GitHub schedules are best-effort rather than a guaranteed operational scheduler. The refresh workflows therefore use repeated attempts, validation before publication, atomic replacement, fallback retention and race-safe rebasing before push.

## Evidence boundaries

The following remain outside the validated scope:

- live BMS, PCS, SCADA or meter telemetry;
- physical dispatch or automatic bid submission;
- actual asset settlement and performance penalties;
- proprietary day-ahead auction or route-to-market data;
- distribution/transmission connection studies;
- site-specific weather, availability and degradation histories;
- supplier-quoted CAPEX/OPEX or lender-approved revenue curves;
- tax, accounting, legal, credit or investment advice.

A green calculation status must not be interpreted as validation of these excluded areas.

## Professional presentation controls

This quality pass also covers matters that can undermine trust even when the mathematics is correct:

- consistent signed-currency formatting, including `-£` for negative values;
- removal of character-encoding artefacts;
- unique and sequential methods-guide numbering;
- frozen validation examples clearly distinguished from current live data;
- plain-English product headings with internal stage identifiers retained only where useful for traceability;
- keyboard focus states, reduced-motion support and semantic PWA status/dialog attributes;
- metadata, canonical URL, health endpoint, real CI badges and deployment health checks.

## Deferred structural debt

`app.py` remains a large presentation/integration module. Its analytical equations already live in independently tested `engine/` modules, but the page layout and callback layer should eventually be split into smaller domain modules. That refactor is deliberately deferred from this assurance release because a large structural change would add regression risk without changing validated results.

The professional standard for future changes is:

1. preserve issue-time versus realised-scoring boundaries;
2. add or update a test before changing a validated calculation;
3. rerun the independent assurance checks;
4. keep stale or incomplete data visibly labelled;
5. update the assumption and evidence registers;
6. verify both GitHub Actions and the deployed endpoints before release.
