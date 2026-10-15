"""Causal persistence state engine with bounded between-ping occupancy intervals."""
from __future__ import annotations
import numpy as np
import pandas as pd

def reconstruct(points,stationary_speed=1.0,minimum_minutes=30,gap_minutes=30,cutoff=None):
    p=points.loc[points.eligible_cargo_proxy].copy()
    if cutoff is not None:p=p.loc[p.timestamp<pd.Timestamp(cutoff)]
    p=p.sort_values(["mmsi","timestamp"],kind="mergesort").reset_index(drop=True)
    if p.empty:return p,pd.DataFrame(),pd.DataFrame()
    keys=p.mmsi
    previous_time=p.groupby("mmsi",sort=False).timestamp.shift()
    dt=(p.timestamp-previous_time).dt.total_seconds()/60
    previous_gateway=p.groupby("mmsi",sort=False).gateway_id.shift()
    raw=np.full(len(p),"APPROACH",dtype=object)
    mask=lambda s:s.fillna(False).to_numpy(dtype=bool)
    raw[mask(p.zone.eq("transit") | (p.sog>stationary_speed))]="TRANSIT"
    raw[mask(p.zone.eq("anchorage") & (p.sog<=stationary_speed))]="ANCHORAGE_CANDIDATE"
    raw[mask(p.zone.isin(["container_berth","other_commercial_berth"]) & (p.sog<=stationary_speed))]="BERTH_CANDIDATE"
    raw[mask(p.sog.isna() | ~p.valid_position)]="UNKNOWN_GAP"
    p["raw_state"]=raw
    previous_raw=p.groupby("mmsi",sort=False).raw_state.shift()
    reset=dt.isna() | (dt>gap_minutes) | previous_raw.ne(p.raw_state) | previous_gateway.ne(p.gateway_id)
    p["run_id"]=reset.cumsum().astype("int64")
    p["run_start"]=p.groupby("run_id",sort=False).timestamp.transform("first")
    p["elapsed_minutes"]=(p.timestamp-p.run_start).dt.total_seconds()/60
    stationary=p.raw_state.isin(["ANCHORAGE_CANDIDATE","BERTH_CANDIDATE"])
    p["state"]=p.raw_state.where(~stationary | (p.elapsed_minutes>=minimum_minutes),"PERSISTENCE_PENDING")
    p["gap_before"]=(dt>gap_minutes) | dt.isna() | previous_raw.eq("UNKNOWN_GAP")
    first_flags=p.groupby("run_id",sort=False).gap_before.transform("first")
    p["left_censored"]=first_flags
    p["interval_minutes"]=dt
    p["continuous_interval"]=dt.notna() & dt.le(gap_minutes) & previous_gateway.eq(p.gateway_id)
    # Interval attribution requires BOTH endpoint zones/speeds to agree and a
    # confirmed persistence window by interval start. No future departure needed.
    interval_ok=~reset & stationary & p.valid_position
    starts=pd.concat([previous_time,p.run_start+pd.Timedelta(minutes=minimum_minutes)],axis=1).max(axis=1)
    interval_ok &= starts<p.timestamp
    intervals=p.loc[interval_ok,["mmsi","gateway_id","run_id","raw_state","timestamp","left_censored"]].rename(columns={"timestamp":"end","raw_state":"state"}).copy()
    intervals["start"]=starts.loc[interval_ok]
    intervals["hours"]=(intervals.end-intervals.start).dt.total_seconds()/3600
    intervals["bounded_occupancy_assumption"]=True
    # Episodes are full retrospective QA objects. Daily predictors are calculated
    # independently from prefix-only per-day last observations below.
    episodes=p.groupby("run_id",sort=False).agg(mmsi=("mmsi","first"),gateway_id=("gateway_id","first"),state=("raw_state","first"),start=("timestamp","first"),last_observed=("timestamp","last"),points=("timestamp","size"),left_censored=("left_censored","first"),max_elapsed_minutes=("elapsed_minutes","max"))
    last_indices=p.groupby("run_id",sort=False).tail(1).index
    next_time=p.timestamp.shift(-1).loc[last_indices].to_numpy()
    next_mmsi=p.mmsi.shift(-1).loc[last_indices].to_numpy()
    next_raw=p.raw_state.shift(-1).loc[last_indices].to_numpy()
    next_gap=(p.timestamp.shift(-1)-p.timestamp).dt.total_seconds().div(60).loc[last_indices].to_numpy()
    episodes["right_censored"]=(next_mmsi!=episodes.mmsi.to_numpy()) | (next_gap>gap_minutes) | pd.isna(next_time) | (next_raw=="UNKNOWN_GAP")
    episodes["departure_observed_at"]=pd.to_datetime(next_time,utc=True)
    episodes.loc[episodes.right_censored,"departure_observed_at"]=pd.NaT
    episodes["observed_hours"]=intervals.groupby("run_id").hours.sum().reindex(episodes.index,fill_value=0)
    episodes["confirmed"]=~episodes.state.isin(["ANCHORAGE_CANDIDATE","BERTH_CANDIDATE"]) | episodes.max_elapsed_minutes.ge(minimum_minutes)
    episodes["elapsed_duration_is_lower_bound"]=episodes.left_censored
    return p,intervals,episodes.reset_index()

def split_intervals_by_day(intervals):
    if intervals.empty:return pd.DataFrame(columns=["gateway_id","date","state","hours"])
    # Intervals <=60 min can span at most one UTC midnight.
    x=intervals.copy();x["interval_observed_at"]=x.end; midnight=x.end.dt.floor("D")
    crossing=x.start<midnight
    first=x.loc[crossing].copy();first["end"]=midnight.loc[crossing]
    x.loc[crossing,"start"]=midnight.loc[crossing]
    result=pd.concat([x,first],ignore_index=True)
    result["date"]=result.start.dt.strftime("%Y-%m-%d")
    result["hours"]=(result.end-result.start).dt.total_seconds()/3600
    return result.loc[result.hours>0]
