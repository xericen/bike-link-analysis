from backend.tests.local_requirements import requires_local_files, requires_local_inputs
"""Completion checks use controlled fixtures, not fabricated observation results."""
import copy,json
from pathlib import Path
import pytest
from backend.agents.completion_checks import check,compact
from scripts.validate.timetable_journeys import itinerary,departures
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/completion-20261123"
@pytest.fixture
def evidence():
    return [{"tool":"get_project_conclusion","result":{"cities":[{"candidates":[
      {"site_id":"grid-1-1","nearby_rentals_1000m":100,"potential_added_area_m2":100000,"route":{"status":"model_connected","before_minutes":12,"after_minutes":8,"improvement_minutes":4}},
      {"site_id":"grid-2-2","nearby_rentals_1000m":200,"potential_added_area_m2":200000,"route":{"status":"route_unconfirmed","before_minutes":None,"after_minutes":None,"improvement_minutes":None}}]}]}}]
def test_candidate_numbers_cannot_be_borrowed_from_another_candidate(evidence):
    assert not check("grid-1-1 주변1km 관측 대여200건.",evidence)["passed"]
    assert check("grid-1-1 주변1km 관측 대여100건, grid-2-2 주변1km 관측 대여200건.",evidence)["passed"]
def test_units_and_same_candidate_area_are_checked(evidence):
    assert check("grid-1-1 추가 면적0.100km².",evidence)["passed"]
    assert not check("grid-1-1 추가 면적0.200km².",evidence)["passed"]
    assert not check("grid-1-1 추가 면적100건.",evidence)["passed"]
def test_basic_route_time_and_pending_status(evidence):
    assert check("grid-1-1 기본 도보12분, 연계8분, 단축4분.",evidence)["passed"]
    assert not check("grid-1-1 기본 단축-4분.",evidence)["passed"]
    assert not check("grid-2-2 경로가 확인되었습니다.",evidence)["passed"]
def test_effect_and_actual_transfer_are_not_invented(evidence):
    assert not check("실제 환승률12.3%입니다.",evidence)["passed"]
    assert not check("설치하면 이용량이20% 증가합니다.",evidence)["passed"]
    assert check("실제 환승률은 확인하지 못했습니다.",evidence)["passed"]
def test_compaction_preserves_source_and_candidate_facts(evidence):
    r=evidence[0]["result"];original=copy.deepcopy(r);r["project_goals"]={"long":"가"*100000}
    out=compact("get_project_conclusion",r)
    assert out["cities"][0]["candidates"]==original["cities"][0]["candidates"]
    assert len(json.dumps(out,ensure_ascii=False).encode())<=24000
    assert "project_goals" in r
def test_oversized_unknown_payload_is_explicitly_withheld():
    out=compact("unknown",{"available":True,"scope":"test","unrecognized":"가"*100000})
    assert out["details_withheld"] and "unrecognized" not in out
def test_waiting_can_eliminate_access_time_difference_and_missing_last_train():
    # Synthetic timetable fixture; no claim these are real observations.
    a=itinerary(0,3,[600],120);b=itinerary(0,5,[600],120)
    assert a["total_minutes"]==b["total_minutes"] and a["wait_minutes"]>b["wait_minutes"]
    assert not itinerary(700,0,[600],120)["available"]
def test_short_turn_trains_are_not_assumed_to_reach_destination():
    info={"data":{"cTimeList":[{"tm_zone":"23","tm_list_down_d":"10 20(정부청사) 30(반석)"}]}}
    assert departures(info)==[23*3600+600,23*3600+1800]
def test_prospective_journeys_and_field_audit_never_claim_historical_or_field_validation():
    j=json.loads((OUT/"journeys.json").read_text());a=json.loads((OUT/"site-audit.json").read_text())
    assert not j["historical_2025_validated"] and len(j["examples"])==3
    assert not a["field_verification_complete"]
    assert all(not r["field_verified"] and not r["is_historical_2025_inventory"] for r in a["seoul_dock_master"])

