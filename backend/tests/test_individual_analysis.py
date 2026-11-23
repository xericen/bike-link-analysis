from backend.tests.local_requirements import requires_local_files, requires_local_inputs
"""Prepared full histories remain independent of the common December database."""
import json
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.main import app
from backend.presentation import individual
from backend.agents import solar
from backend.services import real_data

ROOT=Path(__file__).resolve().parents[2]
EXPECTED={"seoul":("2025-01-01","2025-12-31",37176546,12),"daejeon":("2024-08-01","2026-10-31",14992420,27),"sejong":("2020-01-01","2025-12-31",12903589,72)}

@pytest.mark.parametrize("city",EXPECTED)
@requires_local_files(*("data/individual/" + city + "/normalization.json" for city in ("seoul", "daejeon", "sejong")))
def test_full_history_matches_independently_saved_months_and_assets(city):
    start,end,total,months=EXPECTED[city]
    s=individual.scope(city)
    assert (s["start"],s["end"],s["rental_count"])==(start,end,total)
    norm=json.loads((ROOT/"data/individual"/city/"normalization.json").read_text())
    old=json.loads((ROOT/"data/reference/monthly_trends"/(city+".json")).read_text())
    assert norm["original_monthly_matches"]
    assert len(norm["monthly"])==months
    assert norm["monthly"]=={m["month"]:m["rental_count"] for m in old["months"]}
    assert sum(norm["monthly"].values())==total
    assert s["algorithm_revision"] and s["data_revision"] and s["reference_sha256"]
    prepared=individual.folder(city)
    react=ROOT/"frontend/public/assets/bike-link/individual"/s["asset_path"]
    for action in s["actions"]:
        a=(prepared/(action+".json")).read_bytes()
        assert a==(react/(action+".json")).read_bytes()
        packet=json.loads(a)
        assert (packet["period_start"],packet["period_end"])==(start,end)
        assert packet["precomputed"]["revision"]==s["revision"]
    assert individual.read(city,"overview")["total_rentals"]==total

@pytest.mark.parametrize("city",EXPECTED)
def test_reads_and_solar_tools_do_not_recompute_or_use_common_database(city,monkeypatch):
    s=individual.scope(city)
    def forbidden(*args,**kwargs):raise AssertionError("shared DB touched")
    monkeypatch.setattr(real_data,"overview",forbidden)
    monkeypatch.setattr(real_data,"profiles",forbidden)
    monkeypatch.setattr(real_data,"network",forbidden)
    ctx=individual.context(city,s["start"],s["end"])
    result=solar.run_tool("get_region_overview",{"region_id":city},ctx)
    assert result["total_rentals"]==s["rental_count"]
    assert result["analysis_scope"]=="individual_full"
    linked=solar.run_tool("get_transit_linkage",{"region_id":city},ctx)
    assert linked["goal_metrics"]["linked_trip_total"]==s["rental_count"]
    graph=solar.run_tool("get_network_analysis",{"region_id":city,"filters":{"node_limit":30}},ctx)
    assert len(graph["nodes"])==30
    assert graph["period_start"]==s["start"]
    comparison=solar.run_tool("compare_region_patterns",{"region_ids":[city]},ctx)
    assert comparison["available"] is False
    with pytest.raises(HTTPException):individual.read(city,"overview",{"date_start":"2025-12-01","date_end":"2025-12-31"})

@pytest.mark.parametrize("city",EXPECTED)
def test_candidate_selection_and_station_detail_are_resolved_from_full_period(city):
    s=individual.scope(city)
    station=individual.read(city,"stations")["stations"][0]
    plan=individual.read(city,"planning")
    site=plan["scenario_pool"][0]["site_id"]
    context=individual.context(city,s["start"],s["end"],{"station":{"region_id":city,"station_id":station["station_id"]},"candidate_city":city,"candidate_ids":[site]})
    assert context["selected_station"]["station_id"]==station["station_id"]
    assert context["selected_scenario"]["selected_ids"]==[site]
    assert context["selection_source"]["precomputed"]["revision"]==s["revision"]
    detail=individual.station(city,station["station_id"])
    assert detail["station"]["rental_count"]==station["rental_count"]
    with pytest.raises(ValueError):individual.context(city,s["start"],s["end"],{"candidate_city":city,"candidate_ids":["invented"]})
    client=TestClient(app)
    r=client.get("/api/individual/"+city+"/overview")
    assert r.status_code==200 and r.json()["total_rentals"]==s["rental_count"]
    assert client.get("/api/individual/"+city+"/overview?date_start=1900-01-01").status_code==422

def test_common_comparison_keeps_original_december_totals():
    from backend.presentation.monthly_trends import read
    value=read("all")
    assert value["summary"]["rental_count"]==2487201
    assert value["display_start"]=="2025-12-01" and value["display_end"]=="2025-12-31"
    assert {m["region_id"]:m["rental_count"] for m in value["months"]}=={"seoul":1954344,"daejeon":368491,"sejong":164366}
