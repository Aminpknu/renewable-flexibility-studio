"""Build a versioned Elexon APX Market Index Price archive for V2 target days."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time

import pandas as pd

from adapters.forecast_data import load_historical_predictions
from adapters.market_reference import fetch_market_index_prices

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "historical_backtest.csv"
OUTPUT_PATH = ROOT / "data" / "elexon_market_index_prices.csv"
MANIFEST_PATH = ROOT / "data" / "elexon_market_index_prices_manifest.json"
PROVIDER = "APXMIDP"


def _fetch_with_retry(target: str, attempts: int = 3) -> pd.DataFrame:
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            frame = fetch_market_index_prices(target, PROVIDER, timeout_seconds=30)
            frame.insert(0, "settlement_date", target)
            return frame
        except Exception as exc:  # network retry boundary
            error = exc
            if attempt + 1 < attempts:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"Failed to fetch {target}: {error}")


def _canonical_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    history = load_historical_predictions(HISTORY_PATH)
    dates = sorted(
        pd.to_datetime(history["settlement_date"], errors="raise")
        .dt.strftime("%Y-%m-%d")
        .unique()
    )
    frames: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_fetch_with_retry, date): date for date in dates}
        for future in as_completed(futures):
            date = futures[future]
            try:
                frames[date] = future.result()
            except Exception as exc:
                failures[date] = str(exc)
            if (len(frames) + len(failures)) % 50 == 0:
                print(f"completed {len(frames) + len(failures)}/{len(dates)}", flush=True)
    if failures:
        raise RuntimeError(f"Market-index archive has fetch failures: {failures}")
    combined = pd.concat([frames[date] for date in dates], ignore_index=True)
    combined.to_csv(OUTPUT_PATH, index=False, lineterminator="\n")
    counts = combined.groupby("settlement_date")["settlement_period"].nunique()
    expected_counts = (
        history.groupby("settlement_date")["settlement_period"].nunique()
        .rename_axis("settlement_date")
    )
    expected_counts.index = pd.to_datetime(expected_counts.index).strftime("%Y-%m-%d")
    if not counts.equals(expected_counts.loc[counts.index]):
        mismatch = pd.DataFrame({"market": counts, "history": expected_counts}).dropna()
        mismatch = mismatch.loc[mismatch["market"].ne(mismatch["history"])]
        raise RuntimeError(f"Market-index settlement counts do not match V2 history: {mismatch.to_dict('index')}")
    manifest = {
        "schema_version": "1.0",
        "source": "Elexon Insights Market Index Data",
        "endpoint": "balancing/pricing/market-index",
        "data_provider": PROVIDER,
        "semantic_label": "short-term GB wholesale market reference; not day-ahead auction price",
        "target_days": int(len(dates)),
        "rows": int(len(combined)),
        "target_date_start": dates[0],
        "target_date_end": dates[-1],
        "sha256": _canonical_sha256(OUTPUT_PATH),
        "sha256_normalisation": "UTF-8 text with LF line endings",
        "public_api_key_required": False,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print("saved", OUTPUT_PATH)
    print("saved", MANIFEST_PATH)


if __name__ == "__main__":
    main()
