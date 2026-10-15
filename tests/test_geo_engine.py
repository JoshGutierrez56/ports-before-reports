import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point,box,mapping
from scsi.geo.cleaning import clean_points
from scsi.geo.episodes import reconstruct,split_intervals_by_day
from scsi.geo.coverage import daily_features
from scsi.geo.geofences import meter_buffer,classify_zones
from scsi.features.friction import add_friction

def fixture(times,zone="anchorage",speeds=0.1):
    n=len(times)
    return pd.DataFrame(dict(mmsi=[123456789]*n,timestamp=pd.to_datetime(times,utc=True),gateway_id=["san_pedro_bay"]*n,longitude=[-118.2]*n,latitude=[33.7]*n,zone=[zone]*n,sog=np.full(n,speeds),valid_position=True,eligible_cargo_proxy=True))

def times(start,periods,freq="10min"):
    return pd.date_range(start,periods=periods,freq=freq,tz="UTC")

def test_transit_through_anchorage_not_waiting():
    p,i,e=reconstruct(fixture(times("2024-01-01",12),speeds=8))
    assert (p.state=="TRANSIT").all() and i.empty

def test_candidate_requires_past_persistence():
    p,i,e=reconstruct(fixture(times("2024-01-01",7)))
    assert list(p.state[:3])==["PERSISTENCE_PENDING"]*3
    assert abs(i.hours.sum()-.5)<1e-9

def test_boundary_jitter_never_repeated_confirmed_arrival():
    q=fixture(times("2024-01-01",30));q.loc[q.index%2==0,"zone"]="approach"
    p,i,e=reconstruct(q)
    assert not p.state.eq("ANCHORAGE_CANDIDATE").any()

def test_cross_midnight_split_conserves_duration():
    p,i,e=reconstruct(fixture(times("2024-01-01 23:20",5,"20min")))
    split=split_intervals_by_day(i);byday=split.groupby("date").hours.sum()
    assert np.isclose(byday["2024-01-01"],10/60)
    assert np.isclose(byday["2024-01-02"],40/60)
    assert np.isclose(split.hours.sum(),i.hours.sum())

def test_unknown_gap_not_extended_dwell():
    q=fixture(["2024-01-01 00:00","2024-01-01 00:30","2024-01-01 04:00","2024-01-01 04:30"])
    p,i,e=reconstruct(q)
    assert i.empty and e.left_censored.all() and e.right_censored.all()

def test_invalid_position_marker_censors_next_episode():
    q=fixture(times("2024-01-01",9));q.loc[1,"valid_position"]=False
    p,i,e=reconstruct(q)
    candidate=e.loc[e.state.eq("ANCHORAGE_CANDIDATE") & e.confirmed]
    assert len(candidate)==1 and candidate.left_censored.all()

def test_unfinished_prefix_no_future_departure():
    q=fixture(times("2024-01-01",10));q.loc[8:,"zone"]="transit"
    p,i,e=reconstruct(q,cutoff="2024-01-01 01:10Z")
    assert e.right_censored.all() and e.departure_observed_at.isna().all()
    assert p.elapsed_minutes.max()==60

def test_degree_buffer_rejected():
    with pytest.raises(ValueError,match="projected"):meter_buffer(Point(-118,34),100,"EPSG:4326")
    assert meter_buffer(Point(-118,34),100,"EPSG:32611").area<.00001

def test_shared_anchorage_single_assignment():
    q=fixture(times("2024-01-01",7))
    f=dict(type="Feature",geometry=mapping(box(-118.3,33.6,-118.1,33.8)),properties=dict(gateway_id="san_pedro_bay",zone="anchorage"))
    q["zone"]=classify_zones(q,{"features":[f,f]})
    p,i,e=reconstruct(q)
    assert np.isclose(i.hours.sum(),.5)

def test_channel_overrides_overlapping_anchorage():
    q=fixture(times("2024-01-01",7))
    f=dict(type="Feature",geometry=mapping(box(-118.3,33.6,-118.1,33.8)),properties=dict(gateway_id="san_pedro_bay",zone="anchorage"))
    t={**f,"properties":dict(gateway_id="san_pedro_bay",zone="transit")}
    assert all(classify_zones(q,{"features":[f,t]})=="transit")

def test_clean_duplicate_conflict_and_proxy_label():
    q=fixture(times("2024-01-01",3));q["base_date_time"]=q.timestamp;q["vessel_type"]=70
    q=pd.concat([q,q.iloc[[0]],q.iloc[[1]].assign(longitude=-120)])
    p,r=clean_points(q)
    assert r["duplicate_rows"]==1 and r["conflict_rows"]==2
    assert set(p.classification)=={"cargo-vessel proxy"}

def test_invalid_speed_sentinel_unknown_not_stationary():
    q=fixture(times("2024-01-01",3));q["base_date_time"]=q.timestamp;q["vessel_type"]=70;q["sog"]=102.3
    p,r=clean_points(q);p["zone"]="anchorage";p,i,e=reconstruct(p)
    assert p.state.eq("UNKNOWN_GAP").all()

