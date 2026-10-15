"""Fixed denominators, all-model comparison and validation-only selection."""
import numpy as np
import pandas as pd
from scsi.config import MODELS
from scsi.research.bootstrap import paired_bootstrap
from scsi.research.models import feature_names

def metrics(records):
    x=pd.DataFrame(records)
    if x.empty:return {}
    paired=x.actual_teu.notna() & x.prediction_teu.notna()
    p=x.loc[paired]
    if p.empty:return {"n_months":0}
    y=p.actual_teu.to_numpy(float);forecast=p.prediction_teu.to_numpy(float)
    e=forecast-y;base=p.seasonal_base_teu.to_numpy(float)
    return {"n_months":len(p),"wape":float(np.abs(e).sum()/y.sum()),"mae":float(np.abs(e).mean()),"rmse":float(np.sqrt(np.mean(e**2))),"bias":float(e.mean()),"direction_accuracy":float(np.mean(np.sign(forecast-base)==np.sign(y-base))),"fallback_rate":float(x.fallback_used.mean()),"source_coverage_rate":float(x.source_features_valid.mean()),"denominator_teu":float(y.sum()),"total_origins":len(x)}

def evaluate_origins(engine,months,alphas,protocol_hash=None,source_ids=None):
    result=[]
    for m in months:
        for model in MODELS:
            r=engine.forecast(m,model,alphas.get(model,10.),protocol_hash,source_ids)
            if r is None:continue
            value=engine.targets.loc[pd.Timestamp(m),"target_teu"]
            r["actual_teu"]=float(value) if pd.notna(value) else None
            result.append(r)
    return result

def select_validation(engine):
    months=pd.date_range("2023-01-01","2023-12-01",freq="MS")
    candidates=[];selected={};chosen_records=[]
    for model in MODELS:
        alphas=[1.,10.,100.] if model.endswith("_ridge") else [0.]
        choices=[]
        for alpha in alphas:
            rows=[]
            for m in months:
                r=engine.forecast(m,model,alpha)
                if r:
                    v=engine.targets.loc[m,"target_teu"]
                    r["actual_teu"]=float(v) if pd.notna(v) else None
                    rows.append(r)
            score=metrics(rows)
            if score.get("n_months",0)<12:
                raise ValueError("Incomplete validation target history; do not silently choose a model")
            choices.append((score["wape"],-alpha,alpha,rows,score))
            candidates.append({"model_id":model,"alpha":alpha,**score})
        best=min(choices,key=lambda z:(z[0],z[1]))
        if model.endswith("_ridge"):selected[model]=best[2]
        chosen_records.extend(best[3])
    baseline_scores=[(metrics([r for r in chosen_records if r["model_id"]==m])["wape"],len(feature_names(m,engine.gateways)),m) for m in MODELS if m!="geography_ridge"]
    benchmark=min(baseline_scores)[2]
    return {"selection_period":"2023-01/2023-12","alphas":selected,"selected_benchmark":benchmark,"grid":candidates,"records":chosen_records,"selection_rule":"min validation WAPE, ties stronger ridge penalty; baseline ties fewer features then name"}

def comparison(records,benchmark,seed=20261015):
    x=pd.DataFrame(records)
    preds=x.pivot(index="target_month",columns="model_id",values="prediction_teu")
    actual=x.drop_duplicates("target_month").set_index("target_month").actual_teu
    preds["actual_teu"]=actual
    if preds.drop(columns="actual_teu").isna().any().any():
        raise ValueError("Every mandatory model must forecast every target origin; shared fallback required")
    if x.groupby("target_month").actual_teu.nunique(dropna=False).max()!=1:
        raise ValueError("Model comparisons disagree on target values")
    result=[]
    for comparator in dict.fromkeys(["aggregate_activity_ridge",benchmark]):
        c=metrics(x[x.model_id=="geography_ridge"].to_dict("records"))
        b=metrics(x[x.model_id==comparator].to_dict("records"))
        result.append({"candidate":"geography_ridge","comparator":comparator,"relative_lift":1-c["wape"]/b["wape"],"candidate_wape":c["wape"],"comparator_wape":b["wape"],"n_months":c["n_months"],"bootstrap":[paired_bootstrap(preds,"geography_ridge",comparator,k,10000,seed) for k in (3,6)]})
    return result
