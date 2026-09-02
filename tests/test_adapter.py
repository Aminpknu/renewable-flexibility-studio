from pathlib import Path

import pandas as pd
import pytest

from adapters.forecast_data import available_dates, load_historical_predictions, select_date

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_historical_day_is_complete() -> None:
    frame = load_historical_predictions(ROOT / "data" / "sample_historical.csv")
    assert len(frame) == 48
    assert available_dates(frame) == ["2025-06-01"]
    selected = select_date(frame, "2025-06-01")
    assert selected["settlement_period"].tolist() == list(range(1, 49))
    assert str(selected["valid_time_utc"].dtype).endswith("UTC]")


def test_incomplete_day_is_rejected(tmp_path: Path) -> None:
    source = pd.read_csv(ROOT / "data" / "sample_historical.csv").head(3)
    path = tmp_path / "incomplete.csv"
    source.to_csv(path, index=False)
    with pytest.raises(ValueError, match="incomplete"):
        load_historical_predictions(path)


def test_missing_date_raises() -> None:
    frame = load_historical_predictions(ROOT / "data" / "sample_historical.csv")
    with pytest.raises(KeyError):
        select_date(frame, "2025-06-02")


def test_v2_out_of_sample_bundle_is_complete_and_multi_day() -> None:
    frame = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")
    dates = available_dates(frame)
    assert len(frame) == 21600
    assert len(dates) == 450
    assert dates[0] == "2025-04-01"
    assert dates[-1] == "2026-06-30"
    assert "2025-08-06" not in dates
    assert "2026-06-24" not in dates
    assert set(frame["evaluation_segment"].unique()) == {"development_oof", "locked_test"}