def test_impossible_jump_kept_as_unknown_marker():
    q=fixture(times("2024-01-01",4));q["base_date_time"]=q.timestamp;q["vessel_type"]=70;q.loc[2,"longitude"]=-80
    p,r=clean_points(q)
    assert r["impossible_jump_rows"]>=1 and (~p.valid_position).any()

def test_missing_day_never_zero():
    p,i,e=reconstruct(fixture(times("2024-01-01",10)))
    d=daily_features(p,i,e,{"2024-01-01"},"2024-01-01","2024-01-02")
    row=d.loc[(d.date=="2024-01-02")&(d.gateway_id=="san_pedro_bay")].iloc[0]
    assert pd.isna(row.anchorage_hours) and pd.isna(row.queue_stock)

def test_sparse_day_queue_not_zero():
    p,i,e=reconstruct(fixture(times("2024-01-01",10)))
    d=daily_features(p,i,e,{"2024-01-01"},"2024-01-01","2024-01-01")
    assert pd.isna(d.iloc[0].queue_stock) and not d.iloc[0].verified_zero_queue

def test_unknown_signals_throughout_day_do_not_prove_zero_queue():
    q=fixture(times("2024-01-01",144,"10min"));q["sog"]=np.nan
    p,i,e=reconstruct(q)
    d=daily_features(p,i,e,{"2024-01-01"},"2024-01-01","2024-01-01")
    assert pd.isna(d.iloc[0].queue_stock) and not d.iloc[0].verified_zero_queue
    assert d.iloc[0].observed_hours_of_day==0 and d.iloc[0].retained_invalid_observation_rate==1

def test_future_append_does_not_change_asof_core_features():
    q=fixture(times("2024-01-01",300));q.loc[q.timestamp>=pd.Timestamp("2024-01-02",tz="UTC"),"zone"]="transit"
    p,i,e=reconstruct(q);a=daily_features(p,i,e,{"2024-01-01","2024-01-02"},"2024-01-01","2024-01-01")
    p,i,e=reconstruct(q,cutoff="2024-01-02T00:00:00Z");b=daily_features(p,i,e,{"2024-01-01"},"2024-01-01","2024-01-01")
    columns=["observed_arrivals","anchorage_hours","berth_hours","queue_stock","median_active_age_hours"]
    pd.testing.assert_frame_equal(a[columns],b[columns])

def test_future_midnight_bridge_cannot_fill_prior_asof_hours():
    q=fixture(times("2024-01-01 20:00",40,"10min"))
    p,i,e=reconstruct(q);a=daily_features(p,i,e,{"2024-01-01","2024-01-02"},"2024-01-01","2024-01-01")
    p,i,e=reconstruct(q,cutoff="2024-01-02T00:00:00Z");b=daily_features(p,i,e,{"2024-01-01"},"2024-01-01","2024-01-01")
    assert a.anchorage_hours.fillna(-1).tolist()==b.anchorage_hours.fillna(-1).tolist()

def test_friction_past_only_and_zero_mad_fallback():
    d=pd.DataFrame(dict(gateway_id="savannah",date=pd.date_range("2024-01-01",periods=40),anchorage_hours=np.ones(40),median_active_age_hours=np.ones(40)))
    a=add_friction(d);d.loc[39,"anchorage_hours"]=10000;b=add_friction(d)
    pd.testing.assert_series_equal(a.friction_index[:39],b.friction_index[:39])
    assert a.friction_index[:30].isna().all() and a.friction_scale_fallback.iloc[30]

def test_friction_uses_previous_valid_days_not_calendar_window():
    # Thirty admissible observations span150calendar days; all remain available.
    d=pd.DataFrame(dict(gateway_id="savannah",date=pd.date_range("2024-01-01",periods=151),anchorage_hours=np.nan,median_active_age_hours=np.nan))
    d.loc[d.index%5==0,["anchorage_hours","median_active_age_hours"]]=1.
    result=add_friction(d,window=90,minimum=30)
    assert pd.notna(result.friction_index.iloc[150])
    assert result.friction_index.iloc[:150].isna().all()

def test_frozen_pilot_resume_does_not_overwrite_reviewed_audit(tmp_path):
    import json
    from scsi.sources.noaa_points import digest
    from scsi.geo.pipeline import build_geospatial,should_run_audit
    audit=tmp_path/"artifacts/audit";audit.mkdir(parents=True)
    geography=tmp_path/"data/geography";geography.mkdir(parents=True)
    geometry=geography/"geofences_v1.geojson";geometry.write_text('{"features":[]}')
    config={"geospatial":{"stationary_speed_knots":1.0}}
    frozen={"geometry_sha256":digest(geometry),"geospatial":config["geospatial"],"measurement_receipt":{"source_days":14,"audit_rows":60}}
    (audit/"geo_pilot_freeze.json").write_text(json.dumps(frozen))
    reviewed=audit/"geo_trajectory_audit.csv";reviewed.write_text('audit_id,review_status\nGEO-001,agent_visual_reviewed\n')
    before=reviewed.read_bytes()
    assert not should_run_audit(tmp_path) and should_run_audit(tmp_path,True)
    assert build_geospatial(tmp_path,config,pilot=True)["source_days"]==14
    assert reviewed.read_bytes()==before

