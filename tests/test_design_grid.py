from pathlib import Path

from adapters.design_grid import load_design_grid, scaled_design_grid
from engine.design_sizing import select_stable_design

ROOT = Path(__file__).resolve().parents[1]
GRID = load_design_grid(ROOT / "outputs" / "design_sizing_grid_100mw.csv")


def test_design_grid_covers_every_supported_mix() -> None:
    assert len(GRID) == 2541
    assert sorted(GRID["wind_share_pct"].unique()) == list(range(0, 101, 5))
    assert GRID["design_operating_mode"].nunique() == 1
    assert GRID["design_operating_mode"].iloc[0] == "grid_connected_daily_soc_restore_50pct"


def test_default_mixed_design_is_25mw_200mwh_for_90_90_gate() -> None:
    mixed = scaled_design_grid(GRID, "mixed", 100.0, 50.0)
    selected = select_stable_design(mixed, 90, 90)
    assert selected is not None
    assert selected["power_mw"] == 25.0
    assert selected["energy_mwh"] == 200.0
    assert selected["duration_hours"] == 8.0


def test_design_grid_scales_power_energy_and_grid_reset_with_portfolio_capacity() -> None:
    base = scaled_design_grid(GRID, "mixed", 100.0, 50.0)
    doubled = scaled_design_grid(GRID, "mixed", 200.0, 50.0)
    a = base.sort_values(["power_mw", "duration_hours"]).iloc[0]
    b = doubled.sort_values(["power_mw", "duration_hours"]).iloc[0]
    assert b["power_mw"] == 2 * a["power_mw"]
    assert b["energy_mwh"] == 2 * a["energy_mwh"]
    assert b["grid_reset_import_mwh"] == 2 * a["grid_reset_import_mwh"]
    assert b["duration_hours"] == a["duration_hours"]


def test_design_grid_manifest_locks_default_future_sizing() -> None:
    import hashlib, json
    path = ROOT / "outputs" / "design_sizing_grid_100mw.csv"
    manifest = json.loads((ROOT / "outputs" / "design_sizing_grid_manifest.json").read_text(encoding="utf-8"))
    canonical = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert manifest["rows"] == 2541
    assert manifest["operating_mode"] == "grid_connected_daily_soc_restore_50pct"
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == manifest["sha256"]
    default = manifest["default_90_90_designs_100mw"]["mixed_50_50"]
    assert default["power_mw"] == 25.0
    assert default["energy_mwh"] == 200.0
    assert default["duration_hours"] == 8.0
