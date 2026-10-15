"""Coverage-aware daily summaries; no missing source partition becomes zero."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scsi.geo.episodes import split_intervals_by_day
from scsi.sources.noaa_points import BBOXES

def daily_features(points,intervals,episodes,source_days,start,end,gap_minutes=30):
    p=points.copy();p["date"]=p.timestamp.dt.strftime("%Y-%m-%d")
    split=split_intervals_by_day(intervals)
    if len(split):
        # Past-only daily series excludes pieces established only by a ping at or
        # after that day's exclusive cutoff. Full retrospective splitting remains
        # available in split_intervals_by_day for continuity QA.
        cutoff=pd.to_datetime(split.date,utc=True)+pd.Timedelta(days=1)
        split=split.loc[split.interval_observed_at<cutoff]
    hours=split.groupby(["gateway_id","date","state"]).hours.sum() if len(split) else pd.Series(dtype=float)
    result=[]
    grouped={(g,d):f for (g,d),f in p.groupby(["gateway_id","date"],sort=False)}
    # A persistent inner-zone entry following observed approach/transit is a
    # candidate zone-arrival, not a total port-call census.
    ep=episodes.copy()
    ep["date"]=pd.to_datetime(ep.start,utc=True).dt.strftime("%Y-%m-%d")
    ep_valid=p.loc[p.state.isin(["ANCHORAGE_CANDIDATE","BERTH_CANDIDATE"]) & ~p.left_censored].groupby("run_id",sort=False).head(1)
    arrivals=ep_valid.groupby(["gateway_id","date"]).mmsi.nunique()
    for day in pd.date_range(start,end,tz="UTC"):
        d=day.strftime("%Y-%m-%d");cutoff=day+pd.Timedelta(days=1)
        for gateway in BBOXES:
            q=grouped.get((gateway,d));complete=d in source_days
            row=dict(gateway_id=gateway,date=d,source_complete=complete,observed_arrivals=None,anchorage_hours=None,berth_hours=None,queue_stock=None,median_active_age_hours=None,completed_berth_median_hours=None,censored_episodes=None,censored_fraction=None,eligible_ping_count=0,retained_invalid_observation_count=None,retained_invalid_observation_rate=None,ping_continuity=None,observed_hours_of_day=0,verified_zero_queue=False,quality_flags="missing_source_partition",observation_cutoff_utc=cutoff.isoformat(),availability_basis="retrospective_descriptive")
            if not complete:
                result.append(row);continue
            if q is None or q.empty:
                row["quality_flags"]="complete_source_but_no_eligible_observations;coverage_unknown"
                result.append(row);continue
            usable=q.interval_minutes.notna()
            continuity=float(q.loc[usable,"continuous_interval"].mean()) if usable.any() else None
            usable_signal=q.valid_position & q.sog.notna()
            observed_hours=q.loc[usable_signal,"timestamp"].dt.hour.nunique()
            adequate=observed_hours==24 and continuity is not None and continuity>=0.8
            last=q.groupby("mmsi",sort=False).tail(1)
            active=last.loc[(last.timestamp>=cutoff-pd.Timedelta(minutes=gap_minutes)) & last.state.eq("ANCHORAGE_CANDIDATE")]
            row.update(observed_arrivals=int(arrivals.get((gateway,d),0)),anchorage_hours=float(hours.get((gateway,d,"ANCHORAGE_CANDIDATE"),0)),berth_hours=float(hours.get((gateway,d,"BERTH_CANDIDATE"),0)),eligible_ping_count=len(q),ping_continuity=continuity,observed_hours_of_day=int(observed_hours),quality_flags="coverage_limited_lower_bounds;receiver_uptime_unknown" if adequate else "unreliable_day;coverage_limited_lower_bounds;receiver_uptime_unknown")
            row.update(retained_invalid_observation_count=int((~usable_signal).sum()),retained_invalid_observation_rate=float((~usable_signal).mean()))
            if adequate:
                row.update(queue_stock=len(active),median_active_age_hours=float(active.elapsed_minutes.median()/60) if len(active) else 0.0,verified_zero_queue=not len(active))
            starts=ep.loc[ep.gateway_id.eq(gateway) & ep.date.eq(d) & ep.confirmed & ep.state.isin(["ANCHORAGE_CANDIDATE","BERTH_CANDIDATE"])]
            # Censoring is explicit retrospective QA; never an as-of predictor.
            row["censored_episodes"]=int((starts.left_censored|starts.right_censored).sum())
            row["censored_fraction"]=float((starts.left_censored|starts.right_censored).mean()) if len(starts) else None
            completed=ep.loc[ep.gateway_id.eq(gateway)&ep.state.eq("BERTH_CANDIDATE")&ep.confirmed&~ep.right_censored&~ep.left_censored&(ep.departure_observed_at>=day)&(ep.departure_observed_at<cutoff)]
            if len(completed):row["completed_berth_median_hours"]=float(completed.observed_hours.median())
            result.append(row)
    return pd.DataFrame(result)
