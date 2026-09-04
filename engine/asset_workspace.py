"""Persistent user-scenario asset workspace helpers.

Stage 18 deliberately separates site configuration from evidence quality: a saved
asset describes technical assumptions but does not convert national evidence into
a site-specific forecast or connection study.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .battery import BatteryConfig


@dataclass(frozen=True)
class AssetConfig:
    asset_name: str
    location_label: str
    power_mw: float
    duration_hours: float
    grid_import_limit_mw: float
    grid_export_limit_mw: float
    round_trip_efficiency: float = 0.90
    minimum_soc_fraction: float = 0.10
    maximum_soc_fraction: float = 0.90
    initial_soc_fraction: float = 0.50
    state_of_health_fraction: float = 1.0

    def __post_init__(self) -> None:
        if not self.asset_name.strip():
            raise ValueError("Asset name cannot be empty.")
        values = [
            self.power_mw, self.duration_hours, self.grid_import_limit_mw,
            self.grid_export_limit_mw, self.round_trip_efficiency,
            self.minimum_soc_fraction, self.maximum_soc_fraction,
            self.initial_soc_fraction, self.state_of_health_fraction,
        ]
        if not all(np.isfinite(float(v)) for v in values):
            raise ValueError("Asset configuration values must be finite.")
        if min(self.power_mw, self.duration_hours, self.grid_import_limit_mw,
               self.grid_export_limit_mw) <= 0:
            raise ValueError("Power, duration and grid limits must be positive.")
        if not 0 < self.round_trip_efficiency <= 1:
            raise ValueError("Round-trip efficiency must lie in (0, 1].")
        if not 0 <= self.minimum_soc_fraction < self.maximum_soc_fraction <= 1:
            raise ValueError("SOC limits are invalid.")
        if not self.minimum_soc_fraction <= self.initial_soc_fraction <= self.maximum_soc_fraction:
            raise ValueError("Initial SOC must lie inside the SOC band.")
        if not 0 < self.state_of_health_fraction <= 1:
            raise ValueError("State of health must lie in (0, 1].")
    @property
    def nameplate_energy_mwh(self) -> float:
        return float(self.power_mw * self.duration_hours)

    @property
    def available_energy_mwh(self) -> float:
        return float(self.nameplate_energy_mwh * self.state_of_health_fraction)

    @property
    def effective_charge_power_mw(self) -> float:
        return float(min(self.power_mw, self.grid_import_limit_mw))

    @property
    def effective_discharge_power_mw(self) -> float:
        return float(min(self.power_mw, self.grid_export_limit_mw))

    def to_battery_config(self) -> BatteryConfig:
        # BatteryConfig remains symmetric in power. Site-specific asymmetric grid
        # limits are preserved separately for market constraints and UI evidence.
        return BatteryConfig(
            power_mw=min(self.power_mw, self.grid_import_limit_mw, self.grid_export_limit_mw),
            duration_hours=self.available_energy_mwh /
            min(self.power_mw, self.grid_import_limit_mw, self.grid_export_limit_mw),
            round_trip_efficiency=self.round_trip_efficiency,
            initial_soc_fraction=self.initial_soc_fraction,
            minimum_soc_fraction=self.minimum_soc_fraction,
            maximum_soc_fraction=self.maximum_soc_fraction,
        )
    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["nameplate_energy_mwh"] = self.nameplate_energy_mwh
        record["available_energy_mwh"] = self.available_energy_mwh
        record["effective_charge_power_mw"] = self.effective_charge_power_mw
        record["effective_discharge_power_mw"] = self.effective_discharge_power_mw
        return record


def normalise_asset_store(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("Saved asset store must be a list.")
    records: list[dict[str, Any]] = []
    names: set[str] = set()
    fields = set(AssetConfig.__dataclass_fields__)
    for raw in data:
        if not isinstance(raw, dict):
            raise ValueError("Each saved asset must be an object.")
        config = AssetConfig(**{key: raw[key] for key in fields if key in raw})
        key = config.asset_name.strip().casefold()
        if key in names:
            raise ValueError("Saved asset names must be unique.")
        names.add(key)
        records.append(config.to_record())
    return records


def upsert_asset(data: Any, asset: AssetConfig) -> list[dict[str, Any]]:
    records = normalise_asset_store(data)
    key = asset.asset_name.strip().casefold()
    records = [r for r in records if str(r["asset_name"]).strip().casefold() != key]
    records.append(asset.to_record())
    return sorted(records, key=lambda r: str(r["asset_name"]).casefold())


def delete_asset(data: Any, asset_name: str) -> list[dict[str, Any]]:
    key = str(asset_name).strip().casefold()
    return [
        record for record in normalise_asset_store(data)
        if str(record["asset_name"]).strip().casefold() != key
    ]


def get_asset(data: Any, asset_name: str | None) -> AssetConfig | None:
    if not asset_name:
        return None
    key = str(asset_name).strip().casefold()
    fields = set(AssetConfig.__dataclass_fields__)
    for record in normalise_asset_store(data):
        if str(record["asset_name"]).strip().casefold() == key:
            return AssetConfig(**{name: record[name] for name in fields})
    return None
