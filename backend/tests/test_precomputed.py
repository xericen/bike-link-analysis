"""Deployment lookup must never fall back to runtime analysis."""
import sqlite3
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.services import precomputed,periods,real_data
from backend.main import app

def test_exact_period_revision_and_readonly_cache(tmp_path):
    value={"counts":{"persistent_imbalance":207},"types":{"persistent_imbalance":[{"station_id":"ST-753"}]}}
    precomputed.put("research","seoul","2026-10-01","2026-10-31",value,tmp_path,"revision1")
    got=precomputed.read("research","seoul","2026-10-01","2026-10-31",tmp_path,"revision1")
    assert got["counts"]==value["counts"] and got["precomputed"]["read_only"]
    for start,version in [("2026-10-02","revision1"),("2026-10-01","revision2")]:
        with pytest.raises(HTTPException) as error:
            precomputed.read("research","seoul",start,"2026-10-31",tmp_path,version)
        assert error.value.status_code==409
    assert sqlite3.connect(precomputed.path(tmp_path)).execute("SELECT COUNT(*) FROM kpi").fetchone()[0]==1

def test_empty_store_never_created_by_reader(tmp_path):
    with pytest.raises(HTTPException) as error:
        precomputed.read("research","daejeon","2026-10-01","2026-10-31",tmp_path)
    assert error.value.status_code==409
    assert not precomputed.path(tmp_path).exists()

def test_api_uses_stored_values_without_analysis(monkeypatch,tmp_path):
    monkeypatch.setattr(precomputed,"PROCESSED",tmp_path)
    monkeypatch.setattr(periods,"resolve",lambda *a:("2026-10-01","2026-10-31"))
    precomputed.put("research","daejeon","2026-10-01","2026-10-31",{"counts":{"persistent_imbalance":2}})
    def forbidden(*a,**kw):raise AssertionError("Runtime recomputation")
    monkeypatch.setattr(real_data,"role_candidates",forbidden)
    client=TestClient(app)
    result=client.get("/api/precomputed/daejeon/research")
    assert result.status_code==200 and result.json()["counts"]["persistent_imbalance"]==2
    assert client.get("/api/precomputed/daejeon/network").status_code==409

def test_changed_data_invalidates_revision(tmp_path):
    p=tmp_path/"stations.csv";p.write_text("a")
    old=precomputed.revision(tmp_path)
    p.write_text("changed")
    assert old!=precomputed.revision(tmp_path)
