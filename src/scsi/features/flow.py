"""Strict complete-window container-call features in fixed gateway order."""
import numpy as np
import pandas as pd
from scsi.config import GATEWAYS
from scsi.features.asof import flow_cutoff

def normalized_daily(frame):
    x=frame.copy()
    needed={"gateway_id","observation_date","port_calls","vessel_category"}
    if not needed.issubset(x.columns):
        raise ValueError(f"Missing flow columns: {needed-set(x.columns)}")
    if not x.vessel_category.astype(str).str.lower().isin(["container","containers","container_ship","container_specific","containership"]).all():
        raise ValueError("Primary predictors require container-specific calls, not cargo/tons")
    x["observation_date"]=pd.to_datetime(x.observation_date,utc=True).dt.tz_localize(None).dt.normalize()
    x["port_calls"]=pd.to_numeric(x.port_calls,errors="raise")
    if (x.port_calls.dropna()<0).any():
        raise ValueError("Negative port calls")
    keys=["gateway_id","observation_date"]
    if "source_port_id" in x:
        if x.duplicated(["source_port_id","observation_date"]).any():
            raise ValueError("Duplicate port/date calls would double count")
        # A missing contributing facility makes the gateway observation missing.
        expected=x.groupby("gateway_id").source_port_id.nunique().to_dict()
        sums=x.groupby(keys).port_calls.sum(min_count=1)
        counts=x.groupby(keys).port_calls.count()
        for g,n in expected.items():
            mask=sums.index.get_level_values(0)==g
            sums.loc[mask]=sums.loc[mask].where(counts.loc[mask]==n)
        x=sums.rename("port_calls").reset_index()
    elif x.duplicated(keys).any():
        raise ValueError("Duplicate gateway/date calls")
    return x.pivot(index="observation_date",columns="gateway_id",values="port_calls").reindex(columns=GATEWAYS).sort_index()

def matched_prior_end(day):
    # pandas DateOffset clamps Feb29 to Feb28, retaining calendar alignment.
    return pd.Timestamp(day)-pd.DateOffset(years=1)

def window_sum(daily,end,days,gateways):
    idx=pd.date_range(pd.Timestamp(end)-pd.Timedelta(days=days-1),pd.Timestamp(end),freq="D")
    w=daily.reindex(idx)[gateways]
    if w.isna().any().any():
        return None
    return w.sum()

def shipping_features(daily,month,lag_days=7,gateways=None):
    gateways=list(gateways or GATEWAYS)
    cutoff=flow_cutoff(month,lag_days)
    end=(cutoff-pd.Timedelta(days=1)).tz_localize(None).normalize()
    values={}; sums={}
    for days in (7,28):
        now=window_sum(daily,end,days,gateways)
        previous=window_sum(daily,matched_prior_end(end),days,gateways)
        if now is None or previous is None:
            return {"valid":False,"reason":"incomplete_current_or_prior_year_window","cutoff":cutoff,"features":{},"recent_calls":None}
        for g in gateways:
            values[f"{g}_{days}d"]=float(np.log((1+now[g])/(1+previous[g])))
        values[f"aggregate_{days}d"]=float(np.log((1+now.sum())/(1+previous.sum())))
        sums[days]=now.to_dict()
    return {"valid":True,"reason":None,"cutoff":cutoff,"features":values,"recent_calls":sums[28]}
