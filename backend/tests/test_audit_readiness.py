from backend.services import deployment, decision_evidence

def test_readiness_includes_current_evidence(monkeypatch):
    monkeypatch.setattr(deployment.precomputed, "read", lambda *a: {})
    monkeypatch.setattr(deployment.precomputed, "revision", lambda: "v")
    from backend.services import periods
    monkeypatch.setattr(periods, "resolve", lambda *a: ("2025-12-01", "2025-12-31"))
    monkeypatch.setattr(decision_evidence, "read", lambda *a: {"matches_selected_period": True})
    assert deployment.readiness()["ready"]
    def stale(*a):
        raise deployment.precomputed.HTTPException(409, "stale evidence")
    monkeypatch.setattr(decision_evidence, "read", stale)
    result = deployment.readiness()
    assert not result["ready"]
    assert all(c["aggregates_ready"] and not c["decision_evidence_ready"] for c in result["cities"].values())