def test_initial_payload_budget_blocks_provider_call(monkeypatch,tmp_path):
    from backend.agents import solar
    from backend.tests.test_solar_recovery import setup_client
    from fastapi import HTTPException
    captured=setup_client(monkeypatch,tmp_path,[])
    ctx={"region_ids":["seoul"],"date_start":"2025-01-01","date_end":"2025-12-31","untrusted_extra":"x"*120000}
    with pytest.raises(HTTPException) as exc:solar.chat("분석 결론",ctx)
    assert exc.value.status_code==413 and not captured

def test_real_journey_components_conserve_time_and_same_origin_departure():
    report=json.loads((OUT/"journeys.json").read_text())
    for example in report["examples"]:
        for pair in example["examples"]:
            a,b=pair["transit_only"],pair["bike_plus_transit"]
            assert a["origin_departure_s"]==b["origin_departure_s"]
            for leg in (a,b):
                assert leg["available"] and leg["wait_minutes"]>=0
                assert leg["total_minutes"]==pytest.approx(sum(leg[k] for k in ("access_minutes","station_entry_minutes","wait_minutes","rail_minutes","station_exit_minutes")))
            assert pair["total_gain_minutes"]==pytest.approx(a["total_minutes"]-b["total_minutes"])

def test_translated_ids_and_changed_pickup_assumptions_are_not_approved(evidence):
    r=evidence[0]["result"]["cities"][0]["candidates"][0]
    r["additional_validation"]={"overhead_sensitivity":[{"overhead_minutes":2,"gain_minutes":4},{"overhead_minutes":5,"gain_minutes":1}]}
    assert not check("격자-1-1 주변1km 관측 대여100건.",evidence)["passed"]
    assert not check("grid-1-1 5분 가정에서4분 단축.",evidence)["passed"]
    assert check("grid-1-1 5분 가정에서1분 단축.",evidence)["passed"]

def test_rank_alias_time_confusion_and_sign_interpretation(evidence):
    r=evidence[0]["result"]["cities"][0]["candidates"][0];r["rank"]=1;r["route"]["anchor_name"]="답십리"
    assert not check("1순위 답십리 기본 도보로8분에서4분 단축.",evidence)["passed"]
    assert not check("grid-1-1 4분으로 크게 느립니다.",evidence)["passed"]
    assert check("1순위 답십리 기본 도보로12분에서4분 단축.",evidence)["passed"]

@pytest.mark.parametrize("city",["seoul","daejeon","sejong"])
def test_actual_live_erroneous_prose_is_withheld(city):
    from backend.agents.solar import finalize_answer
    r=json.loads((OUT/"live-solar"/("solar-"+city+".json")).read_text());b=r["response"]
    result=finalize_answer(r["question"],b.get("solar_answer") or b["answer"],b["evidence"],b.get("analysis_context"),b.get("model_finish_reason"))
    assert not result["completion_validation"]["passed"]
    assert result["answer_basis"]=="tool_summary" and "grid-" in result["answer"]

@pytest.mark.parametrize("city,trips,members",[("seoul",37176546,12),("daejeon",14992420,27),("sejong",12903589,24)])
def test_full_raw_spark_reconciles_all_three_outputs(city,trips,members):
    from backend.presentation.individual import scope
    r=json.loads((OUT/("spark-raw-"+city+".json")).read_text())
    assert r["source_revision"]==scope(city)["revision"]
    assert r["valid_rows"]==trips and r["members"]==members
    assert r["raw_rows"]==r["valid_rows"]+r["excluded_rows"]+r["duplicate_rows"]
    for table in ("od","station_usage","anchor_hours"):
        assert r[table]["matches"] and r[table]["actual"]==r[table]["expected"]
        assert len(r[table]["actual"]["sha256_limb_sums"])==4

@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_compact_conclusion_preserves_prospective_scope_and_time_assumptions():
    from backend.research.conclusion import tool
    from backend.presentation.individual import scope
    s=scope("daejeon");r=compact("get_project_conclusion",tool("daejeon",s["start"],s["end"]))
    reference=r["cities"][0]["completion"]
    assert "2026-11-23" in reference["journey_scope"] and "재현 아님" in reference["journey_scope"]
    assert reference["assumed_minutes"]=={"pickup_return":2,"station_entry":2,"station_exit":2}
    assert len(reference["journey_rows"])==9 and "journeys" not in reference
