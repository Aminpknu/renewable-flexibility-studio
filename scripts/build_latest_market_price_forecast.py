"""Build a leakage-safe forecast-day APX Market Index price forecast."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from adapters.latest_forecast import latest_target_date, load_latest_forecast
from adapters.market_reference import fetch_market_index_prices
from engine.price_forecast import (
    MarketPriceForecastConfig,
    build_market_price_features,
    forecast_market_price_day,
)

ROOT = Path(__file__).resolve().parents[1]
LATEST_RENEWABLE = ROOT / "data" / "latest_forecast.csv"
OUTPUT = ROOT / "data" / "latest_market_price_forecast.csv"
MANIFEST = ROOT / "data" / "latest_market_price_forecast_manifest.json"
LOOKBACK_DAYS = 90


def _canonical_sha256(text: str) -> str:
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_forecast_bundle(
    output_path: str | Path = OUTPUT,
    manifest_path: str | Path = MANIFEST,
    *,
    target_date: str | None = None,
    lookback_days: int = LOOKBACK_DAYS,
) -> dict:
    renewable = load_latest_forecast(LATEST_RENEWABLE)
    target_text = target_date or latest_target_date(renewable)
    target = pd.Timestamp(target_text).normalize()
    parts = []
    for day in pd.date_range(
        target - pd.Timedelta(days=lookback_days),
        target - pd.Timedelta(days=1),
        freq="D",
    ):
        try:
            parts.append(fetch_market_index_prices(day.date().isoformat()))
        except (KeyError, ValueError) as error:
            print(f"skip {day.date()}: {error}", flush=True)
    if len(parts) < 30:
        raise RuntimeError(f"Only {len(parts)} prior market days were retrieved.")
    history = pd.concat(parts, ignore_index=True)
    history["settlement_date"] = pd.to_datetime(
        history["valid_time_utc"], utc=True
    ).dt.tz_convert("Europe/London").dt.date
    history["settlement_date"] = pd.to_datetime(history["settlement_date"])
    template = renewable[["settlement_period", "valid_time_utc"]].copy()
    if target_text != latest_target_date(renewable):
        raise ValueError("Target override must match the current renewable forecast target.")
    template["settlement_date"] = target
    template["market_index_provider"] = "forecast"
    template["market_index_price_gbp_per_mwh"] = float("nan")
    template["market_index_volume_mwh"] = float("nan")
    combined = pd.concat([
        history[[
            "settlement_date", "settlement_period", "valid_time_utc",
            "market_index_provider", "market_index_price_gbp_per_mwh",
            "market_index_volume_mwh",
        ]],
        template,
    ], ignore_index=True)
    features = build_market_price_features(combined)
    forecast, metadata = forecast_market_price_day(
        features,
        target,
        MarketPriceForecastConfig(minimum_history_days=30, ridge_alpha=20.0),
    )
    generated = pd.Timestamp.now(tz="UTC")
    output = forecast[[
        "settlement_date", "settlement_period", "valid_time_utc",
        "forecast_market_index_price_gbp_per_mwh",
        "naive_market_index_price_gbp_per_mwh",
    ]].copy()
    output.insert(0, "forecast_created_utc", generated.isoformat())
    csv_text = output.to_csv(index=False, lineterminator="\n")
    output_path = Path(output_path)
    manifest_path = Path(manifest_path)
    output_path.write_text(csv_text, encoding="utf-8", newline="")
    target_start = pd.to_datetime(output["valid_time_utc"], utc=True).min()
    payload = {
        "schema_version": "1.1",
        "target_date": target.date().isoformat(),
        "forecast_created_utc": generated.isoformat(),
        "source": "Elexon APXMIDP Market Index Data",
        "semantic_label": "forecast of short-term GB wholesale market reference; not day-ahead auction price",
        "history_start": min(pd.to_datetime(history["settlement_date"])).date().isoformat(),
        "history_end": max(pd.to_datetime(history["settlement_date"])).date().isoformat(),
        "retrieved_history_days": int(pd.to_datetime(history["settlement_date"]).nunique()),
        "method": metadata,
        "period_count": int(len(output)),
        "row_count": int(len(output)),
        "sha256": _canonical_sha256(csv_text),
        "sha256_normalisation": "UTF-8 text with LF line endings",
        "target_start_utc": target_start.isoformat(),
        "issued_before_target_start": bool(generated <= target_start),
        "operational_status": (
            "pre_delivery_issue" if generated <= target_start
            else "as_if_reconstruction_after_target_start"
        ),
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    payload = build_forecast_bundle()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
