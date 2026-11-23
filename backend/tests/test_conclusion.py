from backend.tests.local_requirements import requires_local_files, requires_local_inputs
"""Conclusions preserve scope, independently sourced month totals, route validity and legacy analysis."""
import hashlib,json,math
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.main import app
from backend.research import conclusion as c
from backend.presentation import individual,monthly_trends
from backend.agents.solar import run_tool
from scripts.validate import build_conclusion as batch
ROOT=c.ROOT
MONTHS=["2025-01"]+["2025-"+str(m).zfill(2) for m in range(4,13)]

@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_common_comparison_uses_exactly_ten_complete_months_and_equal_days():
    result=c.read("all")
    assert result["common_months"]==MONTHS and len(result["comparison"])==10
    assert len(result["cities"])==3 and result["scope"]=="common_multi_month"
    assert all("2025-02"!=r["month"]!="2025-03" for r in result["comparison"])
    for city in result["cities"]:
        raw=json.loads((ROOT/"data/reference/monthly_trends"/(city["city"]+".json")).read_text())
        selected=[r for r in raw["months"] if r["month"] in MONTHS]
        assert all(r["complete"] for r in selected)
        assert city["metrics"]["observed_days"]==306
        assert city["metrics"]["rental_count"]==sum(r["rental_count"] for r in selected)
        assert math.isclose(city["metrics"]["anchor_linked_ratio"],sum(r["anchor_linked_trips"] for r in selected)/sum(r["rental_count"] for r in selected))

@pytest.mark.parametrize("city",["seoul","daejeon","sejong"])
@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_individual_candidates_are_original_full_scope_with_reproducible_month_recurrence(city):
    result=c.read(city);packet=result["cities"][0];scope=individual.scope(city)
    assert result["scope"]=="individual_full"
    assert (packet["period_start"],packet["period_end"])==(scope["start"],scope["end"])
    canonical=individual.read(city,"planning")["new_sites"][:3]
    assert [r["site_id"] for r in packet["candidates"]]==[r["site_id"] for r in canonical]
    raw=json.loads((ROOT/"data/reference/monthly_trends"/(city+".json")).read_text())
    eligible={r["month"] for r in raw["months"] if r["complete"]}
    for row in packet["candidates"]:
        assert row["eligible_months"]==len(eligible)
        assert row["top10_months"]==sum(r["rank"]<=10 for r in row["monthly_ranks"])
        assert all(r["month"] in eligible for r in row["monthly_ranks"])
        assert row["nearby_rentals_1000m"]==canonical[row["rank"]-1]["nearby_rentals_1000m"]
    ctx={"region_ids":[city],"date_start":scope["start"],"date_end":scope["end"]}
    result=run_tool("get_project_conclusion",{"region_id":city},ctx)
    assert result["scope"]=="individual_full"
    assert "geometry" not in json.dumps(result)
    assert "comparison" not in result

@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_every_confirmed_chain_has_close_snaps_and_correct_model_time():
    for mode in ("common","individual"):
        for city in ("seoul","daejeon","sejong"):
            result=c.read(city,mode)["cities"][0]
            for s in result["candidates"]:
                r=s["route"]
                if r["status"]=="model_connected":
                    assert max(r["bike_to_dock"]["snap_distances_m"])<=50
                    assert max(r["walk_to_anchor"]["snap_distances_m"])<=50
                    assert batch.metres((r["dock_latitude"],r["dock_longitude"]),(r["anchor_latitude"],r["anchor_longitude"]))<=300
                    assert math.isclose(r["after_minutes"],(r["bike_to_dock"]["duration_s"]+r["walk_to_anchor"]["duration_s"]+120)/60)
                    if r.get("before_minutes") is not None:
                        assert math.isclose(r["improvement_minutes"],r["before_minutes"]-r["after_minutes"])
                else:
                    assert r["after_minutes"] is None and r["improvement_minutes"] is None
                assert not r["field_installation_verified"]
            assert result["model_connected_count"]==sum(s["route"]["status"]=="model_connected" for s in result["candidates"])
            for threshold in result["time_threshold_sensitivity"]:
                assert threshold["candidate_count"]==sum(s["route"].get("after_minutes") is not None and s["route"]["after_minutes"]<=threshold["minutes"] for s in result["candidates"])

