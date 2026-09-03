from pathlib import Path

import numpy as np
import pandas as pd

from adapters.neso_services import load_eac_service_history, load_service_specs
from engine.battery import BatteryConfig
from engine.multiservice import MultiServiceConfig, optimise_firming_arbitrage_and_services

ROOT = Path(__file__).resolve().parents[1]


def _base_inputs(periods: int, start: str = "2026-04-01T05:00:00Z"):
    times = pd.date_range(start, periods=periods, freq="30min")
    portfolio = pd.DataFrame({
        "settlement_period": range(1, periods + 1),
        "valid_time_utc": times,
        "actual_mw": 0.0,
        "forecast_mw": 0.0,
    })
    system = pd.DataFrame({"settlement_period": range(1, periods + 1), "system_price_gbp_per_mwh": 0.0})
    market = pd.DataFrame({"settlement_period": range(1, periods + 1), "market_index_price_gbp_per_mwh": 0.0})
    return portfolio, system, market


def _service(product, family, direction, start, end, price, volume=10.0, guard=0.5, bm=False):
    return {
        "product": product, "family": family, "direction": direction,
        "delivery_start_utc": pd.Timestamp(start), "delivery_end_utc": pd.Timestamp(end),
        "cleared_volume_mw": volume, "clearing_price_gbp_per_mw_per_hour": price,
        "window_hours": (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds() / 3600.0,
        "minimum_mw": 1, "whole_mw": True, "bm_required": bm, "energy_guard_hours": guard,
    }


def test_service_spec_and_archive_cover_current_eac_families() -> None:
    specs = load_service_specs()
    archive = load_eac_service_history(ROOT / "data" / "neso_multiservice_prices.csv")
    assert set(specs["product"]) == {"PQR", "NQR", "PSR", "NSR", "PBR", "NBR", "DCL", "DCH", "DML", "DMH", "DRL", "DRH"}
    assert set(archive["family"]) == {
        "Quick Reserve", "Slow Reserve", "Balancing Reserve",
        "Dynamic Containment", "Dynamic Moderation", "Dynamic Regulation",
    }
    assert len(archive) == 29514


def test_conservative_no_double_selling_limits_simultaneous_services() -> None:
    portfolio, system, market = _base_inputs(1)
    services = pd.DataFrame([
        _service("PQR", "Quick Reserve", "upward", "2026-04-01T05:00:00Z", "2026-04-01T05:30:00Z", 10.0, guard=0.25),
        _service("PSR", "Slow Reserve", "upward", "2026-04-01T05:00:00Z", "2026-04-01T05:30:00Z", 9.0, guard=0.25),
    ])
    battery = BatteryConfig(power_mw=10, duration_hours=2, round_trip_efficiency=0.90, initial_soc_fraction=0.75)
    frame, summary = optimise_firming_arbitrage_and_services(
        portfolio, system, market, services, battery,
        MultiServiceConfig(enable_firming=False, enable_arbitrage=False, enabled_families=("Quick Reserve", "Slow Reserve")),
    )
    contracted = frame[["quick_reserve_contracted_mw", "slow_reserve_contracted_mw"]].sum(axis=1)
    assert contracted.max() <= 10.0 + 1e-8
    assert summary["ancillary_availability_payment_gbp"] <= 50.0 + 1e-8


def test_balancing_reserve_requires_explicit_bm_eligibility() -> None:
    portfolio, system, market = _base_inputs(1)
    services = pd.DataFrame([
        _service("PBR", "Balancing Reserve", "upward", "2026-04-01T05:00:00Z", "2026-04-01T05:30:00Z", 20.0, guard=0.25, bm=True),
    ])
    battery = BatteryConfig(power_mw=10, duration_hours=2, round_trip_efficiency=0.90, initial_soc_fraction=0.75)
    _, non_bm = optimise_firming_arbitrage_and_services(
        portfolio, system, market, services, battery,
        MultiServiceConfig(enable_firming=False, enable_arbitrage=False, enabled_families=("Balancing Reserve",), assume_bm_eligible=False),
    )
    _, bm = optimise_firming_arbitrage_and_services(
        portfolio, system, market, services, battery,
        MultiServiceConfig(enable_firming=False, enable_arbitrage=False, enabled_families=("Balancing Reserve",), assume_bm_eligible=True),
    )
    assert non_bm["ancillary_availability_payment_gbp"] == 0.0
    assert bm["ancillary_availability_payment_gbp"] > 0.0


def test_response_commitment_is_one_four_hour_contract() -> None:
    portfolio, system, market = _base_inputs(8, "2026-04-01T06:00:00Z")
    services = pd.DataFrame([
        _service("DCL", "Dynamic Containment", "upward", "2026-04-01T06:00:00Z", "2026-04-01T10:00:00Z", 5.0, volume=5.0, guard=0.25),
    ])
    battery = BatteryConfig(power_mw=10, duration_hours=2, round_trip_efficiency=0.90, initial_soc_fraction=0.75)
    frame, _ = optimise_firming_arbitrage_and_services(
        portfolio, system, market, services, battery,
        MultiServiceConfig(enable_firming=False, enable_arbitrage=False, enabled_families=("Dynamic Containment",)),
    )
    assert frame["dynamic_containment_contracted_mw"].nunique() == 1
    assert frame["dynamic_containment_contracted_mw"].iloc[0] == 5.0


def test_psr_transition_windows_force_identical_mw() -> None:
    portfolio, system, market = _base_inputs(2, "2026-04-01T05:00:00Z")  # 06:00 local BST
    services = pd.DataFrame([
        _service("PSR", "Slow Reserve", "upward", "2026-04-01T05:00:00Z", "2026-04-01T05:30:00Z", 10.0, volume=5.0, guard=0.25),
        _service("PSR", "Slow Reserve", "upward", "2026-04-01T05:30:00Z", "2026-04-01T06:00:00Z", -5.0, volume=5.0, guard=0.25),
    ])
    battery = BatteryConfig(power_mw=10, duration_hours=2, round_trip_efficiency=0.90, initial_soc_fraction=0.75)
    frame, summary = optimise_firming_arbitrage_and_services(
        portfolio, system, market, services, battery,
        MultiServiceConfig(enable_firming=False, enable_arbitrage=False, enabled_families=("Slow Reserve",)),
    )
    values = frame["slow_reserve_contracted_mw"].tolist()
    assert values[0] == values[1] == 5.0
    assert summary["ancillary_availability_payment_gbp"] == 12.5


def test_multiservice_archive_manifest_locks_source_and_scope() -> None:
    import hashlib
    import json

    csv_path = ROOT / "data" / "neso_multiservice_prices.csv"
    manifest = json.loads((ROOT / "data" / "neso_multiservice_prices_manifest.json").read_text(encoding="utf-8"))
    assert manifest["rights"] == "NESO Open Data Licence"
    assert manifest["rows"] == 29514
    assert len(manifest["products"]) == 12
    assert set(manifest["families"]) == {
        "Quick Reserve", "Slow Reserve", "Balancing Reserve",
        "Dynamic Containment", "Dynamic Moderation", "Dynamic Regulation",
    }
    canonical = csv_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == manifest["sha256"]
