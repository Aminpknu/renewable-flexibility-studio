"""Independent calculation checks used by the public assurance layer.

These functions do not estimate new revenue. They reperform key accounting
identities and data-shape checks so an unattractive result is not confused with
a silent calculation failure.
"""

from __future__ import annotations

from typing import Any
import math

import numpy as np
import pandas as pd

from engine.market_investment import MarketInvestmentAssumptions
from engine.project_finance import ProjectFinanceAssumptions


def annualise_unique_daily_values(
    frame: pd.DataFrame,
    value_column: str,
    *,
    date_column: str = "settlement_date",
    days_per_year: float = 365.25,
) -> float:
    """Annualise a complete daily evidence series after validating its keys."""
    if frame.empty:
        raise ValueError("Daily evidence cannot be empty.")
    missing = {date_column, value_column}.difference(frame.columns)
    if missing:
        raise ValueError(f"Daily evidence is missing columns: {sorted(missing)}")
    dates = pd.to_datetime(frame[date_column], errors="raise").dt.normalize()
    if dates.duplicated().any():
        duplicates = dates.loc[dates.duplicated(keep=False)].dt.date.astype(str).unique()
        raise ValueError(f"Daily evidence contains duplicate dates: {duplicates[:5].tolist()}")
    values = pd.to_numeric(frame[value_column], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Daily evidence values must be finite.")
    if not np.isfinite(float(days_per_year)) or days_per_year <= 0:
        raise ValueError("Days per year must be finite and positive.")
    return float(values.mean() * float(days_per_year))


def _market_independent_values(
    annual_operating_value_gbp: float,
    assumptions: MarketInvestmentAssumptions,
) -> dict[str, float]:
    years = np.arange(1, assumptions.asset_life_years + 1, dtype=float)
    discount = np.power(1.0 + assumptions.discount_rate, years)
    degradation = np.power(
        1.0 - assumptions.annual_revenue_degradation_fraction,
        years - 1.0,
    )
    revenue_factor = float(np.sum(degradation / discount))
    opex_factor = float(np.sum(1.0 / discount))
    pv_market = float(annual_operating_value_gbp) * revenue_factor
    pv_opex = float(assumptions.fixed_opex_gbp_per_year) * opex_factor
    pv_replacement = 0.0
    if assumptions.replacement_year is not None:
        pv_replacement = float(
            assumptions.replacement_cost_gbp
            / ((1.0 + assumptions.discount_rate) ** assumptions.replacement_year)
        )
    pv_total_cost = float(assumptions.total_capex_gbp + pv_opex + pv_replacement)
    npv = float(pv_market - pv_total_cost)
    maximum_capex = float(max(pv_market - pv_opex - pv_replacement, 0.0))
    break_even_value = float(pv_total_cost / revenue_factor)
    return {
        "revenue_factor": revenue_factor,
        "opex_factor": opex_factor,
        "pv_market_value_gbp": pv_market,
        "pv_fixed_opex_gbp": pv_opex,
        "pv_replacement_gbp": pv_replacement,
        "pv_total_cost_gbp": pv_total_cost,
        "npv_gbp": npv,
        "maximum_capex_for_zero_npv_gbp": maximum_capex,
        "minimum_annual_market_value_for_zero_npv_gbp": break_even_value,
    }


def assure_market_investment(
    annual_operating_value_gbp: float,
    assumptions: MarketInvestmentAssumptions,
    *,
    reported: dict[str, Any] | None = None,
    daily_evidence: pd.DataFrame | None = None,
    value_column: str = "forecast_strategy_margin_gbp",
    tolerance_gbp: float = 1.0,
) -> dict[str, Any]:
    """Reconcile the market-backed NPV using an independent vector formula."""
    independent = _market_independent_values(annual_operating_value_gbp, assumptions)
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    identity = (
        independent["pv_market_value_gbp"]
        - independent["pv_total_cost_gbp"]
    )
    add(
        "NPV accounting identity",
        abs(identity - independent["npv_gbp"]) <= tolerance_gbp,
        "NPV = PV operating value - CAPEX - PV OPEX - PV replacement.",
    )
    if reported is not None:
        comparisons = {
            "Reported NPV reconciliation": "npv_gbp",
            "Reported PV operating value reconciliation": "pv_market_value_gbp",
            "Reported PV total cost reconciliation": "pv_total_cost_gbp",
        }
        for name, key in comparisons.items():
            if key in reported:
                difference = float(reported[key]) - independent[key]
                add(name, abs(difference) <= tolerance_gbp, f"Difference £{difference:,.2f}.")

    if daily_evidence is not None:
        annualised = annualise_unique_daily_values(daily_evidence, value_column)
        difference = annualised - float(annual_operating_value_gbp)
        add(
            "Daily evidence annualisation",
            abs(difference) <= tolerance_gbp,
            f"{len(daily_evidence):,} unique daily rows; difference £{difference:,.2f}.",
        )

    zero_from_max_capex = (
        independent["pv_market_value_gbp"]
        - independent["pv_fixed_opex_gbp"]
        - independent["pv_replacement_gbp"]
        - independent["maximum_capex_for_zero_npv_gbp"]
    )
    add(
        "Maximum-CAPEX back-solve",
        abs(zero_from_max_capex) <= tolerance_gbp,
        f"Zero-NPV CAPEX £{independent['maximum_capex_for_zero_npv_gbp']:,.2f}.",
    )
    zero_from_break_even = (
        independent["minimum_annual_market_value_for_zero_npv_gbp"]
        * independent["revenue_factor"]
        - independent["pv_total_cost_gbp"]
    )
    add(
        "Break-even annual-value back-solve",
        abs(zero_from_break_even) <= tolerance_gbp,
        f"Zero-NPV year-one value £{independent['minimum_annual_market_value_for_zero_npv_gbp']:,.2f}.",
    )
    add("Revenue monotonicity", independent["revenue_factor"] > 0, "Higher operating value must increase NPV.")
    add("CAPEX monotonicity", True, "Each additional £1 of upfront CAPEX reduces NPV by £1.")

    passed = all(item["passed"] for item in checks)
    break_even = independent["minimum_annual_market_value_for_zero_npv_gbp"]
    max_capex = independent["maximum_capex_for_zero_npv_gbp"]
    revenue_coverage = (
        100.0 * float(annual_operating_value_gbp) / break_even
        if break_even > 0 else float("inf")
    )
    capex_multiple = (
        assumptions.total_capex_gbp / max_capex
        if max_capex > 0 else float("inf")
    )
    return {
        "calculation_status": "PASS" if passed else "FAIL",
        "economic_outcome": "BELOW_BREAK_EVEN" if independent["npv_gbp"] < 0 else "ABOVE_BREAK_EVEN",
        "checks_passed": int(sum(item["passed"] for item in checks)),
        "checks_total": int(len(checks)),
        "checks": checks,
        "annual_operating_value_gbp": float(annual_operating_value_gbp),
        "total_capex_gbp": float(assumptions.total_capex_gbp),
        **independent,
        "annual_value_gap_to_break_even_gbp": float(break_even - annual_operating_value_gbp),
        "annual_value_coverage_of_break_even_pct": float(revenue_coverage),
        "capex_multiple_of_zero_npv_capex": float(capex_multiple),
        "scope_boundary": (
            "Arithmetic and data-shape assurance only. A PASS does not prove that revenue, "
            "CAPEX, OPEX or market coverage is commercially complete or bankable."
        ),
    }


def assure_project_finance(
    result: dict[str, Any],
    assumptions: ProjectFinanceAssumptions,
    *,
    tolerance_gbp: float = 1.0,
) -> dict[str, Any]:
    """Check the project-finance cash-flow, debt and DSCR identities."""
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    cashflows = np.asarray(result["project_cashflows_gbp"], dtype=float)
    years = np.arange(len(cashflows), dtype=float)
    independent_npv = float(np.sum(cashflows / np.power(1.0 + assumptions.project_discount_rate, years)))
    difference = independent_npv - float(result["project_npv_gbp"])
    add("Project-NPV cash-flow reconciliation", abs(difference) <= tolerance_gbp, f"Difference £{difference:,.2f}.")
    schedule = pd.DataFrame(result["yearly_schedule"])
    initial_debt = float(result["debt_amount_gbp"])
    principal_paid = float(pd.to_numeric(schedule["principal_gbp"]).sum())
    final_debt = float(pd.to_numeric(schedule["debt_closing_gbp"]).iloc[-1])
    add(
        "Debt principal reconciliation",
        abs(principal_paid - initial_debt) <= tolerance_gbp,
        f"Initial debt £{initial_debt:,.2f}; principal repaid £{principal_paid:,.2f}.",
    )
    add("Debt closes at zero", abs(final_debt) <= tolerance_gbp, f"Final debt £{final_debt:,.2f}.")
    tax_nonnegative = (
        pd.to_numeric(schedule["unlevered_tax_gbp"]).ge(-tolerance_gbp).all()
        and pd.to_numeric(schedule["cash_tax_after_interest_gbp"]).ge(-tolerance_gbp).all()
    )
    add("Tax cash flows are non-negative", bool(tax_nonnegative), "No negative tax credit is created by this screening model.")

    debt_rows = schedule.loc[pd.to_numeric(schedule["debt_service_gbp"]).gt(0)].copy()
    if debt_rows.empty:
        dscr_ok = math.isinf(float(result["minimum_dscr"])) or np.isnan(float(result["minimum_dscr"]))
        dscr_detail = "No debt-service years."
    else:
        independent_dscr = (
            pd.to_numeric(debt_rows["cfads_gbp"])
            / pd.to_numeric(debt_rows["debt_service_gbp"])
        )
        reported_dscr = pd.to_numeric(debt_rows["dscr"])
        dscr_ok = bool(np.allclose(independent_dscr, reported_dscr, atol=1e-10, rtol=0))
        dscr_detail = f"Checked {len(debt_rows)} debt-service years."
    add("DSCR row identity", dscr_ok, dscr_detail)

    passed = all(item["passed"] for item in checks)
    return {
        "calculation_status": "PASS" if passed else "FAIL",
        "economic_outcome": "BELOW_BREAK_EVEN" if float(result["project_npv_gbp"]) < 0 else "ABOVE_BREAK_EVEN",
        "checks_passed": int(sum(item["passed"] for item in checks)),
        "checks_total": int(len(checks)),
        "checks": checks,
        "independent_project_npv_gbp": independent_npv,
        "scope_boundary": (
            "Cash-flow, debt and DSCR identities only. A PASS is not a lender decision, "
            "tax opinion or validation of revenue bankability."
        ),
    }
