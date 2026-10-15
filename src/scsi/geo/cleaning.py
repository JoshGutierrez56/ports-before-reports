"""Deterministic UTC cleaning; identifiers never become public exports."""
import numpy as np
import pandas as pd
from pyproj import Geod

def clean_points(raw):
    p=raw.copy()
    p["timestamp"]=pd.to_datetime(p["base_date_time"],utc=True,errors="coerce")
    total=len(p)
    essential=p.timestamp.notna() & p.longitude.between(-180,180) & p.latitude.between(-90,90) & p.mmsi.between(100000000,999999999)
    invalid_essential=int((~essential).sum())
    p=p.loc[essential].copy()
    p["sog"]=pd.to_numeric(p.sog,errors="coerce").where(lambda x:x.between(0,102.2))
    if "cog" in p: p["cog"]=pd.to_numeric(p.cog,errors="coerce").where(lambda x:x.between(0,359.9))
    for col,high in [("length",500),("width",100),("draft",30)]:
        if col in p: p[col]=pd.to_numeric(p[col],errors="coerce").where(lambda x:x.between(0.1,high))
    exact=p.duplicated(["mmsi","timestamp","longitude","latitude","sog"],keep="first")
    duplicate_count=int(exact.sum());p=p.loc[~exact].copy()
    conflicts=p.duplicated(["mmsi","timestamp"],keep=False)
    conflicts_count=int(conflicts.sum());p=p.loc[~conflicts].copy()
    p=p.sort_values(["mmsi","timestamp"],kind="mergesort").reset_index(drop=True)
    previous=p.groupby("mmsi",sort=False)[["longitude","latitude","timestamp"]].shift()
    _,_,distance=Geod(ellps="WGS84").inv(previous.longitude.to_numpy(),previous.latitude.to_numpy(),p.longitude.to_numpy(),p.latitude.to_numpy())
    hours=(p.timestamp-previous.timestamp).dt.total_seconds().to_numpy()/3600
    implied=np.divide(distance/1852,hours,out=np.zeros(len(p)),where=hours>0)
    jump=implied>60
    p["jump_flag"]=jump
    p["eligible_cargo_proxy"]=p.vessel_type.between(70,79)
    p["classification"] = np.where(p.eligible_cargo_proxy,"cargo-vessel proxy",np.where(p.vessel_type.isna() | (p.vessel_type==0),"unknown","other vessel"))
    # Do not join over rejected points: jump endpoints remain as UNKNOWN markers.
    p["valid_position"]=~jump
    return p,dict(raw_rows=total,valid_rows=len(p),invalid_essential=invalid_essential,duplicate_rows=duplicate_count,conflict_rows=conflicts_count,impossible_jump_rows=int(jump.sum()),unknown_speed_rows=int(p.sog.isna().sum()))
