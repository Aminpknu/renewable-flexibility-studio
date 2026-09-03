from pathlib import Path

import numpy as np
import pandas as pd

from engine.multiservice_forecast import (
    build_multiservice_forecast_features, forecast_multiservice_day,
)

ROOT = Path(__file__).resolve().parents[1]


def test_multiservice_price_forecast_does_not_use_target_day_price() -> None:
    history = pd.read_csv(ROOT / "data" / "neso_multiservice_forecast_history.csv")
    features = build_multiservice_forecast_features(history)
    baseline, meta = forecast_multiservice_day(features, "2026-05-01")
    changed = features.copy()
    target = pd.to_datetime(changed["service_date"]).dt.normalize().eq(pd.Timestamp("2026-05-01"))
    changed.loc[target, "clearing_price_gbp_per_mw_per_hour"] += 1000.0
    alternate, _ = forecast_multiservice_day(changed, "2026-05-01")
    assert np.allclose(
        baseline["forecast_clearing_price_gbp_per_mw_per_hour"],
        alternate["forecast_clearing_price_gbp_per_mw_per_hour"],
    )
    assert meta["uses_target_date_clearing_price"] is False


def test_stage13_price_backtest_has_all_current_products() -> None:
    frame = pd.read_csv(ROOT / "outputs" / "multiservice" / "stage13_price_forecast_backtest.csv")
    assert frame["product"].nunique() == 12
    assert frame["service_date"].nunique() == 61
    assert "prior_same_window_price_gbp_per_mw_per_hour" in frame.columns
