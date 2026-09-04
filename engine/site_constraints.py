"""Site and connection realism for a BESS or renewable+BESS scenario."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class SiteConstraintConfig:
    grid_import_limit_mw: float
    grid_export_limit_mw: float
    ramp_limit_mw_per_interval: float
    auxiliary_load_fraction: float = 0.01
    grid_charging_allowed: bool = True
    daily_cycle_limit: float = 2.0
    annual_throughput_limit_mwh: float | None = None
    colocated_renewable_mw: float = 0.0
    curtailment_cap_fraction: float = 1.0

    def __post_init__(self):
        vals=(self.grid_import_limit_mw,self.grid_export_limit_mw,self.ramp_limit_mw_per_interval,self.auxiliary_load_fraction,self.daily_cycle_limit,self.colocated_renewable_mw,self.curtailment_cap_fraction)
        if not all(np.isfinite(float(v)) for v in vals): raise ValueError("Site constraint values must be finite.")
        if min(self.grid_import_limit_mw,self.grid_export_limit_mw,self.ramp_limit_mw_per_interval) <= 0: raise ValueError("Connection and ramp limits must be positive.")
        if not 0 <= self.auxiliary_load_fraction < 1: raise ValueError("Auxiliary load fraction must be in [0,1).")
        if self.daily_cycle_limit <= 0: raise ValueError("Daily cycle limit must be positive.")
        if self.annual_throughput_limit_mwh is not None and self.annual_throughput_limit_mwh <= 0: raise ValueError("Annual throughput limit must be positive when set.")
        if self.colocated_renewable_mw < 0 or not 0 <= self.curtailment_cap_fraction <= 1: raise ValueError("Renewable and curtailment assumptions are invalid.")

def site_capability(power_mw: float, energy_mwh: float, state_of_health_fraction: float, cfg: SiteConstraintConfig) -> dict[str,float|bool]:
    if power_mw <= 0 or energy_mwh <= 0 or not 0 < state_of_health_fraction <= 1: raise ValueError("Battery capability inputs are invalid.")
    usable_nameplate = energy_mwh * state_of_health_fraction
    discharge_cap = min(power_mw, cfg.grid_export_limit_mw)
    charge_cap = min(power_mw, cfg.grid_import_limit_mw) if cfg.grid_charging_allowed else 0.0
    daily_throughput_cap = 2.0 * usable_nameplate * cfg.daily_cycle_limit
    annual_from_cycles = daily_throughput_cap * 365.0
    annual_cap = min(annual_from_cycles, cfg.annual_throughput_limit_mwh) if cfg.annual_throughput_limit_mwh else annual_from_cycles
    return {
        "usable_energy_mwh": float(usable_nameplate),
        "effective_charge_power_mw": float(charge_cap),
        "effective_discharge_power_mw": float(discharge_cap),
        "daily_throughput_cap_mwh": float(daily_throughput_cap),
        "annual_throughput_cap_mwh": float(annual_cap),
        "auxiliary_loss_at_full_power_mw": float(power_mw * cfg.auxiliary_load_fraction),
        "grid_charging_allowed": bool(cfg.grid_charging_allowed),
    }

def apply_site_envelope(schedule: pd.DataFrame, cfg: SiteConstraintConfig, *, charge_col: str="charge_mw", discharge_col: str="discharge_mw") -> tuple[pd.DataFrame,dict[str,float]]:
    if charge_col not in schedule or discharge_col not in schedule: raise ValueError("Schedule is missing charge/discharge columns.")
    frame=schedule.copy()
    ch=np.maximum(pd.to_numeric(frame[charge_col],errors="raise").to_numpy(float),0.0)
    dis=np.maximum(pd.to_numeric(frame[discharge_col],errors="raise").to_numpy(float),0.0)
    ch=np.minimum(ch,cfg.grid_import_limit_mw if cfg.grid_charging_allowed else 0.0)
    dis=np.minimum(dis,cfg.grid_export_limit_mw)
    net=dis-ch
    for i in range(1,len(net)):
        delta=net[i]-net[i-1]
        if abs(delta)>cfg.ramp_limit_mw_per_interval:
            net[i]=net[i-1]+np.sign(delta)*cfg.ramp_limit_mw_per_interval
            dis[i]=max(net[i],0.0); ch[i]=max(-net[i],0.0)
    frame["site_charge_mw"]=ch; frame["site_discharge_mw"]=dis; frame["site_net_export_mw"]=net
    throughput=float((ch+dis).sum()*0.5)
    aux=float((ch+dis).sum()*0.5*cfg.auxiliary_load_fraction)
    return frame,{"throughput_mwh":throughput,"auxiliary_energy_mwh":aux,"peak_import_mw":float(ch.max(initial=0)),"peak_export_mw":float(dis.max(initial=0))}