def test_frozen_geometry_change_refused(tmp_path):
    import json
    from scsi.geo.pipeline import build_geospatial
    audit=tmp_path/"artifacts/audit";audit.mkdir(parents=True)
    geography=tmp_path/"data/geography";geography.mkdir(parents=True)
    (geography/"geofences_v1.geojson").write_text('{}')
    (audit/"geo_pilot_freeze.json").write_text(json.dumps({"geometry_sha256":"wrong","geospatial":{}}))
    with pytest.raises(RuntimeError,match="Frozen"):build_geospatial(tmp_path,{"geospatial":{}},pilot=True)

def test_postfreeze_preservation_is_immutable_on_retry(tmp_path):
    from scsi.geo.finalize import _preserve
    audit=tmp_path/"artifacts/audit";audit.mkdir(parents=True)
    original=audit/"geo_daily_features.csv";original.write_text("gateway_id,date,queue_stock\nsavannah,2024-01-01,0\n")
    first=_preserve(tmp_path)
    original.write_text("corrected output")
    assert _preserve(tmp_path)==first
    preserved=tmp_path/first["artifacts"][0]["preserved_path"]
    assert "savannah" in preserved.read_text()
    preserved.write_text("tampered evidence")
    with pytest.raises(ValueError,match="Preserved pre-correction artifact changed"):_preserve(tmp_path)

def test_premature_finalization_marks_failure_without_replacing_pilot(tmp_path):
    import json
    from scsi.geo.finalize import finalize_measurement
    audit=tmp_path/"artifacts/audit";audit.mkdir(parents=True)
    receipt=audit/"geo_measurement_receipt.json";receipt.write_text(json.dumps({"status":"pilot_measured","source_days":14}))
    daily=audit/"geo_daily_features.csv";daily.write_text("pilot evidence")
    before=receipt.read_bytes()
    with pytest.raises(ValueError,match="Initial full-year measurement"):finalize_measurement(tmp_path,{})
    assert receipt.read_bytes()==before and daily.read_text()=="pilot evidence"
    assert json.loads((audit/"geo_finalization_state.json").read_text())["status"]=="failed"
    assert not (audit/"geo_pre_censor_correction").exists()

def test_archive_budget_checked_before_copy(tmp_path):
    from scsi.geo.finalize import _preserve
    audit=tmp_path/"artifacts/audit";audit.mkdir(parents=True)
    (audit/"geo_daily_features.csv").write_text("observed data")
    with pytest.raises(RuntimeError,match="project cap"):_preserve(tmp_path,{"resources":{"minimum_free_disk_gib":0,"project_disk_cap_gib":0}})
    assert not (audit/"geo_pre_censor_correction/geo_daily_features.csv").exists()

def test_correction_gate_accepts_only_documented_coverage_nullification():
    from scsi.geo.finalize import _correction_checks
    before=pd.DataFrame(dict(gateway_id=["savannah"],date=["2024-01-01"],anchorage_hours=[0.],berth_hours=[1.],queue_stock=[0.],median_active_age_hours=[0.],observed_hours_of_day=[24],source_complete=[True],observed_arrivals=[1],friction_index=[np.nan])).set_index(["gateway_id","date"])
    after=before.copy();after[["queue_stock","median_active_age_hours"]]=np.nan;after["observed_hours_of_day"]=23;after["retained_invalid_observation_count"]=1
    config={"geospatial":{"trailing_standardization_days":90,"minimum_standardization_days":30}}
    nullified,comparison=_correction_checks(before,after,config)
    assert len(nullified)==1 and len(comparison)==1
    after["observed_hours_of_day"]=24
    with pytest.raises(ValueError,match="Undocumented correction impact"):_correction_checks(before,after,config)

def test_correction_gate_rejects_undocumented_friction_change():
    from scsi.geo.finalize import _correction_checks,_legacy_calendar_friction
    before=pd.DataFrame(dict(gateway_id="savannah",date=pd.date_range("2024-01-01",periods=35),anchorage_hours=1.,berth_hours=1.,queue_stock=0.,median_active_age_hours=0.,observed_hours_of_day=24,source_complete=True,observed_arrivals=1,retained_invalid_observation_count=0))
    before["friction_index"]=_legacy_calendar_friction(before,90,30)
    before=before.set_index(["gateway_id","date"]);after=before.copy();after.loc[after.index[-1],"friction_index"]=99.
    with pytest.raises(ValueError,match="Corrected friction differs"):_correction_checks(before,after,{"geospatial":{"trailing_standardization_days":90,"minimum_standardization_days":30}})
