import copy
import numpy as np
import pandas as pd
import pytest
from scsi.features.asof import origin,flow_cutoff,admissible,require_temporal_split,release_time
from scsi.features.flow import normalized_daily,shipping_features,matched_prior_end
from scsi.research.data import prepare_targets
from scsi.research.models import ForecastEngine
from scsi.research.bootstrap import paired_bootstrap
from scsi.research.claims import classify

def test_day21_exclusive_and_lag():
    assert origin("2024-02-01")==pd.Timestamp("2024-02-22",tz="UTC")
    assert flow_cutoff("2024-02-01",7)==pd.Timestamp("2024-02-15",tz="UTC")
    assert flow_cutoff("2024-02-01",28)==pd.Timestamp("2024-01-25",tz="UTC")

def test_leap_year_calendar_rule():
    assert matched_prior_end("2024-02-29")==pd.Timestamp("2023-02-28")

def test_future_retrieval_never_verified_historical():
    r={"verified_available_at_utc":"2026-10-15","assumed_available_at_utc":"2024-01-08"}
    assert not admissible(r,"2024-02-22","verified_point_in_time")
    assert admissible(r,"2024-02-22","current_vintage_pseudo_realtime")
    assert not admissible({"verified_available_at_utc":None},"2024-02-22","verified_point_in_time")

def test_random_and_overlap_rejected():
    with pytest.raises(ValueError):require_temporal_split([2020,2021],[2023],[2024],True)
    with pytest.raises(ValueError):require_temporal_split([2020,2023],[2023],[2024])

def test_missing_day_not_zero(synthetic_flow):
    x=synthetic_flow[~((synthetic_flow.observation_date==pd.Timestamp("2024-01-09"))&(synthetic_flow.gateway_id=="savannah"))]
    f=shipping_features(normalized_daily(x),"2024-01-01")
    assert not f["valid"]

def test_boundary_day15_not_admissible(synthetic_flow):
    before=shipping_features(normalized_daily(synthetic_flow),"2024-01-01")
    synthetic_flow.loc[synthetic_flow.observation_date>=pd.Timestamp("2024-01-15"),"port_calls"]=1e8
    after=shipping_features(normalized_daily(synthetic_flow),"2024-01-01")
    assert before["features"]==after["features"]

def test_cargo_cannot_substitute_containers(synthetic_flow):
    synthetic_flow["vessel_category"]="cargo"
    with pytest.raises(ValueError,match="container-specific"):normalized_daily(synthetic_flow)

def test_tons_cannot_become_teus(synthetic_targets):
    synthetic_targets["unit"]="tons"
    with pytest.raises(ValueError,match="TEUs"):prepare_targets(synthetic_targets)

def test_total_cannot_become_loaded_import(synthetic_targets):
    synthetic_targets["load_status"]="total"
    with pytest.raises(ValueError,match="loaded imports"):prepare_targets(synthetic_targets)

def test_ambiguous_revision_is_not_doublecounted(synthetic_targets):
    doubled=pd.concat([synthetic_targets,synthetic_targets.iloc[:1]])
    with pytest.raises(ValueError,match="duplicate target revisions"):prepare_targets(doubled)

def test_explicit_revisions_select_latest_not_sum(synthetic_targets):
    synthetic_targets["revision_at_utc"]="2025-01-01"
    newer=synthetic_targets.iloc[:1].copy();newer["revision_at_utc"]="2026-01-01";newer["teu"]=222000
    out,raw=prepare_targets(pd.concat([synthetic_targets,newer]))
    assert len(raw)==len(synthetic_targets)
    assert raw[(raw.month==pd.Timestamp("2019-01-01"))&(raw.official_port_id=="la")].teu.iloc[0]==222000

def test_la_lb_report_scope_required(synthetic_targets):
    with pytest.raises(ValueError,match="reporting scope"):prepare_targets(synthetic_targets[synthetic_targets.official_port_id!="lb"])

def test_future_data_append_does_not_change_forecast(synthetic_flow,synthetic_targets):
    t,_=prepare_targets(synthetic_targets);d=normalized_daily(synthetic_flow)
    before=ForecastEngine(d,t).forecast("2024-01-01","geography_ridge",10.)
    # Current/unreleased outcomes and every later source record are deliberately corrupted.
    synthetic_targets.loc[synthetic_targets.month>=pd.Timestamp("2023-11-01"),"teu"]*=100
    synthetic_flow.loc[synthetic_flow.observation_date>=pd.Timestamp("2024-01-15"),"port_calls"]*=100
    t2,_=prepare_targets(synthetic_targets)
    after=ForecastEngine(normalized_daily(synthetic_flow),t2).forecast("2024-01-01","geography_ridge",10.)
    assert before["prediction_teu"]==after["prediction_teu"]
    assert before["model_parameters"]==after["model_parameters"]
    assert max(before["training_months"])<="2023-10"
    assert "2024-01" not in before["training_months"]

def test_all_models_share_fallback_cutoff(synthetic_flow,synthetic_targets):
    synthetic_flow=synthetic_flow[synthetic_flow.observation_date!=pd.Timestamp("2024-01-09")]
    t,_=prepare_targets(synthetic_targets);e=ForecastEngine(normalized_daily(synthetic_flow),t)
    rows=[e.forecast("2024-01-01",m) for m in ["seasonal_naive","released_target_ridge","aggregate_activity_ridge","geography_ridge","simple_calls_to_teu"]]
    assert all(r["fallback_used"] for r in rows)
    assert len({r["prediction_teu"] for r in rows})==1
    assert len({r["feature_cutoff_utc"] for r in rows})==1

def test_bootstrap_preserves_missing_calendar_markers():
    x=pd.DataFrame({"actual_teu":[100.,100.],"c":[105.,105.],"b":[110.,110.]},index=["2024-01","2024-03"])
    b=paired_bootstrap(x,"c","b",3,100,1)
    assert b["calendar_months"]==3 and b["paired_valid_months"]==2
    assert b["lower"]==.5 and b["upper"]==.5
    assert b["resampled_valid_months_min"]==2

def test_claim_gate_both_intervals_and_comparators():
    good={"comparator":"aggregate_activity_ridge","relative_lift":.1,"n_months":24,"bootstrap":[{"lower":.01},{"lower":.01}]}
    worse={**good,"comparator":"seasonal_naive","relative_lift":-.03}
    assert classify([good,worse])=="PROMISING_BUT_UNCERTAIN"
    uncertain=copy.deepcopy(good);uncertain["bootstrap"][1]["lower"]=-.01
    assert classify([uncertain])=="PROMISING_BUT_UNCERTAIN"
    assert classify([good])=="HISTORICAL_LIFT_SUPPORTED"
    assert classify([{**good,"relative_lift":-.001}])=="NO_INCREMENTAL_LIFT"

def test_release_lag_is_assumed_not_verified():
    when,basis=release_time("2023-11-01",None,60)
    assert when>origin("2024-01-01")
    assert basis.startswith("assumed_")

def test_plural_units_cannot_bypass_target_contract(synthetic_targets):
    synthetic_targets["units"]="tons"
    with pytest.raises(ValueError,match="TEUs"):prepare_targets(synthetic_targets)

def test_growth_denominator_must_be_released(synthetic_targets):
    from scsi.research.data import history_features
    t,_=prepare_targets(synthetic_targets)
    t.loc[pd.Timestamp("2022-10-01"),"available_at"]=pd.Timestamp("2025-01-01",tz="UTC")
    _,latest=history_features(t,origin("2024-01-01"))
    assert latest==pd.Timestamp("2023-09-01")
