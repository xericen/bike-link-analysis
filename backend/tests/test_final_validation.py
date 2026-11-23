from backend.tests.local_requirements import requires_local_files, requires_local_inputs
"""Independent checks for withheld periods, route uncertainty and grounded fallback."""
import json,math
from backend.research import conclusion
from backend.agents.solar import finalize_answer
from scripts.validate.final_validation import TRAIN,TEST,OUT
def test_training_and_evaluation_are_disjoint_and_identical_across_cities():
    assert not set(TRAIN)&set(TEST)
    r=json.loads((OUT/"results.json").read_text())
    for c in r["cities"].values():
        t=c["temporal"]
        assert t["train_months"]==TRAIN and t["test_months"]==TEST
        assert t["features"]==["facilities_within_500m","nearby_rentals_1000m","gap_ratio"]
        assert len(t["methods"])==2 and t["operational_update"] is False
        assert all(len(x["selected_sites"])==len(set(x["selected_sites"]))==3 for x in t["methods"])
def test_daejeon_uncertain_and_slower_candidates_cannot_enter_checked_order():
    r=json.loads((OUT/"daejeon.json").read_text())["routes"]
    bad={x["site_id"] for x in r["candidates"] if x["review_status"]!="positive_model"}
    assert bad and not bad.intersection(r["review_order"])
    for row in r["candidates"]:
        if not row["best_checked_route"]:
            assert all(s["gain_minutes"] is None for s in row["overhead_sensitivity"])
            continue
        gains=[s["gain_minutes"] for s in row["overhead_sensitivity"]]
        assert math.isclose(gains[0]-gains[1],2) and math.isclose(gains[1]-gains[2],3)
@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_extra_route_checks_preserve_original_scope_and_route():
    original=json.loads((OUT.parent/"conclusion-20261123/results.json").read_text())
    for city in ("seoul","daejeon","sejong"):
        packet=conclusion.read(city)["cities"][0]
        old=next(r for r in original["individual_cities"] if r["city"]==city)
        assert [(r["site_id"],r["score"],r["rank"],r["route"]) for r in packet["candidates"]]==[(r["site_id"],r["score"],r["rank"],r["route"]) for r in old["candidates"]]
        assert packet["additional_validation"]["full_journey"]["available"] is False
        # API/agent supplement must not duplicate routing geometry.
        assert "geometry" not in json.dumps(packet["additional_validation"])
def test_spark_entire_current_scope_counts_match_original_totals():
    r=json.loads((OUT/"spark.json").read_text())
    assert r["all_match"] and not r["raw_normalization_in_spark"]
    assert {x["city"]:x["trips"] for x in r["results"]}=={"seoul":37176546,"daejeon":14992420,"sejong":12903589}
    assert sum(x["daily_od_rows"] for x in r["results"])==41850476
def test_real_solar_fallback_keeps_candidate_ids_and_negative_time():
    r=json.loads((OUT/"solar-daejeon.json").read_text());b=r["response"]
    result=finalize_answer(r["question"],b.get("solar_answer") or b["answer"],b["evidence"],b["analysis_context"],fallback_reason="test_force_hold")
    assert "grid-987500-1816500" in result["answer"]
    assert "-3.894" in result["answer"]
    assert "2024-08-01" in result["answer"] and result["answer_basis"]=="tool_summary"
