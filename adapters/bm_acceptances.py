"""Elexon BOALF ingestion for BM acceptance evidence."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import requests

API_URL="https://data.elexon.co.uk/bmrs/api/v1/balancing/acceptances/all/latest"
REQUIRED={"settlementDate","settlementPeriodFrom","settlementPeriodTo","timeFrom","timeTo","levelFrom","levelTo","bmUnit","acceptanceNumber","acceptanceTime","storFlag"}

def fetch_latest_bm_acceptances(timeout: float=20.0) -> pd.DataFrame:
    response=requests.get(API_URL,timeout=timeout); response.raise_for_status()
    payload=response.json(); frame=pd.DataFrame(payload.get("data",[]))
    return validate_bm_acceptances(frame)

def validate_bm_acceptances(frame: pd.DataFrame) -> pd.DataFrame:
    missing=sorted(REQUIRED.difference(frame.columns))
    if missing: raise ValueError(f"BOALF data missing columns: {missing}")
    out=frame.copy()
    for c in ("timeFrom","timeTo","acceptanceTime"): out[c]=pd.to_datetime(out[c],utc=True,errors="raise")
    out["settlementDate"]=pd.to_datetime(out["settlementDate"],errors="raise").dt.date.astype(str)
    out["direction"]=((pd.to_numeric(out["levelTo"])-pd.to_numeric(out["levelFrom"])).apply(lambda x:"up" if x>0 else ("down" if x<0 else "flat")))
    out["accepted_delta_mw"]=(pd.to_numeric(out["levelTo"])-pd.to_numeric(out["levelFrom"])).abs()
    return out

def append_acceptance_archive(latest: pd.DataFrame, path: Path) -> pd.DataFrame:
    current=pd.read_csv(path) if path.exists() else pd.DataFrame()
    incoming=latest.copy()
    for c in ("timeFrom","timeTo","acceptanceTime"):
        if c in incoming: incoming[c]=incoming[c].astype(str)
    combined=pd.concat([current,incoming],ignore_index=True,sort=False)
    keys=[c for c in ("settlementDate","bmUnit","acceptanceNumber","timeFrom","timeTo") if c in combined]
    if keys: combined=combined.drop_duplicates(keys,keep="last")
    combined=combined.sort_values([c for c in ("settlementDate","acceptanceTime") if c in combined]).reset_index(drop=True)
    path.parent.mkdir(parents=True,exist_ok=True); combined.to_csv(path,index=False)
    return combined
