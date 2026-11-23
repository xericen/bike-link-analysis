"""Read-only broad-search evidence must preserve purpose and exploration labels."""
import json
import pytest
from backend.research import breadth_presentation as p,recovery_breadth as b,method_validation as m

def test_actual_archived_summary_keeps_spacing_tracks_distinct():
    if not (m.ROOT/"data/individual/seoul/analysis.sqlite").exists():pytest.skip("private source snapshot absent")
    result=p.read("all")
    assert result["available"] and result["exploratory"] and not result["operational_update"]
    assert result["period_start"]=="2025-12-01" and result["evaluation_start"]=="2025-08-01"
    assert result["combination_count"]==46
    expected={"seoul":(1,3),"daejeon":(4,2),"sejong":(0,3)}
    for row in result["cities"]:
        assert row["baseline"]["hits"]==0
        assert (row["strict"]["hits"],row["diagnostic"]["hits"])==expected[row["city"]]
        assert row["strict"]["method"] in b.STRICT
        assert row["diagnostic"]["method"] in b.DIAGNOSTIC
    result["cities"].clear()
    assert len(p.read("seoul")["cities"])==1

def test_reader_never_recomputes_candidates(monkeypatch):
    if not (m.ROOT/"data/individual/seoul/analysis.sqlite").exists():pytest.skip("private source snapshot absent")
    monkeypatch.setattr(b,"fold",lambda *a,**k:(_ for _ in ()).throw(AssertionError("computed")))
    assert p.read("daejeon")["available"]

def test_modified_artifact_is_rejected(tmp_path,monkeypatch):
    (tmp_path/"inputs.json").write_text("{}")
    (tmp_path/"results.json").write_text("{}")
    (tmp_path/"protocol.json").write_text("{}")
    (tmp_path/"audit.json").write_text(json.dumps({"passed":True,"artifacts":{"results.json":"wrong"}}))
    monkeypatch.setattr(b,"OUT",tmp_path)
    p._load.cache_clear()
    assert not p.read("all")["available"]
