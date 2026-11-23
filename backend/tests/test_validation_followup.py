"""Synthetic fixtures here remain separate from real research artifacts."""
import copy
import pytest
from shapely.geometry import box
from backend.research import method_validation as m, validation_followup as f
from backend.presentation.viewer_cache import refresh
from backend.agents import solar

def station(sid,x=0,y=0,anchor=700):
    px,py=m.PROJECT(127,37.5)
    lon,lat=m.UNPROJECT(px+x,py+y)
    return {"station_id":sid,"latitude":lat,"longitude":lon,"coordinate_valid":True,
            "rental_count":10,"return_count":5,"nearest_anchor_distance_m":anchor}

def point(sid,x=0):
    return {**station(sid,x),"site_id":sid,"district":"fixture","rank":1}

def test_recurrence_excludes_buffer_only_duplicate_and_reports_proximity():
    top=[point("grid-a")]
    base={"top":top,"candidate_buffer_m":300,"grid_step_m":500,"anchor_radius_m":500,"policy":"equal"}
    rows=[base,{**base,"candidate_buffer_m":500},
          {**base,"grid_step_m":250,"top":[point("grid-b",20)]},
          {**base,"policy":"demand","top":[point("grid-c",2000)]}]
    result=f.recurrence(rows)["items"][0]
    assert result["same_grid_hits"]==1 and result["same_grid_tests"]==2
    assert result["changed_grid_hits"]==1 and result["changed_grid_tests"]==1
    assert result["total_tests"]==3

def test_gap_eligibility_uses_other_stations_and_fixed_anchor_rule():
    px,py=m.PROJECT(127,37.5)
    boundary=box(px-4000,py-4000,px+4000,py+4000)
    rows=[station("a"),station("b",100),station("eligible",1500),station("near-anchor",3000,anchor=400)]
    eligible,audit=f.eligible_targets(rows,boundary)
    assert [r["station_id"] for r in eligible]==["eligible"]
    assert audit["eligible"]==1
    assert audit["excluded_by_first_rule"]["near_anchor"]==1
    assert audit["excluded_by_first_rule"]["near_other_bike_station"]==2

def test_neighborhood_totals_must_match_existing_radius_data():
    rows=[station("a"),station("b",30)]
    matrix={"available":True,"rows":[{"station_name":"fixture","quadrant":"high_low",
        "latitude":rows[0]["latitude"],"longitude":rows[0]["longitude"],"transit_total":100,
        "bike_activity_500m":30,"bike_station_count_500m":2}]}
    result=f.neighborhoods(matrix,rows,"seoul")
    assert len(result[0]["nearby_stations"])==2
    changed=copy.deepcopy(matrix);changed["rows"][0]["bike_activity_500m"]=31
    with pytest.raises(AssertionError):f.neighborhoods(changed,rows,"seoul")

def test_viewer_refresh_does_not_clear_other_project_or_route_state(tmp_path):
    source=tmp_path/"controller.py";source.write_text("new source")
    key="route.fn#"+str(source)
    cache={key:"old compiled","route.code#bike.link.viewer":"old code",
           "route.fn#/unrelated/controller.py":"keep","route.code#other":"keep","urlmap":"keep"}
    assert refresh(cache,source)
    assert key not in cache and "route.code#bike.link.viewer" not in cache
    assert cache["route.code#other"]=="keep" and cache["urlmap"]=="keep"
    assert cache["route.fn#/unrelated/controller.py"]=="keep"
    assert not refresh(cache,source)
    source.write_text("source changed again")
    assert refresh(cache,source)

def test_new_tool_is_registered_and_never_falls_back_to_individual_scope(monkeypatch):
    from backend.research.runtime import presentation
    p=presentation()
    calls=[]
    def report(city,start,end,anchor_name,station_id,top_n):
        calls.append((city,start,end,anchor_name,station_id,top_n))
        return {"available":False,"message":"reference period mismatch"}
    monkeypatch.setattr(p,"tool_report",report)
    from backend.presentation import individual
    monkeypatch.setattr(individual,"tool",lambda *a:pytest.fail("new tool was intercepted by individual packet mapper"))
    context={"region_ids":["seoul"],"date_start":"2025-01-01","date_end":"2025-12-31"}
    value=solar.run_tool("get_method_validation",{"region_id":"seoul","anchor_name":"fixture"},context)
    assert not value["available"]
    assert calls[0][1:3]==("2025-01-01","2025-12-31")
    assert "get_method_validation" in solar.TOOL_DEFINITIONS

def test_report_keeps_zero_recovery_as_actual_finding():
    result={"available":True,"city":"seoul","period_start":m.START,"period_end":m.END,
            "original_recovery":[{"fold":"high_usage","hits":0,"target_count":10}],
            "matrix":{"available":True,"counts":{"high_low":42}},"limitations":[]}
    value=solar._report("검증","실제 근거", [{"tool":"get_method_validation","arguments":{"region_id":"seoul"},"result":result}])
    assert any(x.get("value")==0 and "가림" in x.get("label","") for x in value["key_findings"])

def test_followup_period_mismatch_abstains_before_data_access(monkeypatch):
    from backend.research import presentation as p
    monkeypatch.setattr(p,"read_support",lambda *a:pytest.fail("mismatched reference was read"))
    result=p.tool_report("seoul","2025-02-01","2025-03-31")
    assert not result["available"]
    assert "anchor_reviews" not in result

def test_stale_followup_never_overwrites_original_failure(tmp_path,monkeypatch):
    from backend.research import presentation as p
    path=tmp_path/"followup.json"
    import json
    path.write_text(json.dumps({"revision":"old","dependencies":{}}))
    monkeypatch.setattr(f,"FILE",path)
    monkeypatch.setattr(p,"read",lambda city:{"revision":"current","cities":[{"city":city,"backtest":[{"hits":0}]}]})
    value=p.read_support("seoul")
    assert not value["followup_available"]
    assert value["cities"][0]["backtest"]==[{"hits":0}]
    assert "followup" not in value["cities"][0]

def test_anchor_review_rejects_unknown_names_and_copies_response(monkeypatch):
    from backend.research import presentation as p
    source={"followup_available":True,"cities":[{"followup":{"matrix_neighborhoods":[{"anchor_name":"real","nearby_stations":[{"station_id":"one"}]}]}}]}
    monkeypatch.setattr(p,"read_support",lambda *a:source)
    with pytest.raises(p.HTTPException) as exc:p.anchor("seoul","invented")
    assert exc.value.status_code==404
    result=p.anchor("seoul","real");result["nearby_stations"].clear()
    assert source["cities"][0]["followup"]["matrix_neighborhoods"][0]["nearby_stations"]
