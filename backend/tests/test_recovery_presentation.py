"""Read-only UI evidence: strict file provenance, independent periods and city filtering."""
import json
from pathlib import Path
import pytest
from backend.research import recovery_presentation as p, method_validation as m

def fixture_report(tmp_path,monkeypatch):
    source=json.loads((p.DIRECTORY/"results.json").read_text())
    (tmp_path/"results.json").write_text(json.dumps(source))
    (tmp_path/"audit.json").write_text(json.dumps({"passed":True,"matching_metric_checks":288}))
    (tmp_path/"inputs.json").write_text("{}")
    (tmp_path/"presentation-manifest.json").write_text(json.dumps({n:m.sha(tmp_path/n) for n in ("results.json","audit.json","inputs.json")}))
    monkeypatch.setattr(p,"DIRECTORY",tmp_path)
    p._summary.cache_clear()
    return source

def test_city_filter_preserves_december_and_separate_experiment(tmp_path,monkeypatch):
    fixture_report(tmp_path,monkeypatch)
    result=p.read("seoul")
    assert result["available"] and len(result["cities"])==1
    assert result["service_period_start"]=="2025-12-01"
    assert result["evaluation_period_start"]=="2025-07-01"
    assert result["cities"][0]["comparison"]["baseline_hits"]==3
    assert result["cities"][0]["comparison"]["selected_hits"]==2
    assert result["cities"][0]["original"]["hits10"]==0
    assert result["checked_conditions"]==144
    result["cities"].clear()
    assert len(p.read("seoul")["cities"])==1

def test_missing_or_modified_report_is_not_filled_with_previous_city(tmp_path,monkeypatch):
    fixture_report(tmp_path,monkeypatch)
    assert p.read("all")["available"]
    (tmp_path/"results.json").write_text("{}")
    assert not p.read("all")["available"]
    assert not p.read("busan")["available"]

def test_source_metadata_change_blocks_extra_experiment_only(tmp_path,monkeypatch):
    fixture_report(tmp_path,monkeypatch)
    source=tmp_path/"source.csv";source.write_text("original")
    manifest={str(source):{"size":1,"mtime_ns":1,"sha256":"wrong"}}
    (tmp_path/"inputs.json").write_text(json.dumps(manifest))
    checksums={n:m.sha(tmp_path/n) for n in ("results.json","audit.json","inputs.json")}
    (tmp_path/"presentation-manifest.json").write_text(json.dumps(checksums))
    assert not p.read("all")["available"]

def test_reader_never_computes_candidates_or_queries_database(tmp_path,monkeypatch):
    fixture_report(tmp_path,monkeypatch)
    monkeypatch.setattr(m,"grid_candidates",lambda *a,**k:pytest.fail("request-time recomputation"))
    monkeypatch.setattr(m,"load_city",lambda *a,**k:pytest.fail("request-time source query"))
    assert p.read("all")["available"]
