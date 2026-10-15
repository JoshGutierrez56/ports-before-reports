"""Expanding monthly fits with immutable features and origin-specific label access."""
import calendar
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from scsi.config import GATEWAYS, canonical_hash
from scsi.features.asof import origin
from scsi.features.flow import shipping_features,window_sum
from scsi.research.data import growths,history_features

def feature_names(model,gateways):
    history=["released_growth_latest","released_growth_mean3"]
    if model=="released_target_ridge":return history
    if model=="aggregate_activity_ridge":return history+["aggregate_7d","aggregate_28d"]
    if model=="geography_ridge":return history+[f"{g}_{d}d" for d in (7,28) for g in gateways]
    return []

class ForecastEngine:
    def __init__(self,daily,targets,flow_lag=7,gateways=None,minimum_training=24):
        self.daily=daily;self.targets=targets;self.flow_lag=flow_lag
        self.gateways=list(gateways or GATEWAYS);self.minimum_training=minimum_training
        self.growth=growths(targets);self.context={}
        for m in targets.index:
            if m.year<2020:continue
            shipping=shipping_features(daily,m,flow_lag,self.gateways)
            history,latest=history_features(targets,origin(m))
            self.context[m]={**shipping,"latest_training_target":latest,"values":{**shipping["features"],**(history or {})},"valid":shipping["valid"] and history is not None}

    def forecast(self,month,model,alpha=10.,protocol_hash=None,source_ids=None):
        month=pd.Timestamp(month).to_period("M").start_time
        at=origin(month);ctx=self.context[month]
        base_month=month-pd.DateOffset(years=1)
        if base_month not in self.targets.index or pd.isna(self.targets.loc[base_month,"target_teu"]) or self.targets.loc[base_month,"available_at"]>at:
            return None
        base=float(self.targets.loc[base_month,"target_teu"])
        train=[m for m,c in self.context.items() if m<month and m.year>=2020 and c["valid"] and pd.notna(self.growth.loc[m]) and pd.notna(self.targets.loc[m,"available_at"]) and self.targets.loc[m,"available_at"]<=at and pd.notna(self.targets.loc[m-pd.DateOffset(years=1),"available_at"]) and self.targets.loc[m-pd.DateOffset(years=1),"available_at"]<=at]
        fallback=not ctx["valid"] or len(train)<self.minimum_training
        reason=None if not fallback else (ctx.get("reason") or "insufficient_released_training_history")
        names=feature_names(model,self.gateways)
        params={"alpha":float(alpha)} if names else {}
        prediction=base
        if not fallback and model.endswith("_ridge"):
            X=np.asarray([[self.context[m]["values"][k] for k in names] for m in train],dtype=float)
            y=self.growth.loc[train].to_numpy(dtype=float)
            v=np.asarray([[ctx["values"][k] for k in names]],dtype=float)
            if not np.isfinite(X).all() or not np.isfinite(v).all():
                raise ValueError("Missing/nonfinite feature values reached the model")
            pipeline=make_pipeline(StandardScaler(),Ridge(alpha=alpha))
            with threadpool_limits(limits=1):
                pipeline.fit(X,y)
                predicted_growth=float(pipeline.predict(v)[0])
            prediction=float(base*np.exp(predicted_growth))
            if not np.isfinite(prediction):raise ValueError("Nonfinite forecast; no outcome-tuned clipping permitted")
            params.update({"feature_names":names,"coefficients":pipeline[-1].coef_.tolist(),"intercept":float(pipeline[-1].intercept_),"training_mean":pipeline[0].mean_.tolist(),"training_scale":pipeline[0].scale_.tolist()})
        elif not fallback and model=="simple_calls_to_teu":
            ratios={g:[] for g in self.gateways}
            for m in train:
                days=calendar.monthrange(m.year,m.month)[1]
                sums=window_sum(self.daily,m+pd.offsets.MonthEnd(0),days,self.gateways)
                if sums is None:continue
                for g in self.gateways:
                    if sums[g]>0 and pd.notna(self.targets.loc[m,g]):
                        ratios[g].append(float(self.targets.loc[m,g]/sums[g]))
            if any(not r for r in ratios.values()):
                fallback=True;reason="no_admissible_complete_month_conversion_ratio"
            else:
                med={g:float(np.median(r)) for g,r in ratios.items()}
                days=calendar.monthrange(month.year,month.month)[1]
                prediction=sum(med[g]*ctx["recent_calls"][g]/28*days for g in self.gateways)
                params={"median_teu_per_call":med,"ratio_training_month_counts":{g:len(r) for g,r in ratios.items()},"projected_month_days":days}
        elif model!="seasonal_naive" and not fallback:
            raise ValueError(f"Unknown model: {model}")
        return {"model_id":model,"target_month":month.strftime("%Y-%m"),"forecast_origin_utc":at.isoformat(),"feature_cutoff_utc":ctx["cutoff"].isoformat(),"training_label_cutoff":at.isoformat(),"train_end":max(train).strftime("%Y-%m") if train else None,"training_months":[m.strftime("%Y-%m") for m in train],"latest_training_target":ctx["latest_training_target"].strftime("%Y-%m") if ctx["latest_training_target"] is not None else None,"feature_snapshot_ids":source_ids or [],"protocol_sha256":protocol_hash,"feature_values":{k:float(ctx["values"][k]) for k in names} if ctx["valid"] else {},"feature_hash":canonical_hash(ctx["values"]) if ctx["valid"] else None,"model_parameters":params,"prediction_teu":float(prediction),"interval_lower":None,"interval_upper":None,"fallback_used":bool(fallback),"fallback_reason":reason,"source_features_valid":bool(ctx["valid"]),"flow_lag_days":self.flow_lag,"seasonal_base_teu":base,"available_training_months":len(train)}
