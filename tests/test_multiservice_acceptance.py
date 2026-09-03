import pandas as pd

from engine.multiservice_acceptance import predict_acceptance_ratio


def _calibration() -> pd.DataFrame:
    return pd.DataFrame([
        {"sample_class":"standalone_parent","product":"PQR","margin_bin":"-0.5:0","quantity_bin":"10:25","orders":200,"accepted_fraction_sum":120.0},
        {"sample_class":"standalone_parent","product":"PQR","margin_bin":"0:0.5","quantity_bin":"10:25","orders":200,"accepted_fraction_sum":40.0},
        {"sample_class":"nonlooped_parent","product":"PQR","margin_bin":"-0.5:0","quantity_bin":"10:25","orders":500,"accepted_fraction_sum":250.0},
        {"sample_class":"nonlooped_parent","product":"NBR","margin_bin":"-0.5:0","quantity_bin":"10:25","orders":300,"accepted_fraction_sum":90.0},
    ])


def test_acceptance_lookup_uses_issue_time_bid_margin() -> None:
    calibration = _calibration()
    cheap, meta = predict_acceptance_ratio(calibration, "PQR", 9.8, 20.0, 10.0)
    expensive, _ = predict_acceptance_ratio(calibration, "PQR", 10.2, 20.0, 10.0)
    assert 0 <= expensive < cheap <= 1
    assert meta["level"].startswith("standalone_parent")


def test_acceptance_lookup_falls_back_to_broad_parent_when_needed() -> None:
    probability, meta = predict_acceptance_ratio(_calibration(), "NBR", 9.8, 20.0, 10.0)
    assert 0 <= probability <= 1
    assert meta["level"].startswith("nonlooped_parent")
