"""One stage per command, explicit receipts, resumable inputs, no remote writes."""
import argparse
from pathlib import Path
import json
import sys
import traceback
from scsi.config import load_config
from scsi.provenance import ledger,write_json,utcnow,resource_check

STAGES={"preflight":"A","audit-sources":"B","acquire-targets":"C","acquire-flow":"C","build-crosswalk":"C","acquire-ais":"D","audit-ais":"D","build-geospatial":"E","build-features":"F","validate-models":"F","lock-protocol":"G","evaluate-locked":"H","run-robustness":"I","build-report":"I","build-site-data":"J","verify-release":"K","shadow-forecast":"L"}

def dispatch(command,root,c,args):
    root=Path(root)
    if command=="preflight":
        checks=resource_check(root,c)
        return {"status":"complete",**checks,"initial_receipt":"artifacts/preflight.json"}
    if command in ("audit-sources","acquire-targets","acquire-flow","build-crosswalk") and (root/"artifacts/protocol_lock.json").exists():
        from scsi.research.pipeline import verify_lock
        verify_lock(root)
        return {"status":"verified_frozen_inputs","command":command,"network_requests":0,"note":"Existing locked sources reused; a new vintage requires an explicitly separate experiment."}
    if command in ("audit-sources","acquire-flow","build-crosswalk"):
        from scsi.sources.portwatch import audit_sources,acquire_flow,build_crosswalk
        return {"audit-sources":audit_sources,"acquire-flow":acquire_flow,"build-crosswalk":build_crosswalk}[command](root)
    if command=="acquire-targets":
        from scsi.sources.official_teu import acquire_targets
        return acquire_targets(root)
    if command=="acquire-ais":
        from scsi.sources.noaa_points import acquire_ais
        return acquire_ais(root,c,pilot=args.pilot)
    if command=="audit-ais":
        frozen=root/"artifacts/audit/geo_pilot_freeze.json"
        if frozen.exists():
            from scsi.provenance import assert_hash
            receipt=json.loads(frozen.read_text(encoding="utf-8"))
            assert_hash(root/"data/geography/geofences_v1.geojson",receipt["geometry_sha256"])
            if c["geospatial"]!=receipt["geospatial"]:raise ValueError("Geospatial settings differ from immutable pilot freeze")
            return {"status":"verified_frozen_pilot","freeze":receipt,"pilot_not_reexecuted":True}
        from scsi.geo.pipeline import build_geospatial,freeze_pilot
        receipt=build_geospatial(root,c,pilot=True)
        return {"measurement":receipt,"freeze":freeze_pilot(root,c)}
    if command=="build-geospatial":
        from scsi.geo.finalize import build_accepted_geospatial
        return build_accepted_geospatial(root,c)
    if command in ("build-features","validate-models","lock-protocol","evaluate-locked","run-robustness"):
        from scsi.research import pipeline
        return getattr(pipeline,command.replace("-","_"))(root,c)
    if command in ("build-report","build-site-data","verify-release","shadow-forecast"):
        from scsi.publishing import exports
        if command=="shadow-forecast":return exports.shadow_forecast(root,c,args.snapshot)
        return getattr(exports,command.replace("-","_"))(root,c)
    raise ValueError(command)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=list(STAGES))
    p.add_argument("--config",default="configs/project.yaml")
    p.add_argument("--pilot",action="store_true")
    p.add_argument("--resume",action="store_true")
    p.add_argument("--snapshot",type=Path)
    a=p.parse_args(argv);c=load_config(a.config);root=Path(c["project"]["workspace_root"])
    stage=STAGES[a.command];started=utcnow()
    ledger(root,stage,"command_started",command=a.command,pilot=a.pilot,resume=a.resume)
    try:
        result=dispatch(a.command,root,c,a)
        receipt={"command":a.command,"started_at_utc":started,"finished_at_utc":utcnow(),"exit_code":0,"result":result}
        write_json(root/f"artifacts/audit/command_{a.command}_{'pilot' if a.pilot else 'core'}.json",receipt)
        ledger(root,stage,"command_finished",command=a.command,exit_code=0)
        print(json.dumps(receipt,default=str,ensure_ascii=False),flush=True)
        return 0
    except Exception as exc:
        receipt={"command":a.command,"started_at_utc":started,"finished_at_utc":utcnow(),"exit_code":1,"error_type":type(exc).__name__,"error":str(exc)}
        write_json(root/f"artifacts/audit/command_{a.command}_FAILED_{started.replace(':','').replace('+','')}.json",receipt)
        ledger(root,stage,"command_failed",**receipt)
        print(json.dumps(receipt),file=sys.stderr);traceback.print_exc()
        return 1

if __name__=="__main__":
    raise SystemExit(main())
