from pathlib import Path
import json
import pytest
from scsi.research.pipeline import verify_lock
from scsi.provenance import write_json,sha256,assert_hash
from scsi.research.evaluation import comparison

def test_evaluation_cannot_start_without_lock(tmp_path):
    with pytest.raises(RuntimeError,match="requires a valid protocol lock"):verify_lock(tmp_path)

def test_hash_mismatch_is_fatal(tmp_path):
    p=tmp_path/"source";p.write_bytes(b"original");h=sha256(p);p.write_bytes(b"changed")
    with pytest.raises(ValueError,match="hash mismatch"):assert_hash(p,h)

def test_immutable_artifact_cannot_be_overwritten(tmp_path):
    p=tmp_path/"result.json";write_json(p,{"x":1},immutable=True)
    with pytest.raises(RuntimeError,match="Immutable"):write_json(p,{"x":2},immutable=True)
    assert json.loads(p.read_text())=={"x":1}

def test_comparisons_refuse_inconsistent_pair_masks():
    rows=[{"target_month":"2024-01","model_id":"geography_ridge","prediction_teu":90.,"actual_teu":100.},
          {"target_month":"2024-01","model_id":"aggregate_activity_ridge","prediction_teu":None,"actual_teu":100.}]
    with pytest.raises(ValueError,match="Every mandatory model"):comparison(rows,"aggregate_activity_ridge")
