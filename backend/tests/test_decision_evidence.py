import json
import pytest
from fastapi import HTTPException
from backend.services import decision_evidence
from scripts.validate.solar_paired_evaluation import score

def test_missing_or_stale_package_is_not_silently_served(tmp_path,monkeypatch):
    path=tmp_path/"study.json"
    monkeypatch.setattr(decision_evidence,"FILE",path)
    monkeypatch.setattr(decision_evidence.precomputed,"revision",lambda:"current")
    with pytest.raises(HTTPException) as error:decision_evidence.read("seoul")
    assert error.value.status_code==409
    path.write_text(json.dumps({"revision":"stale"}))
    with pytest.raises(HTTPException) as error:decision_evidence.read("seoul")
    assert error.value.status_code==409

def test_reference_period_is_explicit_and_response_copy_isolated(tmp_path,monkeypatch):
    path=tmp_path/"study.json"
    path.write_text(json.dumps({"revision":"v1","profiles":{"seoul":{"period_start":"2026-10-01","period_end":"2026-10-31","top3":[{"site_id":"a"}]}},"transfer_audit":{}}))
    monkeypatch.setattr(decision_evidence,"FILE",path)
    monkeypatch.setattr(decision_evidence.precomputed,"revision",lambda:"v1")
    first=decision_evidence.read("seoul","2026-10-25","2026-10-31")
    assert first["matches_selected_period"] is False
    assert first["period_start"]=="2026-10-01"
    assert first["transfer_audit"]["actual_transfer_rate"] is None
    first["top3"].clear()
    assert decision_evidence.read("seoul")["top3"]==[{"site_id":"a"}]

TRUTH={"candidate_count":3,"top_station_id":"ST-X","top_rentals":12,"top_anchor_distance_m":900.1234,"linked_trip_share":.4}

def test_abstention_does_not_become_perfect_accuracy():
    result=score('{"facts":{},"narrative_claims":[]}',TRUTH)
    assert result["coverage"]==0
    assert result["evidence_agreement"] is None
    assert result["unsupported_structured_claims"]==0

def test_wrong_id_and_claims_are_separate_from_unchecked_prose():
    result=score(json.dumps({"facts":{**TRUTH,"top_station_id":"ST-Y"},"narrative_claims":["주변 인구가 많다"]}),TRUTH)
    assert result["evidence_agreement"]==.8
    assert result["unsupported_structured_claims"]==1
    assert result["narrative_claims_outside_automatic_check"]==1
    assert not result["station_id_correct"]

def test_decision_tool_rejects_different_reference_period(monkeypatch):
    from backend.agents.solar import run_tool
    monkeypatch.setattr(decision_evidence,"read",lambda *args:{"matches_selected_period":False,"period_start":"2025-10-01","period_end":"2025-10-31","top3":[{"site_id":"must-not-leak"}]})
    result=run_tool("get_decision_evidence",{"region_id":"sejong","date_range":{"date_start":"2025-10-25","date_end":"2025-10-31"}})
    assert result["available"] is False
    assert "top3" not in result

def test_decision_routes_cannot_be_reassigned_to_another_grid():
    from backend.agents.decision_checks import check
    e=[{"tool":"get_decision_evidence","result":{"available":True,"city":"sejong",
        "top3":[{"site_id":"grid-1-2"},{"site_id":"grid-3-4"}],
        "route_audit":[{"candidate_id":"grid-1-2","routes":{"foot":{"distance_m":1234}}}]}}]
    assert check("grid-1-2 도보 1234m",e)["passed"]
    assert not check("grid-3-4 도보 1234m",e)["passed"]
    assert not check("인구밀도는 행정구 전체 밀도로 대체했으며 사용했습니다.",e)["passed"]
    assert check("인구밀도는 제외했으며 행정구 밀도로 대체하지 않았습니다.",e)["passed"]
