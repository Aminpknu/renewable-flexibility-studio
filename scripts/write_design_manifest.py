"""Write the reproducibility manifest for the precomputed future-sizing grid."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from engine.design_sizing import DEFAULT_DURATIONS_HOURS, DEFAULT_POWER_FRACTIONS, select_stable_design

ROOT = Path(__file__).resolve().parents[1]
GRID_PATH = ROOT / "outputs" / "design_sizing_grid_100mw.csv"
MANIFEST_PATH = ROOT / "outputs" / "design_sizing_grid_manifest.json"


def _canonical_sha(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _default_design(grid: pd.DataFrame, share: int) -> dict[str, float | str]:
    selected = select_stable_design(grid.loc[grid["wind_share_pct"].eq(share)], 90, 90)
    if selected is None:
        raise RuntimeError(f"No default 90/90 stable design for wind share {share}%.")
    return {key: selected[key] for key in (
        "power_mw", "energy_mwh", "duration_hours", "classification",
        "development_overall_absorbed_pct", "locked_overall_absorbed_pct",
        "development_days90_pct", "locked_days90_pct",
    )}


def main() -> None:
    grid = pd.read_csv(GRID_PATH)
    manifest = {
        "schema_version": "1.0",
        "purpose": "future_battery_sizing_benchmark",
        "reference_portfolio_capacity_mw": 100.0,
        "wind_share_steps_pct": list(range(0, 101, 5)),
        "power_fractions_of_portfolio": list(DEFAULT_POWER_FRACTIONS),
        "duration_candidates_hours": list(DEFAULT_DURATIONS_HOURS),
        "candidate_cells_per_mix": len(DEFAULT_POWER_FRACTIONS) * len(DEFAULT_DURATIONS_HOURS),
        "rows": int(len(grid)),
        "operating_mode": "grid_connected_daily_soc_restore_50pct",
        "initial_and_daily_target_soc_pct": 50.0,
        "soc_bounds_pct": [10.0, 90.0],
        "round_trip_efficiency_pct": 90.0,
        "intraday_grid_charging": False,
        "pre_day_soc_restoration_energy_tracked": True,
        "design_targets_pct": [80, 90, 95],
        "reliability_targets_pct": [80, 90, 95],
        "stability_periods": ["development_oof", "locked_test"],
        "selection_rule": "minimum energy_mwh, then power_mw, then duration_hours, while meeting overall and daily reliability gates in both historical periods",
        "sha256": _canonical_sha(GRID_PATH),
        "sha256_normalisation": "UTF-8 text with LF line endings",
        "default_90_90_designs_100mw": {
            "solar": _default_design(grid, 0),
            "mixed_50_50": _default_design(grid, 50),
            "wind": _default_design(grid, 100),
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