@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_common_reference_is_explicit_and_never_silently_replaces_december():
    ctx={"region_ids":["seoul","daejeon","sejong"],"date_start":"2025-12-01","date_end":"2025-12-31"}
    no=run_tool("get_project_conclusion",{"region_id":"seoul"},ctx)
    assert no["available"] is False
    yes=run_tool("get_project_conclusion",{"region_id":"seoul","scope":"common"},ctx)
    assert yes["reference_scope"] is True and yes["scope"]=="common_multi_month"
    assert all(set(r["cities"])=={"seoul"} for r in yes["comparison"])
    assert yes["selected_context_period"]=={"start":"2025-12-01","end":"2025-12-31"}
    assert monthly_trends.read("all")["summary"]["rental_count"]==2487201

@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_readonly_api_uses_saved_results_and_rejects_invalid_scope(monkeypatch):
    monkeypatch.setattr(batch.Router,"get",lambda *a:pytest.fail("runtime external routing"))
    client=TestClient(app)
    assert client.get("/api/conclusion?city=all").status_code==200
    assert client.get("/api/conclusion?city=all&scope=individual").status_code==422
    assert client.get("/api/conclusion?city=unknown").status_code==404
    assert client.get("/api/conclusion?city=seoul&scope=wrong").status_code==422

def test_router_uses_cache_and_rejects_large_snap(tmp_path,monkeypatch):
    monkeypatch.setattr(batch,"CACHE",tmp_path)
    monkeypatch.setattr(batch.requests,"get",lambda *a,**k:pytest.fail("cache should be reused"))
    a=(37.,127.);b=(37.1,127.1)
    url=f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{a[1]},{a[0]};{b[1]},{b[0]}"
    path=tmp_path/(hashlib.sha256(url.encode()).hexdigest()+".json")
    path.write_text(json.dumps({"code":"Ok","routes":[{"distance":100,"duration":60}],"waypoints":[{"distance":0},{"distance":51}]}))
    assert batch.Router().get("foot",a,b)["status"]=="snap_uncertain"

def test_network_failure_circuit_breaker_does_not_fabricate_routes(tmp_path,monkeypatch):
    monkeypatch.setattr(batch,"CACHE",tmp_path);monkeypatch.setattr(batch.time,"sleep",lambda *a:None)
    def fail(*args,**kwargs):raise batch.requests.Timeout()
    monkeypatch.setattr(batch.requests,"get",fail)
    router=batch.Router()
    rows=[router.get("bike",(37+i*.01,127.),(37.2,127.2)) for i in range(5)]
    assert router.requests==3
    assert all(r["status"]=="unavailable" for r in rows)
    assert rows[-1]["reason"]=="provider_circuit_breaker"

@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_result_copy_does_not_mutate_stored_conclusion():
    first=c.read("seoul");first["cities"][0]["candidates"][0]["rank"]=999
    assert c.read("seoul")["cities"][0]["candidates"][0]["rank"]==1

@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_connection_alone_is_not_a_positive_recommendation():
    packet=c.read("daejeon")["cities"][0]
    slower=[r for r in packet["candidates"] if r["route"].get("improvement_minutes") is not None and r["route"]["improvement_minutes"]<=0]
    assert slower
    assert all("재검토" in r["action"] for r in slower)

@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_conclusion_matches_five_original_goals_without_overclaiming():
    result=c.read("all")
    goals=result["project_goals"]["items"]
    assert [g["number"] for g in goals]==[1,2,3,4,5]
    assert all(g["objective"] and g["finding"] and g["remaining"] for g in goals)
    assert "노선" in goals[1]["objective"] and "미확보" in goals[1]["status"]
    assert "직접 항으로 통합되지" in goals[2]["remaining"]
    assert "전체 여정" in goals[3]["remaining"]
    assert "서울 3/3곳" in goals[3]["evidence"]
    assert "Upstage Solar" in goals[4]["objective"]
    selected=c.read("sejong")["project_goals"]["items"][3]["evidence"]
    assert "세종 1/3곳" in selected and "서울 3/3곳" not in selected
