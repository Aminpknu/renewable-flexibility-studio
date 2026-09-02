"""Validate and load standalone historical forecast evidence."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

MINIMUM_COLUMNS = {
    "settlement_date",
    "settlement_period",
    "valid_time_utc",
    "wind_cf",
    "solar_cf",
    "wind_pred_cf",
    "solar_pred_cf",
}


def load_historical_predictions(path: str | Path) -> pd.DataFrame:
    """Load CSV or Parquet historical predictions under a stable contract."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Historical forecast bundle does not exist: {source}")
    if source.suffix.lower() == ".parquet":
        frame = pd.read_parquet(source)
    elif source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
    else:
        raise ValueError("Historical bundle must be CSV or Parquet.")

    missing = sorted(MINIMUM_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Historical bundle is missing columns: {missing}")
    frame = frame.copy()
    frame["settlement_date"] = pd.to_datetime(
        frame["settlement_date"], errors="raise"
    ).dt.normalize()
    frame["valid_time_utc"] = pd.to_datetime(
        frame["valid_time_utc"], utc=True, errors="raise"
    )
    frame["settlement_period"] = pd.to_numeric(
        frame["settlement_period"], errors="raise"
    ).astype(int)
    if frame.duplicated(["settlement_date", "settlement_period"]).any():
        raise ValueError("Historical bundle contains duplicate settlement periods.")
    if frame[list(MINIMUM_COLUMNS - {"settlement_date", "valid_time_utc"})].isna().any().any():
        raise ValueError("Historical bundle contains missing required values.")

    counts = frame.groupby("settlement_date")["settlement_period"].nunique()
    invalid = counts.loc[~counts.isin([46, 48, 50])]
    if not invalid.empty:
        raise ValueError(
            "Historical bundle contains incomplete GB settlement days: "
            + ", ".join(f"{date.date()}={count}" for date, count in invalid.items())
        )
    return frame.sort_values(["settlement_date", "settlement_period"]).reset_index(drop=True)


def available_dates(frame: pd.DataFrame) -> list[str]:
    """Return selectable dates in ISO format."""

    if "settlement_date" not in frame.columns:
        raise ValueError("Data frame has no settlement_date column.")
    return [value.strftime("%Y-%m-%d") for value in sorted(frame["settlement_date"].unique())]


def select_date(frame: pd.DataFrame, date_value: str) -> pd.DataFrame:
    """Select one complete historical target day."""

    target = pd.Timestamp(date_value).normalize()
    selected = frame.loc[frame["settlement_date"].eq(target)].copy()
    if selected.empty:
        raise KeyError(f"No historical evidence is available for {target.date()}.")
    return selected.sort_values("settlement_period").reset_index(drop=True)
