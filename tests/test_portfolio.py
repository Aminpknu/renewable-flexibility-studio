from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from adapters.forecast_data import load_historical_predictions, select_date
from engine.portfolio import build_virtual_portfolio

ROOT = Path(__file__).resolve().parents[1]
SOURCE = load_historical_predictions(ROOT / "data" / "sample_historical.csv")
DAY = select_date(SOURCE, "2025-06-01")


def test_wind_portfolio_scales_capacity_factor() -> None:
    portfolio = build_virtual_portfolio(DAY, "wind", 100.0)
    assert np.isclose(portfolio.loc[0, "actual_mw"], DAY.loc[0, "wind_cf"] * 100)
    assert np.isclose(portfolio.loc[0, "forecast_mw"], DAY.loc[0, "wind_pred_cf"] * 100)
    assert portfolio["wind_share"].eq(1.0).all()


def test_solar_portfolio_is_zero_at_night() -> None:
    portfolio = build_virtual_portfolio(DAY, "solar", 100.0)
    assert portfolio.loc[0, "actual_mw"] == 0
    assert portfolio.loc[0, "forecast_mw"] == 0
    assert portfolio["wind_share"].eq(0.0).all()


def test_mixed_portfolio_is_capacity_weighted() -> None:
    portfolio = build_virtual_portfolio(DAY, "mixed", 100.0, wind_share=0.6)
    expected = 100 * (0.6 * DAY.loc[20, "wind_cf"] + 0.4 * DAY.loc[20, "solar_cf"])
    assert np.isclose(portfolio.loc[20, "actual_mw"], expected)
    assert portfolio["wind_share"].eq(0.6).all()


def test_invalid_portfolio_inputs_raise() -> None:
    with pytest.raises(ValueError):
        build_virtual_portfolio(DAY, "mixed", 0)
    with pytest.raises(ValueError):
        build_virtual_portfolio(DAY, "mixed", 100, wind_share=1.2)
