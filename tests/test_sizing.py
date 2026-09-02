from pathlib import Path

from adapters.forecast_data import load_historical_predictions, select_date
from engine.portfolio import build_virtual_portfolio
from engine.sizing import find_minimum_battery

ROOT = Path(__file__).resolve().parents[1]
SOURCE = load_historical_predictions(ROOT / "data" / "sample_historical.csv")
DAY = select_date(SOURCE, "2025-06-01")


def test_sizing_returns_all_candidates_and_a_feasible_case() -> None:
    portfolio = build_virtual_portfolio(DAY, "mixed", 100.0, wind_share=0.5)
    best, comparison = find_minimum_battery(
        portfolio,
        target_absorbed_pct=30,
        power_candidates_mw=[5, 10, 25, 50],
        duration_candidates_hours=[1, 2, 4],
    )
    assert len(comparison) == 12
    assert set(comparison["duration_hours"]) == {1.0, 2.0, 4.0}
    assert best is not None
    assert best["error_reduction_pct"] >= 30


def test_impossible_target_can_return_no_feasible_case() -> None:
    portfolio = build_virtual_portfolio(DAY, "mixed", 100.0, wind_share=0.5)
    best, comparison = find_minimum_battery(
        portfolio,
        target_absorbed_pct=100,
        power_candidates_mw=[1],
        duration_candidates_hours=[1],
    )
    assert best is None
    assert not comparison["meets_target"].any()
