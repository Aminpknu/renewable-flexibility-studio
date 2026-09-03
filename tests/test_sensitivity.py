from __future__ import annotations

from engine.sensitivity import build_capex_consequence_sensitivity
from engine.value import ValueAssumptions


def test_sensitivity_is_monotonic_in_consequence_and_capex() -> None:
    base = ValueAssumptions(
        consequence_value_gbp_per_mwh=100.0,
        total_capex_gbp=1_000_000.0,
        fixed_opex_gbp_per_year=10_000.0,
        asset_life_years=10,
        discount_rate=0.05,
        annual_degradation_fraction=0.01,
    )
    table = build_capex_consequence_sensitivity(
        20_000.0,
        5_000.0,
        base,
        consequence_values_gbp_per_mwh=[50.0, 100.0],
        capex_multipliers=[0.8, 1.2],
    )
    assert len(table) == 4
    low_value = table[table["consequence_value_gbp_per_mwh"].eq(50.0)]
    high_value = table[table["consequence_value_gbp_per_mwh"].eq(100.0)]
    assert high_value["npv_gbp"].min() > low_value["npv_gbp"].min()
    for _, group in table.groupby("consequence_value_gbp_per_mwh"):
        ordered = group.sort_values("capex_multiplier")
        assert ordered["npv_gbp"].iloc[0] > ordered["npv_gbp"].iloc[-1]