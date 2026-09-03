from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import adapters.market_reference as market_reference


def _payload(periods: int = 48) -> bytes:
    data = []
    for period in range(1, periods + 1):
        data.extend([
            {
                "startTime": f"2026-09-01T00:00:00Z",
                "dataProvider": "APXMIDP",
                "settlementDate": "2026-09-01",
                "settlementPeriod": period,
                "price": 50.0 + period,
                "volume": 1000.0 + period,
            },
            {
                "startTime": f"2026-09-01T00:00:00Z",
                "dataProvider": "N2EXMIDP",
                "settlementDate": "2026-09-01",
                "settlementPeriod": period,
                "price": 0.0,
                "volume": 0.0,
            },
        ])
    return json.dumps({"data": data}).encode("utf-8")


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


def test_fetch_market_index_filters_provider_and_validates_day(monkeypatch) -> None:
    monkeypatch.setattr(
        market_reference,
        "urlopen",
        lambda *_args, **_kwargs: _Response(_payload()),
    )
    frame = market_reference.fetch_market_index_prices("2026-09-01")
    assert len(frame) == 48
    assert frame["market_index_provider"].eq("APXMIDP").all()
    assert frame["settlement_period"].tolist() == list(range(1, 49))
    assert frame["market_index_price_gbp_per_mwh"].iloc[0] == 51.0


def test_fetch_market_index_rejects_incomplete_day(monkeypatch) -> None:
    monkeypatch.setattr(
        market_reference,
        "urlopen",
        lambda *_args, **_kwargs: _Response(_payload(47)),
    )
    with pytest.raises(ValueError, match="expected 46/48/50"):
        market_reference.fetch_market_index_prices("2026-09-01")


def test_licensed_day_ahead_contract_enforces_publication_cutoff(tmp_path: Path) -> None:
    frame = pd.DataFrame({
        "settlement_date": ["2026-09-02"] * 48,
        "settlement_period": range(1, 49),
        "valid_time_utc": pd.date_range("2026-09-01T23:00Z", periods=48, freq="30min"),
        "publication_time_utc": ["2026-09-01T11:00Z"] * 48,
        "day_ahead_price_gbp_per_mwh": [100.0] * 48,
        "source": ["licensed_fixture"] * 48,
    })
    path = tmp_path / "day_ahead.csv"
    frame.to_csv(path, index=False)
    loaded = market_reference.load_licensed_day_ahead_prices(
        path, issue_cutoff_utc="2026-09-01T12:00Z"
    )
    assert len(loaded) == 48
    with pytest.raises(ValueError, match="published after"):
        market_reference.load_licensed_day_ahead_prices(
            path, issue_cutoff_utc="2026-09-01T10:00Z"
        )
