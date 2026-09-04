from engine.portfolio_benchmarking import benchmark_asset_portfolio

def test_portfolio_aggregation_and_reference_scaling():
    store={'assets':{'a':{'asset_name':'A','location_label':'X','power_mw':25,'duration_hours':4,'state_of_health_fraction':.9,'grid_import_limit_mw':20,'grid_export_limit_mw':25},'b':{'asset_name':'B','location_label':'Y','power_mw':10,'duration_hours':2,'state_of_health_fraction':1,'grid_import_limit_mw':10,'grid_export_limit_mw':8}}}
    frame,summary=benchmark_asset_portfolio(store,2_000_000,25)
    assert summary['asset_count']==2
    assert summary['total_power_mw']==35
    assert summary['available_energy_mwh']==110
    assert summary['connection_limited_power_mw']==28
    assert summary['reference_scaled_value_gbp_per_year']==2_240_000
    assert list(frame['asset_name'])==['A','B']

def test_empty_portfolio_is_safe():
    frame,summary=benchmark_asset_portfolio(None,1_000_000)
    assert frame.empty and summary['asset_count']==0
