"""All synthetic coordinates below are isolated test fixtures, never service evidence."""
import copy
import json

import pytest
from shapely.geometry import Point, box

from backend.analysis.planning import PROJECT, UNPROJECT, grid_sites
from backend.research import method_validation as m
from backend.research import presentation

def station(sid,x=0,y=0,count=10):
    centre=PROJECT(127,37.5)
    lon,lat=UNPROJECT(centre[0]+x,centre[1]+y)
    return {"station_id":sid,"latitude":lat,"longitude":lon,
            "coordinate_valid":True,"rental_count":count,"return_count":3}

def edge(o,d,n):
    return {"origin_station_id":o,"destination_station_id":d,"trip_count":n}

def test_hidden_demand_cannot_leak_to_neighbourhood_features():
    rows=[station("hidden",count=99999),station("a"),station("b")]
    od=[edge("hidden","a",50),edge("b","hidden",60),edge("a","b",7)]
    kept,audit=m.retain_training(rows,od,["hidden"])
    assert {r["station_id"] for r in kept}=={"a","b"}
    assert {r["station_id"]:r["rental_count"] for r in kept}=={"a":7,"b":0}
    assert {r["station_id"]:r["return_count"] for r in kept}=={"a":0,"b":7}
    assert audit["removed_od_trips"]==110
    assert audit["hidden_station_count_in_training"]==0
    changed=copy.deepcopy(rows);changed[0]["rental_count"]=1
    assert kept==m.retain_training(changed,od,["hidden"])[0]

def test_empty_training_never_reuses_original_counts():
    kept,audit=m.retain_training([station("a"),station("b")],[edge("a","b",99)],["a"])
    assert kept[0]["rental_count"]==kept[0]["return_count"]==0
    assert audit["retained_od_trips"]==0

def test_matching_is_one_to_one_and_radius_is_inclusive():
    targets=[station("a"),station("b",10)]
    one=[{**station("p",5),"site_id":"p"}]
    assert m.geographic_matches(targets,one)["hits"]==1
    far=[{**station("p",1000),"site_id":"p"}]
    assert m.geographic_matches(targets,far)["hits"]==0
    assert m.geographic_matches([],one)["recall"] is None

def test_assignment_maximizes_recovery_instead_of_greedy_pairs():
    targets=[station("a",0),station("b",200)]
    candidates=[{**station("p",100),"site_id":"p"},{**station("q",-200),"site_id":"q"}]
    assert m.geographic_matches(targets,candidates,300)["hits"]==2

@pytest.mark.parametrize("use_population",[True,False])
def test_fast_grid_is_equivalent_to_existing_production_rules(use_population):
    x,y=PROJECT(127,37.5)
    boundary=box(x-1600,y-1600,x+1600,y+1600)
    baseline=Point(x,y).buffer(500,quad_segs=16)
    districts=[{"name":"fixture","geometry":boundary,"population_density_km2":100}]
    rows=[station("a"),station("b",1500,1500,30)]
    facilities=[{"lat":37.5,"lon":127}]
    expected=grid_sites(boundary,baseline,rows,facilities,districts,use_population=use_population)
    actual,weights=m.grid_candidates(boundary,baseline,rows,facilities,districts,use_population=use_population)
    assert [r["site_id"] for r in actual]==[r["site_id"] for r in expected]
    assert [r["score"] for r in actual]==pytest.approx([r["score"] for r in expected],abs=1e-12)
    if not use_population:assert "population_density_km2" not in weights

def demand_row(name,t,b):
    return {"station_name":name,"transit_total":t,"bike_activity_500m":b,
            "bike_station_count_500m":0 if b==0 else 2}

def test_quadrants_use_matched_city_medians_and_do_not_fabricate_missing():
    rows=[demand_row("a",100,100),demand_row("b",100,1),
          demand_row("c",1,100),demand_row("d",1,1)]
    v=m.demand_matrix({"available":True,"stations":rows,"rail_unique_station_names":4})
    assert v["counts"]=={"high_high":1,"high_low":1,"low_high":1,"low_low":1}
    assert v["matched_count"]==4
    assert v["rows"][0]["bike_per_station"]==50
    absent=m.demand_matrix({"available":False,"message":"missing"})
    assert not absent["available"] and "rows" not in absent

def test_report_fails_closed_after_input_or_code_change(tmp_path,monkeypatch):
    path=tmp_path/"report.json"
    monkeypatch.setattr(m,"FILE",path)
    monkeypatch.setattr(presentation.precomputed,"revision",lambda:"v1")
    monkeypatch.setattr(m,"dependencies",lambda:{"source":"hash"})
    with pytest.raises(presentation.HTTPException) as exc:presentation.read("seoul")
    assert exc.value.status_code==409
    data={"available":True,"revision":"v1","dependencies":{"source":"hash"},
          "built_at":"test","period_start":m.START,"period_end":m.END,"scope_note":"fixed experiment",
          "limitations":[],"cities":{"seoul":{"city":"seoul"}}}
    path.write_text(json.dumps(data))
    assert presentation.read("seoul")["period_start"]==m.START
    response=presentation.read("seoul");response["cities"][0]["city"]="mutated"
    assert presentation.read("seoul")["cities"][0]["city"]=="seoul"
    monkeypatch.setattr(m,"dependencies",lambda:{"source":"changed"})
    with pytest.raises(presentation.HTTPException):presentation.read("seoul")

def test_city_validation_and_request_never_calls_builder(monkeypatch,tmp_path):
    with pytest.raises(presentation.HTTPException) as exc:presentation.read("../seoul")
    assert exc.value.status_code==404
    monkeypatch.setattr(m,"FILE",tmp_path/"missing.json")
    monkeypatch.setattr(m,"grid_candidates",lambda *a,**k:pytest.fail("request computed candidates"))
    with pytest.raises(presentation.HTTPException):presentation.read("all")

def test_zero_median_does_not_classify_absent_bike_activity_as_high():
    value=m.demand_matrix({"available":True,"stations":[demand_row("a",10,0),demand_row("b",20,0)]})
    assert value["counts"]["high_high"]==0
    assert all(r["quadrant"].endswith("low") for r in value["rows"])
    assert all(r["bike_per_station"] is None for r in value["rows"])

def test_spatial_fold_hides_whole_block_not_just_first_ten():
    x,y=PROJECT(127,37.5)
    # Place all points well inside a single projected 1km cell.
    ox=(int(x//1000)+0.5)*1000;oy=(int(y//1000)+0.5)*1000
    lon,lat=UNPROJECT(ox,oy)
    rows=[{"station_id":str(i),"latitude":lat,"longitude":lon,"coordinate_valid":True,"rental_count":i+1} for i in range(15)]
    boundary=box(ox-400,oy-400,ox+400,oy+400)
    folds=m.mask_folds(rows,boundary)
    spatial=[f for f in folds if f[0]=="spatial_1km_block"]
    assert len(spatial)==1 and len(spatial[0][2])==15

def test_zero_transit_total_is_not_assumed_to_be_observed_no_demand():
    value=m.demand_matrix({"available":True,"stations":[demand_row("unknown",0,200),demand_row("observed",20,20)]})
    assert value["linked_station_count"]==2 and value["matched_count"]==1
    assert value["excluded_rows"][0]["station_name"]=="unknown"
    assert value["rows"][0]["station_name"]=="observed"
