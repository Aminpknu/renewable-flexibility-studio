import pandas as pd
from adapters.bm_acceptances import validate_bm_acceptances
from engine.bm_evidence import summarise_bm_acceptance_archive

def sample():
    return pd.DataFrame([{'settlementDate':'2026-09-01','settlementPeriodFrom':1,'settlementPeriodTo':1,'timeFrom':'2026-09-01T00:00:00Z','timeTo':'2026-09-01T00:10:00Z','levelFrom':0,'levelTo':10,'bmUnit':'T_TESTB-1','acceptanceNumber':1,'acceptanceTime':'2026-08-31T23:55:00Z','storFlag':True}])

def test_bm_acceptance_validation_derives_direction():
    out=validate_bm_acceptances(sample())
    assert out.loc[0,'direction']=='up'
    assert out.loc[0,'accepted_delta_mw']==10

def test_bm_archive_summary_preserves_probability_boundary():
    out=validate_bm_acceptances(sample())
    summary=summarise_bm_acceptance_archive(out,min_storage_events=1)
    assert summary['storage_events']==1
    assert summary['calibration_ready'] is True
    assert 'not an unconditional acceptance probability' in summary['boundary']
