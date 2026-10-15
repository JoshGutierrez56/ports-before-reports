"""Strict target reconstruction; current-vintage revisions are selected, never summed."""
import numpy as np
import pandas as pd
from scsi.config import GATEWAYS
from scsi.features.asof import release_time

def prepare_targets(frame,release_lag=60,gateways=None):
    gateways=list(gateways or GATEWAYS)
    x=frame.copy()
    required={"official_port_id","gateway_id","month","direction","load_status","teu"}
    if not required.issubset(x.columns):
        raise ValueError(f"Missing target fields: {required-set(x.columns)}")
    if not x.direction.astype(str).str.lower().isin(["import","imports","inbound"]).all() or not x.load_status.astype(str).str.lower().isin(["loaded","full"]).all():
        raise ValueError("Official target must be loaded imports, not exports/empties/total")
    for unit_column in ("unit","units"):
        if unit_column in x and not x[unit_column].astype(str).str.lower().isin(["teu","teus"]).all():
            raise ValueError("Only TEUs are permitted as target units")
    x["month"]=pd.to_datetime(x.month).dt.to_period("M").dt.to_timestamp()
    x["teu"]=pd.to_numeric(x.teu,errors="raise")
    if (x.teu.dropna()<0).any():
        raise ValueError("Negative official TEUs")
    keys=["official_port_id","month"]
    if x.duplicated(keys).any():
        if "revision_at_utc" not in x or x.loc[x.duplicated(keys,False),"revision_at_utc"].isna().any():
            raise ValueError("Ambiguous duplicate target revisions; establish vintage selection")
        x["revision_at_utc"]=pd.to_datetime(x.revision_at_utc,utc=True)
        if x.duplicated(keys+["revision_at_utc"]).any():
            raise ValueError("Conflicting same-vintage target duplicate")
        x=x.sort_values("revision_at_utc").drop_duplicates(keys,keep="last")
    if "first_release_at_utc" not in x:
        x["first_release_at_utc"]=None
    x["available_at"]=x.apply(lambda row:release_time(row.month,row.first_release_at_utc,release_lag)[0],axis=1)
    x["availability_basis"]=x.apply(lambda row:release_time(row.month,row.first_release_at_utc,release_lag)[1],axis=1)
    expected={"san_pedro_bay":2,"new_york_new_jersey":1,"savannah":1}
    found=x.groupby("gateway_id").official_port_id.nunique().to_dict()
    for g in gateways:
        if found.get(g)!=expected[g]:
            raise ValueError(f"Official reporting scope for {g} is not established: {found.get(g)} component IDs")
    rows=[]
    months=pd.date_range("2019-01-01","2025-12-01",freq="MS")
    for m in months:
        row={"month":m}; available=[]
        for g in gateways:
            part=x[(x.month==m)&(x.gateway_id==g)]
            complete=len(part)==expected[g] and part.teu.notna().all()
            row[g]=float(part.teu.sum()) if complete else np.nan
            if complete:
                available.append(part.available_at.max())
        row["target_teu"]=sum(row[g] for g in gateways) if all(pd.notna(row[g]) for g in gateways) else np.nan
        row["available_at"]=max(available) if len(available)==len(gateways) else pd.NaT
        rows.append(row)
    return pd.DataFrame(rows).set_index("month"),x

def growths(targets):
    return np.log(targets.target_teu/targets.target_teu.shift(12))

def history_features(targets,at):
    v=growths(targets)
    denominator_released=targets.available_at.shift(12)
    origin_month=pd.Timestamp(at).tz_localize(None).to_period("M").start_time
    mask=targets.available_at.notna() & (targets.available_at<=at) & denominator_released.notna() & (denominator_released<=at) & v.notna() & (targets.index<origin_month)
    h=v.loc[mask]
    if len(h)<3:
        return None,None
    return {"released_growth_latest":float(h.iloc[-1]),"released_growth_mean3":float(h.iloc[-3:].mean())},h.index[-1]
