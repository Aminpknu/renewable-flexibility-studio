import json, pandas as pd
from engine.multiservice_forecast import backtest_multiservice_price_forecast
h=pd.read_csv('data/neso_multiservice_forecast_history.csv')
r,s=backtest_multiservice_price_forecast(h)
r.to_csv('outputs/multiservice/stage13_price_forecast_backtest.csv',index=False)
open('outputs/multiservice/stage13_price_forecast_summary.json','w',encoding='utf-8').write(json.dumps(s,indent=2)+'\n')
print(json.dumps({k:s[k] for k in ['days','rows','forecast','naive_previous_same_product_window','mae_improvement_vs_naive_pct']},indent=2))
