"""Precompute 450-day battery design grids for every supported wind-share mix."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import os
import time

import pandas as pd

from adapters.forecast_data import load_historical_predictions
from engine.design_sizing import DEFAULT_DURATIONS_HOURS, DEFAULT_POWER_FRACTIONS, evaluate_stability_candidate
from engine.portfolio import build_virtual_portfolio

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "historical_backtest.csv"
OUTPUT = ROOT / "outputs" / "design_sizing_grid_100mw.csv"
WIND_SHARES = tuple(range(0, 101, 5))


def _one_mix(wind_share_pct: int) -> pd.DataFrame:
    history = load_historical_predictions(HISTORY)
    portfolio = build_virtual_portfolio(
        history, "mixed", 100.0, wind_share=float(wind_share_pct) / 100.0
    )
    rows = []
    for fraction in DEFAULT_POWER_FRACTIONS:
        power = 100.0 * fraction
        for duration in DEFAULT_DURATIONS_HOURS:
            row = evaluate_stability_candidate(
                portfolio, power, duration, target_pct=90.0,
                initial_soc_fraction=0.50, daily_soc_target_fraction=0.50,
            )
            row["wind_share_pct"] = int(wind_share_pct)
            row["design_operating_mode"] = "grid_connected_daily_soc_restore_50pct"
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    started = time.time()
    workers = min(8, os.cpu_count() or 4)
    parts = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_one_mix, share): share for share in WIND_SHARES}
        for future in as_completed(futures):
            share = futures[future]
            frame = future.result()
            parts.append(frame)
            print(f"wind share {share}% complete ({len(parts)}/{len(WIND_SHARES)})", flush=True)
    result = pd.concat(parts, ignore_index=True).sort_values(
        ["wind_share_pct", "energy_mwh", "power_mw", "duration_hours"]
    ).reset_index(drop=True)
    OUTPUT.parent.mkdir(exist_ok=True)
    result.to_csv(OUTPUT, index=False)
    print(f"saved {OUTPUT} rows={len(result)} seconds={time.time()-started:.1f}")


if __name__ == "__main__":
    main()
