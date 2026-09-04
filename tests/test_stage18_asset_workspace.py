import pytest

from engine.asset_workspace import (
    AssetConfig, delete_asset, get_asset, normalise_asset_store, upsert_asset,
)


def test_asset_config_derives_effective_limits_and_energy():
    asset = AssetConfig(
        asset_name="Guildford BESS", location_label="Guildford",
        power_mw=50, duration_hours=2, grid_import_limit_mw=30,
        grid_export_limit_mw=40, state_of_health_fraction=0.90,
    )
    assert asset.nameplate_energy_mwh == pytest.approx(100)
    assert asset.available_energy_mwh == pytest.approx(90)
    assert asset.effective_charge_power_mw == pytest.approx(30)
    assert asset.effective_discharge_power_mw == pytest.approx(40)
    battery = asset.to_battery_config()
    assert battery.power_mw == pytest.approx(30)
    assert battery.energy_capacity_mwh == pytest.approx(90)


def test_asset_store_upsert_replace_delete_and_get():
    a = AssetConfig("A", "North", 25, 4, 25, 25)
    b = AssetConfig("B", "South", 50, 2, 40, 45)
    store = upsert_asset(None, a)
    store = upsert_asset(store, b)
    assert [r["asset_name"] for r in store] == ["A", "B"]
    replacement = AssetConfig("A", "North", 30, 4, 25, 30)
    store = upsert_asset(store, replacement)
    assert len(store) == 2
    assert get_asset(store, "a").power_mw == pytest.approx(30)
    store = delete_asset(store, "B")
    assert [r["asset_name"] for r in store] == ["A"]


def test_asset_store_rejects_duplicate_names_and_invalid_soc():
    a = AssetConfig("A", "", 25, 2, 25, 25)
    raw = [a.to_record(), a.to_record()]
    with pytest.raises(ValueError, match="unique"):
        normalise_asset_store(raw)
    with pytest.raises(ValueError, match="SOC"):
        AssetConfig("X", "", 10, 2, 10, 10,
                    minimum_soc_fraction=.8, maximum_soc_fraction=.2)
