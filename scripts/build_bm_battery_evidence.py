from pathlib import Path
from datetime import datetime, timedelta, timezone
import json, requests, pandas as pd, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
ROOT=Path(__file__).resolve().parents[1]; BASE='https://data.elexon.co.uk/bmrs/api/v1'
refs=pd.DataFrame(requests.get(BASE+'/reference/bmunits/all',timeout=30).json())
mask=refs['bmUnitName'].astype(str).str.contains('battery|storage|bess',case=False,regex=True,na=False)
units=refs.loc[mask,'elexonBmUnit'].dropna().astype(str).drop_duplicates().tolist()[:24]
to=datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0); start=to-timedelta(days=6, hours=23)
rows=[]
for unit in units:
    p={'bmUnit':unit,'from':start.isoformat().replace('+00:00','Z'),'to':to.isoformat().replace('+00:00','Z')}
    bod=requests.get(BASE+'/balancing/bid-offer',params=p,timeout=30).json().get('data',[])
    boa=requests.get(BASE+'/balancing/acceptances',params=p,timeout=30).json().get('data',[])
    bdf=pd.DataFrame(bod); adf=pd.DataFrame(boa)
    if bdf.empty: continue
    accepted=set(); up=set(); down=set()
    for _,a in adf.iterrows():
        d=str(a['settlementDate']); lo=int(a['settlementPeriodFrom']); hi=int(a['settlementPeriodTo']); delta=float(a['levelTo'])-float(a['levelFrom'])
        for sp in range(lo,hi+1): accepted.add((d,sp)); (up if delta>0 else down if delta<0 else set()).add((d,sp))
    for (d,sp),g in bdf.groupby(['settlementDate','settlementPeriod']):
        bids=pd.to_numeric(g['bid'],errors='coerce'); offers=pd.to_numeric(g['offer'],errors='coerce')
        rows.append({'bmUnit':unit,'settlementDate':d,'settlementPeriod':int(sp),'pair_count':int(len(g)),'bid_mean':float(bids.mean()),'offer_mean':float(offers.mean()),'spread':float(offers.mean()-bids.mean()),'accepted':int((d,int(sp)) in accepted),'accepted_up':int((d,int(sp)) in up),'accepted_down':int((d,int(sp)) in down)})
df=pd.DataFrame(rows)
if df.empty: raise SystemExit('No battery BOD opportunities returned')
df.to_csv(ROOT/'data'/'bm_battery_opportunities.csv',index=False)
X=df[['settlementPeriod','pair_count','bid_mean','offer_mean','spread']].replace([np.inf,-np.inf],np.nan).fillna(0.0)
y=df['accepted'].to_numpy(int)
summary={'schema_version':'1.0','stage':'release_c_battery_bm_evidence','from':start.isoformat(),'to':to.isoformat(),'battery_bmus_considered':len(units),'battery_bmus_with_bod':int(df.bmUnit.nunique()),'opportunity_periods':int(len(df)),'accepted_periods':int(df.accepted.sum()),'accepted_up_periods':int(df.accepted_up.sum()),'accepted_down_periods':int(df.accepted_down.sum()),'observed_any_acceptance_pct':float(100*df.accepted.mean()),'observed_up_pct':float(100*df.accepted_up.mean()),'observed_down_pct':float(100*df.accepted_down.mean()),'source':'Elexon Insights reference BM Units + BOD + BOALF','identity_rule':'BM Unit name contains battery/storage/BESS; retained explicitly in frozen dataset','claim_boundary':'Observed submitted-BOD settlement periods for a bounded sample of named battery/storage BMUs. This is not a complete GB BESS fleet census and not a causal bid acceptance model.'}
if len(np.unique(y))>1 and len(df)>=100:
    model=LogisticRegression(max_iter=500,class_weight='balanced').fit(X,y); pred=model.predict_proba(X)[:,1]
    summary['model']={'type':'in_sample_logistic_diagnostic','brier_score':float(brier_score_loss(y,pred)),'features':list(X.columns),'intercept':float(model.intercept_[0]),'coefficients':{c:float(v) for c,v in zip(X.columns,model.coef_[0])}}
else: summary['model']={'type':'not_fitted','reason':'insufficient outcome variation/sample'}
(ROOT/'data'/'bm_battery_evidence_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
