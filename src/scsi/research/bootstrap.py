"""Paired non-circular moving blocks over a complete calendar, including nulls."""
import numpy as np
import pandas as pd

def paired_bootstrap(frame,candidate,comparator,block_months,replicates=10000,seed=20261015):
    x=frame.copy()
    x.index=pd.PeriodIndex(x.index,freq="M")
    full=pd.period_range(x.index.min(),x.index.max(),freq="M")
    x=x.reindex(full)
    arr=x[["actual_teu",candidate,comparator]].to_numpy(dtype=float)
    n=len(arr)
    if n<block_months:raise ValueError("Calendar history shorter than bootstrap block")
    rng=np.random.default_rng(seed+block_months)
    starts=rng.integers(0,n-block_months+1,size=(replicates,int(np.ceil(n/block_months))))
    indices=(starts[:,:,None]+np.arange(block_months)).reshape(replicates,-1)[:,:n]
    draws=arr[indices]
    valid=np.isfinite(draws).all(axis=2)
    denominator=np.where(valid,draws[:,:,0],0).sum(axis=1)
    c=np.where(valid,abs(draws[:,:,0]-draws[:,:,1]),0).sum(axis=1)
    b=np.where(valid,abs(draws[:,:,0]-draws[:,:,2]),0).sum(axis=1)
    okay=(denominator>0)&(b>0)
    lifts=1-c[okay]/b[okay]
    bounds=np.quantile(lifts,[.025,.975]).tolist() if len(lifts) else [None,None]
    return {"block_months":block_months,"replicates":replicates,"valid_replicates":int(okay.sum()),"lower":bounds[0],"upper":bounds[1],"paired_valid_months":int(np.isfinite(arr).all(axis=1).sum()),"calendar_months":n,"resampled_valid_months_min":int(valid.sum(axis=1).min()),"resampled_valid_months_max":int(valid.sum(axis=1).max()),"method":"paired_non_circular_moving_calendar_month_blocks"}
