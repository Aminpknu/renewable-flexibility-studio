from pathlib import Path

import numpy as np
import pandas as pd

from adapters.market_reference import load_market_index_history
from engine.price_forecast import (
    MarketPriceForecastConfig,
    backtest_market_price_forecast,
    build_market_price_features,
    forecast_market_price_day,
)

ROOT = Path(__file__).resolve().parents[1]
MARKET = load_market_index_history(ROOT / "data" / "elexon_market_index_prices.csv")


def test_target_day_prices_do_not_change_its_forecast() -> None:
    target = "2025-06-15"
    cfg = MarketPriceForecastConfig(minimum_history_days=30, ridge_alpha=20.0)
    base_features = build_market_price_features(MARKET)
    base, _ = forecast_market_price_day(base_features, target, cfg)
    changed = MARKET.copy()
    mask = changed["settlement_date"].eq(pd.Timestamp(target))
    changed.loc[mask, "market_index_price_gbp_per_mwh"] += 1000.0
    changed_features = build_market_price_features(changed)
    alternative, _ = forecast_market_price_day(changed_features, target, cfg)
    assert np.allclose(
        base["forecast_market_index_price_gbp_per_mwh"],
        alternative["forecast_market_index_price_gbp_per_mwh"],
    )


def test_price_forecast_supports_dst_target_days() -> None:
    features = build_market_price_features(MARKET)
    cfg = MarketPriceForecastConfig(minimum_history_days=30)
    spring, _ = forecast_market_price_day(features, "2026-03-29", cfg)
    autumn, _ = forecast_market_price_day(features, "2025-10-26", cfg)
    assert len(spring) == 46
    assert len(autumn) == 50


def test_installed_price_forecast_improves_mae_over_naive_lag() -> None:
    result, summary = backtest_market_price_forecast(
        MARKET, MarketPriceForecastConfig(minimum_history_days=30, ridge_alpha=20.0)
    )
    assert result["settlement_date"].nunique() == 420
    assert summary["mae_improvement_vs_naive_pct"] > 5.0
    assert summary["forecast"]["r2"] > summary["naive_previous_observed_same_period"]["r2"]
    assert summary["issue_rule"] == "strictly earlier settlement dates only"
