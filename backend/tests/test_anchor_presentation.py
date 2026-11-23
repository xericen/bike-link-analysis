from backend.tests.local_requirements import requires_local_files, requires_local_inputs
import copy,hashlib,json
from backend.presentation.anchors import anchor_text,contextualize,distance_label,scope_answer,context,ROOT
from backend.services import precomputed

def test_anchor_distance_labels_and_values_unchanged():
    original={"ranking":[{"station_id":"ST-660","nearest_stop_distance_m":2784.23456789}],"candidate_count":1276,"limitations":["정류장과의 직선거리 기반","일반 버스 정류장과의 직선거리 보조 지표"]}
    snapshot=copy.deepcopy(original)
    seoul=contextualize(original,"seoul");sejong=contextualize(original,"sejong")
    assert original==snapshot
    assert seoul["ranking"][0]["nearest_stop_distance_m"]==2784.23456789
    assert sejong["ranking"][0]["nearest_stop_distance_m"]==2784.23456789
    assert seoul["distance_label"]=="최근접 지하철역(앵커) 거리"
    assert sejong["distance_label"]=="최근접 BRT 정류장(앵커) 거리"
    assert seoul["limitations"][1]=="일반 버스 정류장과의 직선거리 보조 지표"

def test_answer_anchor_scope_is_explicit():
    evidence=[{"tool":"get_transit_vulnerability","result":{"city":"seoul"}}]
    answer=scope_answer("최근접 정류장 거리 2784.2m",evidence)
    assert "지하철역" in answer and "최근접 정류장 거리" not in answer
    assert "2784.2m" in answer
    assert "BRT 정류장" in scope_answer("후보는 236개",[{**evidence[0],"result":{"city":"sejong"}}])

@requires_local_files("data/processed/kpi_cache.sqlite")
def test_audited_denominator_reasons_and_source_only():
    d=json.loads((ROOT/"docs/anchor_presentation_context.json").read_text())
    for city in ("seoul","daejeon","sejong"):
        value=d["contexts"][city+"|2025-12-01|2025-12-31"]
        link=precomputed.read("transit_linkage",city,"2025-12-01","2025-12-31")
        assert value["denominator_count"]==link["goal_metrics"]["anchor_300m_denominator_count"]
        assert value["master_total"]==len(link["stations"])
        assert value["analysis_station_count"]==precomputed.read("overview",city,"2025-12-01","2025-12-31")["station_count"]
        if city=="sejong":
            assert value["anchor_count"]==152
            assert value["source_name"]=="세종특별자치시 BRT노선별 정류장 현황"
            assert not value["brt_line_geometry_available"]

@requires_local_files("data/processed/kpi_cache.sqlite")
def test_kpi_cache_binary_unchanged():
    audit=json.loads((ROOT/"docs/anchor_presentation_context.json").read_text())
    assert audit["revision"]==precomputed.revision()
    assert hashlib.sha256(precomputed.path().read_bytes()).hexdigest()==audit["cache_sha256"]


def test_rank_wording_replay_changes_no_values():
    answer="상위 5곳 중 최대 수요는 남쪽주차장(SJ_00515)이며 실제 대여 802건입니다."
    evidence=[{"tool":"get_transit_vulnerability","result":{"city":"sejong","ranking":[{"station_id":"SJ_00515","rank":1,"rental_count":802}]}}]
    fixed=scope_answer(answer,evidence)
    assert "최대 수요" not in fixed and "개선 검토 우선순위" in fixed
    assert "802건" in fixed and "SJ_00515" in fixed
