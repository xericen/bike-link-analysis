"""Readiness rejects incomplete/stale deployments and never computes on reads."""
import sqlite3
import pytest
from fastapi import HTTPException
from backend.services import precomputed, deployment

def test_complete_periods_only_and_no_runtime_fallback(monkeypatch,tmp_path):
    monkeypatch.setattr(precomputed,"PROCESSED",tmp_path)
    monkeypatch.setattr(precomputed,"revision",lambda *a:"current")
    assert deployment.available_periods("seoul")==[]
    assert not precomputed.path().exists()
    for action in precomputed.ACTIONS[:-1]:
        precomputed.put(action,"seoul","2026-10-01","2026-10-31",{},expected_revision="current")
    assert deployment.available_periods("seoul")==[]
    with pytest.raises(HTTPException):
        deployment.verify([("seoul","2026-10-01","2026-10-31")])
    precomputed.put(precomputed.ACTIONS[-1],"seoul","2026-10-01","2026-10-31",{},expected_revision="current")
    assert deployment.available_periods("seoul")==[{"start":"2026-10-01","end":"2026-10-31"}]
    assert deployment.verify([("seoul","2026-10-01","2026-10-31")])==len(precomputed.ACTIONS)
    monkeypatch.setattr(precomputed,"revision",lambda *a:"changed-after-copy")
    assert deployment.available_periods("seoul")==[]
