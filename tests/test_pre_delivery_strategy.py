import pandas as pd
import pytest

from engine.battery import BatteryConfig
from engine.pre_delivery_strategy import build_reserve_soc_corridor


def test_reserve_energy_converts_to_soc_corridor_with_efficiency() -> None:
    battery = BatteryConfig(
        power_mw=10, duration_hours=4, round_trip_efficiency=0.81,
        initial_soc_fraction=0.5,
    )
    frame = pd.DataFrame({
        "settlement_period": [1, 2],
        "downward_reserve_requirement_mwh": [9.0, 0.0],
        "upward_headroom_requirement_mwh": [0.0, 9.0],
    })
    corridor, meta = build_reserve_soc_corridor(frame, battery)
    assert corridor.loc[0, "soc_floor_mwh"] == pytest.approx(14.0)
    assert corridor.loc[1, "soc_ceiling_mwh"] == pytest.approx(27.9)
    assert meta["all_periods_feasible"] is True
