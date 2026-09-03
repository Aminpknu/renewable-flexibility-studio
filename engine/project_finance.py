"""Transparent screening-level debt/equity finance for the market-backed BESS case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import brentq


@dataclass(frozen=True)
class ProjectFinanceAssumptions:
    total_capex_gbp: float
    fixed_opex_gbp_per_year: float = 0.0
    asset_life_years: int = 15
    project_discount_rate: float = 0.08
    annual_revenue_degradation_fraction: float = 0.02
    debt_fraction: float = 0.60
    debt_interest_rate: float = 0.06
    debt_tenor_years: int = 10
    corporation_tax_rate: float = 0.25
    capital_allowance_year1_fraction: float = 0.0
    capital_allowance_remaining_years: int = 10
    equity_hurdle_rate: float = 0.12
    dscr_threshold: float = 1.20
    replacement_year: int | None = None
    replacement_cost_gbp: float = 0.0

    def __post_init__(self) -> None:
        numeric = [
            self.total_capex_gbp, self.fixed_opex_gbp_per_year,
            self.project_discount_rate, self.annual_revenue_degradation_fraction,
            self.debt_fraction, self.debt_interest_rate, self.corporation_tax_rate,
            self.capital_allowance_year1_fraction, self.equity_hurdle_rate,
            self.dscr_threshold, self.replacement_cost_gbp,
        ]
        if not np.isfinite(np.asarray(numeric, dtype=float)).all():
            raise ValueError("Project-finance assumptions must be finite.")
        if self.total_capex_gbp < 0 or self.fixed_opex_gbp_per_year < 0 or self.replacement_cost_gbp < 0:
            raise ValueError("Project-finance costs cannot be negative.")
        if self.asset_life_years <= 0 or self.debt_tenor_years <= 0:
            raise ValueError("Asset life and debt tenor must be positive.")
        if self.debt_tenor_years > self.asset_life_years:
            raise ValueError("Debt tenor cannot exceed asset life in this screening model.")
        for name, value in (
            ("debt_fraction", self.debt_fraction),
            ("corporation_tax_rate", self.corporation_tax_rate),
            ("capital_allowance_year1_fraction", self.capital_allowance_year1_fraction),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must lie in [0, 1].")
        if not 0 <= self.annual_revenue_degradation_fraction < 1:
            raise ValueError("Revenue degradation must lie in [0, 1).")
        if self.project_discount_rate <= -1 or self.debt_interest_rate < 0 or self.equity_hurdle_rate <= -1:
            raise ValueError("Discount/hurdle rates are outside the supported range.")
        if self.capital_allowance_remaining_years < 0:
            raise ValueError("Remaining capital-allowance years cannot be negative.")
        if self.capital_allowance_year1_fraction < 1 and self.capital_allowance_remaining_years <= 0:
            raise ValueError("Unclaimed CAPEX requires positive remaining allowance years.")
        if self.dscr_threshold <= 0:
            raise ValueError("DSCR threshold must be positive.")
        if self.replacement_year is not None and not 1 <= self.replacement_year <= self.asset_life_years:
            raise ValueError("Replacement year must lie within asset life.")
        if self.replacement_year is None and self.replacement_cost_gbp > 0:
            raise ValueError("Replacement cost requires a replacement year.")


def _npv(rate: float, cashflows: list[float]) -> float:
    return float(sum(value / ((1.0 + rate) ** year) for year, value in enumerate(cashflows)))


def _irr(cashflows: list[float]) -> float | None:
    values = np.asarray(cashflows, dtype=float)
    if not ((values < 0).any() and (values > 0).any()):
        return None

    def objective(rate: float) -> float:
        return float(sum(value / ((1.0 + rate) ** year) for year, value in enumerate(values)))

    grid = np.concatenate([
        np.linspace(-0.999, 1.0, 300),
        np.geomspace(2.01, 101.0, 200) - 1.0,
    ])
    previous_rate = float(grid[0])
    previous = objective(previous_rate)
    for rate in grid[1:]:
        current_rate = float(rate)
        current = objective(current_rate)
        if current == 0:
            return current_rate
        if previous * current < 0:
            return float(brentq(objective, previous_rate, current_rate, maxiter=300))
        previous_rate, previous = current_rate, current
    return None


def _annual_debt_service(principal: float, rate: float, tenor: int) -> float:
    if principal <= 0:
        return 0.0
    if rate == 0:
        return float(principal / tenor)
    return float(principal * rate / (1.0 - (1.0 + rate) ** (-tenor)))


def _capital_allowance_schedule(assumptions: ProjectFinanceAssumptions) -> list[float]:
    years = assumptions.asset_life_years
    schedule = [0.0] * years
    initial = assumptions.total_capex_gbp * assumptions.capital_allowance_year1_fraction
    schedule[0] = initial
    remainder = assumptions.total_capex_gbp - initial
    if remainder > 0:
        annual = remainder / assumptions.capital_allowance_remaining_years
        for index in range(1, min(years, assumptions.capital_allowance_remaining_years + 1)):
            schedule[index] += annual
    return schedule


def appraise_project_finance(
    annual_operating_value_gbp: float,
    assumptions: ProjectFinanceAssumptions,
) -> dict[str, Any]:
    """Build a screening debt/equity schedule from a year-one operating value."""
    if not np.isfinite(float(annual_operating_value_gbp)):
        raise ValueError("Annual operating value must be finite.")
    debt_opening = assumptions.total_capex_gbp * assumptions.debt_fraction
    equity_initial = assumptions.total_capex_gbp - debt_opening
    debt_payment = _annual_debt_service(
        debt_opening, assumptions.debt_interest_rate, assumptions.debt_tenor_years
    )
    allowance = _capital_allowance_schedule(assumptions)
    rows: list[dict[str, float | int | bool]] = []
    project_cashflows = [-assumptions.total_capex_gbp]
    equity_cashflows = [-equity_initial]
    current_debt = debt_opening
    for year in range(1, assumptions.asset_life_years + 1):
        degradation = (1.0 - assumptions.annual_revenue_degradation_fraction) ** (year - 1)
        operating_value = float(annual_operating_value_gbp * degradation)
        fixed_opex = float(assumptions.fixed_opex_gbp_per_year)
        ebitda = operating_value - fixed_opex
        opening_debt = current_debt
        if year <= assumptions.debt_tenor_years and opening_debt > 1e-8:
            interest = opening_debt * assumptions.debt_interest_rate
            principal = min(max(debt_payment - interest, 0.0), opening_debt)
            debt_service = interest + principal
        else:
            interest = principal = debt_service = 0.0
        closing_debt = max(opening_debt - principal, 0.0)
        tax_allowance = float(allowance[year - 1])
        unlevered_taxable = max(ebitda - tax_allowance, 0.0)
        levered_taxable = max(ebitda - tax_allowance - interest, 0.0)
        unlevered_tax = unlevered_taxable * assumptions.corporation_tax_rate
        cash_tax = levered_taxable * assumptions.corporation_tax_rate
        replacement = (
            assumptions.replacement_cost_gbp
            if assumptions.replacement_year == year else 0.0
        )
        cfads = ebitda - cash_tax
        dscr = cfads / debt_service if debt_service > 0 else np.nan
        project_cf = ebitda - unlevered_tax - replacement
        equity_cf = cfads - debt_service - replacement
        project_cashflows.append(float(project_cf))
        equity_cashflows.append(float(equity_cf))
        rows.append({
            "year": year,
            "degradation_factor": float(degradation),
            "operating_value_gbp": operating_value,
            "fixed_opex_gbp": fixed_opex,
            "ebitda_gbp": float(ebitda),
            "capital_allowance_gbp": tax_allowance,
            "unlevered_tax_gbp": float(unlevered_tax),
            "cash_tax_after_interest_gbp": float(cash_tax),
            "replacement_cost_gbp": float(replacement),
            "debt_opening_gbp": float(opening_debt),
            "interest_gbp": float(interest),
            "principal_gbp": float(principal),
            "debt_service_gbp": float(debt_service),
            "debt_closing_gbp": float(closing_debt),
            "cfads_gbp": float(cfads),
            "dscr": float(dscr) if np.isfinite(dscr) else np.nan,
            "project_cashflow_gbp": float(project_cf),
            "equity_cashflow_gbp": float(equity_cf),
            "dscr_breach": bool(debt_service > 0 and dscr < assumptions.dscr_threshold),
        })
        current_debt = closing_debt

    debt_rows = [row for row in rows if row["debt_service_gbp"] > 0]
    min_dscr = min((float(row["dscr"]) for row in debt_rows), default=float("nan"))
    initial_debt = assumptions.total_capex_gbp * assumptions.debt_fraction
    if initial_debt > 0:
        pv_cfads_loan_life = sum(
            float(row["cfads_gbp"]) / ((1.0 + assumptions.debt_interest_rate) ** int(row["year"]))
            for row in rows[: assumptions.debt_tenor_years]
        )
        llcr = pv_cfads_loan_life / initial_debt
    else:
        llcr = float("inf")
    project_irr = _irr(project_cashflows)
    equity_irr = _irr(equity_cashflows)
    project_npv = _npv(assumptions.project_discount_rate, project_cashflows)
    equity_npv = _npv(assumptions.equity_hurdle_rate, equity_cashflows)
    return {
        "annual_operating_value_gbp_year1": float(annual_operating_value_gbp),
        "debt_amount_gbp": float(initial_debt),
        "initial_equity_gbp": float(equity_initial),
        "annual_debt_service_gbp": float(debt_payment),
        "project_npv_gbp": float(project_npv),
        "project_irr_fraction": project_irr,
        "equity_npv_gbp": float(equity_npv),
        "equity_irr_fraction": equity_irr,
        "minimum_dscr": float(min_dscr),
        "llcr": float(llcr),
        "dscr_threshold": float(assumptions.dscr_threshold),
        "dscr_breach_years": int(sum(bool(row["dscr_breach"]) for row in rows)),
        "total_cash_tax_gbp": float(sum(float(row["cash_tax_after_interest_gbp"]) for row in rows)),
        "total_interest_gbp": float(sum(float(row["interest_gbp"]) for row in rows)),
        "project_cashflows_gbp": project_cashflows,
        "equity_cashflows_gbp": equity_cashflows,
        "yearly_schedule": rows,
        "tax_boundary": "simplified screening tax; no loss carry-forward, group relief, VAT or legal eligibility opinion",
        "capital_allowance_boundary": "user-defined screening allowance schedule, not a claim that this asset qualifies for a specific UK allowance",
    }
