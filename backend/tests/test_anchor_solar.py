from backend.agents.solar import finalize_answer,run_tool
from backend.services import vulnerability

def test_withhold_sejong_population_substitution_claim():
    evidence=[{"tool":"get_site_planning","arguments":{"region_id":"sejong"},"result":{"city":"sejong","available":False,"population_basis":"세종 인구밀도 점수에서 제외","new_sites":[]}}]
    result=finalize_answer("세종 분석","세종은 인구밀도 대신 행정구 밀도만 사용했으며 추가 검증이 필요합니다.",evidence,finish_reason="stop")
    assert result["answer_basis"]=="tool_summary"
    assert not result["anchor_population_validation"]["passed"]
    correct=finalize_answer("세종 분석","세종은 인구밀도를 사용하지 않습니다.",evidence,finish_reason="stop")
    assert correct["answer_basis"]=="solar_interpretation"

def test_anchor_band_tool_limit_preserves_total(monkeypatch):
    monkeypatch.setattr(vulnerability,"prepared",lambda *a,**k:{"candidates":[],"first_last_mile_candidates":[{"station_id":str(i)} for i in range(9)],"first_last_mile_count":66})
    result=run_tool("get_transit_vulnerability",{"region_id":"sejong"})
    assert len(result["first_last_mile_candidates"])==5
    assert result["first_last_mile_count"]==66
