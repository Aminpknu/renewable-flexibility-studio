"""Technical portfolio aggregation and transparent evidence-normalised benchmarking."""
from __future__ import annotations
import pandas as pd

def benchmark_asset_portfolio(asset_store: dict|None, reference_value_gbp_per_year: float, reference_power_mw: float=25.0) -> tuple[pd.DataFrame,dict[str,float]]:
    assets=(asset_store or {}).get("assets",{}) if isinstance(asset_store,dict) else {}
    rows=[]
    for key,item in assets.items():
        p=float(item["power_mw"]); h=float(item["duration_hours"]); soh=float(item.get("state_of_health_fraction",1.0))
        energy=p*h; available=energy*soh
        imp=float(item.get("grid_import_limit_mw",p)); exp=float(item.get("grid_export_limit_mw",p))
        connection=min(p,imp,exp)
        scaled_value=reference_value_gbp_per_year*(connection/reference_power_mw)
        rows.append({"asset_id":key,"asset_name":item.get("asset_name",key),"location":item.get("location_label",""),"power_mw":p,"energy_mwh":energy,"available_energy_mwh":available,"soh_pct":100*soh,"connection_limited_power_mw":connection,"duration_hours":h,"reference_scaled_value_gbp_per_year":scaled_value})
    frame=pd.DataFrame(rows)
    if frame.empty: return frame,{"asset_count":0,"total_power_mw":0.0,"total_energy_mwh":0.0,"available_energy_mwh":0.0,"reference_scaled_value_gbp_per_year":0.0}
    summary={"asset_count":int(len(frame)),"total_power_mw":float(frame.power_mw.sum()),"total_energy_mwh":float(frame.energy_mwh.sum()),"available_energy_mwh":float(frame.available_energy_mwh.sum()),"connection_limited_power_mw":float(frame.connection_limited_power_mw.sum()),"reference_scaled_value_gbp_per_year":float(frame.reference_scaled_value_gbp_per_year.sum())}
    return frame.sort_values(["connection_limited_power_mw","available_energy_mwh"],ascending=False).reset_index(drop=True),summary
