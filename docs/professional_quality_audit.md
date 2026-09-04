# Professional Quality Audit

Date: 4 September 2026

## Scope

This audit reviewed the Studio as a complete product, not as a request for new analytical features. The review covered model-result credibility, terminology, navigation, documentation, metadata, accessibility, mobile/PWA behaviour, exports, testing, deployment and evidence boundaries.

## Highest-risk presentation issue

The default market-backed NPV is strongly negative. The result is economically plausible under the entered CAPEX, OPEX, degradation, discount-rate and revenue assumptions, but a reader could reasonably interpret it as a calculation fault because the interface previously showed the result without an explicit reconciliation check.

The investment tab now includes an independent discounted-cash-flow rebuild. It compares the rebuilt NPV with the model output, reports the reconciliation gap and tolerance, separates arithmetic validity from input validity, and displays the break-even annual value and maximum CAPEX.

A passing arithmetic check does not validate commercial assumptions. The interface now states this directly.

## Professional polish completed

- Replaced stage/release language in principal user-facing headings with decision-oriented names.
- Retained implementation-stage references in the technical guide where they help traceability.
- Corrected duplicate numbering in the Models, Data & Validation Guide.
- Removed a hard-coded daily forecast date from the README.
- Updated the README to reflect the live probabilistic layer and full Excel export.
- Added a more descriptive browser title, page description, canonical URL and social-preview metadata.
- Replaced the prototype-style footer with a product-level evidence statement.
- Added visible keyboard focus treatment and reduced-motion support.
- Added responsive styling for the NPV assurance panel.

## Quality strengths confirmed

- Forecast, uncertainty, battery physics, market analysis and finance retain explicit evidence boundaries.
- Perfect-information, forecast-selected and acceptance-calibrated results are not silently combined.
- Live forecast bundles are validated before publication and stale data is labelled.
- The PWA does not claim that full optimisation works offline.
- CSV and Excel exports preserve a clear audit trail.
- The analytical engines remain separated from the Dash presentation layer and covered by automated tests.

## Remaining non-feature improvements

These are quality-management tasks, not additional modelling modules:

1. Run a documented manual QA pass on current Safari, Chrome and Edge after each major UI release.
2. Add release tags and concise release notes so a reviewer can match the live site to a tested commit.
3. Keep screenshots of the six main tabs as a visual-regression reference.
4. Review all third-party data links and licence statements quarterly.
5. Run a formal WCAG contrast and keyboard-navigation audit.
6. Monitor Render cold-start and response time; the free hosting tier can affect first impressions even when the application is healthy.
7. Replace screening CAPEX/OPEX and revenue assumptions with project-specific evidence whenever the Studio is used for a real asset discussion.

## Claim boundary

The Studio is a transparent decision-intelligence and pre-feasibility product. It does not claim live battery telemetry, dispatch control, bid submission, settlement operations, a network connection study, proprietary market forecasts or bankable lender-grade revenue evidence.
