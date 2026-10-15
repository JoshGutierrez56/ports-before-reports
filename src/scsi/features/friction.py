"""Past-only optional friction summary; unrelated to frozen H1 forecasting."""
import numpy as np
import pandas as pd

def add_friction(daily,window=90,minimum=30):
    result=daily.copy();result["friction_index"]=np.nan;result["friction_scale_fallback"]=False
    for gateway,group in result.groupby("gateway_id",sort=False):
        order=group.sort_values("date").index
        for position,idx in enumerate(order):
            current=result.loc[idx]
            history=result.loc[order[:position]]
            history=history.dropna(subset=["anchorage_hours","median_active_age_hours"]).tail(window)
            if len(history)<minimum or pd.isna(current.median_active_age_hours) or pd.isna(current.anchorage_hours):continue
            zs=[];fallback=False
            for column in ["anchorage_hours","median_active_age_hours"]:
                x=np.log1p(history[column].to_numpy(dtype=float));median=np.median(x);scale=1.4826*np.median(abs(x-median))
                if scale==0:
                    scale=float(np.std(x));fallback=True
                if scale==0:scale=1.0
                zs.append((np.log1p(float(current[column]))-median)/scale)
            result.loc[idx,"friction_index"]=np.mean(zs);result.loc[idx,"friction_scale_fallback"]=fallback
    return result
