"""Information-set boundaries, not merely chronological train/test splits."""
import pandas as pd

def utc(value):
    value=pd.Timestamp(value)
    return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")

def origin(month):
    m=pd.Timestamp(month).to_period("M").start_time
    return utc(m+pd.Timedelta(days=21))

def flow_cutoff(month,lag_days=7):
    if lag_days not in (7,14,28):
        raise ValueError("Core shipping lags are frozen at 7,14,28 days")
    return origin(month)-pd.Timedelta(days=lag_days)

def release_time(month,verified=None,assumed_lag=60):
    if verified is not None and not pd.isna(verified):
        return utc(verified),"verified_first_release"
    # Calendar days after the last date of the month, assumed available EOD.
    end=pd.Timestamp(month).to_period("M").end_time.normalize()
    return utc(end+pd.Timedelta(days=assumed_lag+1)),f"assumed_{assumed_lag}_calendar_days_after_month_end_eod"

def admissible(record,cutoff,mode):
    if mode == "verified_point_in_time":
        when=record.get("verified_available_at_utc")
        return when is not None and not pd.isna(when) and utc(when)<=utc(cutoff)
    if mode == "current_vintage_pseudo_realtime":
        when=record.get("assumed_available_at_utc")
        return when is not None and not pd.isna(when) and utc(when)<=utc(cutoff)
    raise ValueError("Unsupported predictive availability mode")

def require_temporal_split(train_years,validation_years,test_years,random_split=False):
    if random_split or max(train_years)>=min(validation_years) or max(validation_years)>=min(test_years):
        raise ValueError("Random/overlapping core splits are forbidden")
