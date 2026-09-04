"""Evidence summaries for Elexon BOALF acceptance archives."""
from __future__ import annotations
import numpy as np
import pandas as pd

def summarise_bm_acceptance_archive(frame: pd.DataFrame, min_storage_events: int=200) -> dict[str,object]:
    if frame.empty:
        return {"events":0,"storage_events":0,"calibration_ready":False,"boundary":"No BOALF archive has been collected yet."}
    required={"storFlag","direction","accepted_delta_mw","bmUnit","settlementDate"}
    missing=sorted(required.difference(frame.columns))
    if missing: raise ValueError(f"BM acceptance archive missing columns: {missing}")
    storage=frame[frame["storFlag"].astype(str).str.lower().isin(["true","1"])].copy()
    up=storage[storage["direction"]=="up"]; down=storage[storage["direction"]=="down"]
    n=len(storage); total=max(n,1)
    return {
        "events":int(len(frame)), "storage_events":int(n), "storage_bmus":int(storage["bmUnit"].nunique()) if n else 0,
        "storage_up_events":int(len(up)), "storage_down_events":int(len(down)),
        "storage_up_share":float(len(up)/total), "storage_down_share":float(len(down)/total),
        "mean_storage_delta_mw":float(pd.to_numeric(storage["accepted_delta_mw"],errors="coerce").mean()) if n else 0.0,
        "first_date":str(frame["settlementDate"].min()), "last_date":str(frame["settlementDate"].max()),
        "calibration_ready":bool(n>=min_storage_events),
        "boundary":"BOALF contains accepted instructions only. Without the corresponding complete submitted bid/offer opportunity set, this archive supports activation-direction/intensity evidence but not an unconditional acceptance probability.",
    }
