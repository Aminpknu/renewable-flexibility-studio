from __future__ import annotations

import numpy as np
import pandas as pd

from engine.monte_carlo import (
    MonteCarloConfig,
    MonteCarloDistributions,
    TriangularMultiplier,
    resample_complete_settlement_days,
    run_value_monte_carlo,
)
from engine.value import ValueAssumptions


def _daily_evidence(days: int = 20) -> pd.DataFrame:
    return pd.DataFrame({
        "settlement_date": pd.date_range("2026-01-01", periods=days, freq="D"),
        "avoided_exposure_mwh": np.linspace(40.0, 80.0, days),
        "throughput_mwh": np.linspace(50.0, 90.0, days),
    })


def test_monte_carlo_is_reproducible_with_fixed_seed() -> None:
    assumptions = ValueAssumptions(100.0, 1_000_000.0, 20_000.0, 1.0, 10, 0.05, 0.01)
    config = MonteCarloConfig(simulations=50, seed=123, sample_days=30, block_days=3)
    first, first_summary = run_value_monte_carlo(_daily_evidence(), assumptions, config)
    second, second_summary = run_value_monte_carlo(_daily_evidence(), assumptions, config)
    pd.testing.assert_frame_equal(first, second)
    assert first_summary == second_summary


def test_complete_day_resampling_preserves_dst_day_period_counts() -> None:
    counts = {"2026-03-28": 48, "2026-03-29": 46, "2026-10-25": 50}
    parts = []
    for date, count in counts.items():
        parts.append(pd.DataFrame({
            "settlement_date": [pd.Timestamp(date)] * count,
            "settlement_period": range(1, count + 1),
        }))
    frame = pd.concat(parts, ignore_index=True)
    sample = resample_complete_settlement_days(
        frame, sample_days=12, block_days=2, rng=np.random.default_rng(7)
    )
    for _, group in sample.groupby("bootstrap_day"):
        source = group["source_settlement_date"].iloc[0].strftime("%Y-%m-%d")
        assert len(group) == counts[source]

def test_daily_value_evidence_resets_soc_and_reports_firming() -> None:
    from engine.battery import BatteryConfig
    from engine.monte_carlo import build_daily_value_evidence

    dates = [pd.Timestamp("2026-01-01")] * 2 + [pd.Timestamp("2026-01-02")] * 2
    frame = pd.DataFrame({
        "settlement_date": dates,
        "settlement_period": [1, 2, 1, 2],
        "valid_time_utc": pd.date_range("2026-01-01T00:00Z", periods=4, freq="30min"),
        "actual_mw": [0.0, 10.0, 0.0, 10.0],
        "forecast_mw": [5.0, 5.0, 5.0, 5.0],
    })
    evidence = build_daily_value_evidence(frame, BatteryConfig(power_mw=5, duration_hours=2))
    assert len(evidence) == 2
    assert (evidence["period_count"] == 2).all()
    assert evidence["avoided_exposure_mwh"].gt(0).all()
    assert evidence["absorbed_pct"].between(0, 100).all()


def test_monte_carlo_reports_probability_of_failing_design_gate() -> None:
    evidence = _daily_evidence(30)
    evidence["absorbed_pct"] = np.linspace(70.0, 100.0, len(evidence))
    assumptions = ValueAssumptions(100.0, 1_000_000.0, 20_000.0, 1.0, 10, 0.05, 0.01)
    config = MonteCarloConfig(
        simulations=80, seed=44, sample_days=30, block_days=3,
        firming_target_pct=90.0, reliability_target_pct=50.0,
    )
    results, summary = run_value_monte_carlo(evidence, assumptions, config)
    assert "firming_gate_met" in results.columns
    assert 0 <= summary["probability_failing_firming_gate_pct"] <= 100
    assert summary["firming_target_pct"] == 90.0
    assert summary["reliability_target_pct"] == 50.0


def test_availability_outage_days_can_fail_reliability_gate() -> None:
    evidence = _daily_evidence(40)
    evidence["absorbed_pct"] = 100.0
    assumptions = ValueAssumptions(100.0, 1_000_000.0, 20_000.0, 1.0, 10, 0.05, 0.01)
    distributions = MonteCarloDistributions(
        availability_fraction=TriangularMultiplier(0.80, 0.80, 0.80)
    )
    _results, summary = run_value_monte_carlo(
        evidence, assumptions,
        MonteCarloConfig(
            simulations=60, seed=9, sample_days=365, block_days=5,
            firming_target_pct=90.0, reliability_target_pct=90.0,
        ),
        distributions,
    )
    assert summary["probability_failing_firming_gate_pct"] == 100.0
