import pandas as pd
import pytest
from engine.site_constraints import SiteConstraintConfig, apply_site_envelope, site_capability

def test_site_capability_respects_poc_soh_and_warranty():
    cfg=SiteConstraintConfig(10,20,5,0.01,True,1.5,10000,50,0.8)
    out=site_capability(25,200,0.9,cfg)
    assert out['usable_energy_mwh']==pytest.approx(180)
    assert out['effective_charge_power_mw']==10
    assert out['effective_discharge_power_mw']==20
    assert out['annual_throughput_cap_mwh']==10000

def test_site_envelope_clips_connection_and_ramp():
    frame=pd.DataFrame({'charge_mw':[0,30,0],'discharge_mw':[0,0,30]})
    cfg=SiteConstraintConfig(10,20,5)
    out,summary=apply_site_envelope(frame,cfg)
    assert out['site_charge_mw'].max()<=10
    assert out['site_discharge_mw'].max()<=20
    assert out['site_net_export_mw'].diff().dropna().abs().max()<=5+1e-9
    assert summary['throughput_mwh']>=0

def test_grid_charge_can_be_blocked():
    cfg=SiteConstraintConfig(10,20,5,grid_charging_allowed=False)
    assert site_capability(25,100,1,cfg)['effective_charge_power_mw']==0
