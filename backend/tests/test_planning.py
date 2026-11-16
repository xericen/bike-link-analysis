"""Planning invariants: measured inputs, exact geometry, ranking and copied releases."""
import os,shutil,json
import pytest
from shapely.geometry import Point,box,shape
from shapely import to_wkb
from backend.analysis.planning import PROJECT,vector,grid_sites,selection_scenarios,sensitivity
from backend.analysis.vulnerability import rank_candidates,spatial_scenario
from backend.services import input_manifest,precomputed,planning,periods

def test_manifest_copy_touch_and_same_size_tamper(tmp_path):
    a=tmp_path/"a";b=tmp_path/"b";a.mkdir()
    (a/"stations.csv").write_text("abc")
    original=input_manifest.verify(a,create=True)
    shutil.copytree(a,b)
    os.utime(b/"stations.csv",ns=(1234567890,1234567890))
    assert input_manifest.current(b)=="unverified-inputs"
    assert input_manifest.verify(b)==original
    assert input_manifest.current(b)==original
    (b/"stations.csv").write_text("xyz")
    with pytest.raises(RuntimeError):input_manifest.verify(b)

def test_all_stop_vector_and_boundary_clipping():
    x,y=PROJECT(127,37.5);boundary=box(x-600,y-600,x+600,y+600)
    points=((37.5,127),(37.5,127.02))
    scenario,_=spatial_scenario(points,(("A",37.5,127,0),),to_wkb(boundary))
    assert scenario["boundary_clipped"]
    assert scenario["baseline_area_m2"]<=boundary.area
    geo=vector(boundary)
    assert geo["properties"]["area_error_ratio"]<.001

def test_new_grid_sites_without_existing_station():
    x,y=PROJECT(127,37.5);boundary=box(x-1500,y-1500,x+1500,y+1500)
    baseline=Point(x,y).buffer(500)
    stations=[{"station_id":"A","coordinate_valid":True,"latitude":37.5,"longitude":127,"rental_count":20}]
    districts=[{"name":"구","geometry":boundary,"population_density_km2":1000}]
    rows=grid_sites(boundary,baseline,stations,[],districts)
    assert rows and all(r["nearest_station_distance_m"]>300 for r in rows)
    assert all(r["station_id"].startswith("grid-") for r in rows)
    assert all(r["population_basis"].startswith("administrative") for r in rows)

def test_subset_scenario_union_excludes_overlap():
    x,y=PROJECT(127,37.5);boundary=Point(x,y).buffer(3000);baseline=Point(x,y).buffer(100)
    states=selection_scenarios(to_wkb(boundary),to_wkb(baseline),(("A",37.5,127),("B",37.5001,127)))
    both=next(s for s in states if len(s["selected_ids"])==2)
    singles=sum(s["added_area_m2"] for s in states if len(s["selected_ids"])==1)
    assert both["added_area_m2"]<singles and both["overlap_area_m2"]>0
    assert len(states)==4
    assert next(s for s in states if not s["selected_ids"])["added_area_m2"]==0

def test_ranking_demand_counted_once_and_small_population():
    rows=[{"station_id":"A","vulnerability":10,"accessibility_deficit":1,"rental_count":10,"potential_added_area_m2":100},
          {"station_id":"B","vulnerability":1000,"accessibility_deficit":1,"rental_count":10,"potential_added_area_m2":100}]
    rank_candidates(rows)
    assert rows[0]["score"]==rows[1]["score"]
    assert "vulnerability" not in rows[0]["score_components"]
    assert rows[0]["score_confidence"]=="insufficient_candidates"
    stats=sensitivity([{**r,"nearest_stop_distance_m":600} for r in rows])
    assert len(stats)==9
    assert next(r for r in stats if r["distance_m"]==800)["candidate_count"]==0

def test_scenario_lookup_never_computes_and_rejects_unknown(monkeypatch):
    monkeypatch.setattr(planning,"prepared",lambda *a:{"selection_states":[{"selected_ids":["A"],"added_area_m2":3}]})
    assert planning.scenario("seoul",None,None,["A"])["added_area_m2"]==3
    with pytest.raises(ValueError):planning.scenario("seoul",None,None,["unknown"])
    with pytest.raises(ValueError):planning.scenario("all",None,None,[])

def test_facility_can_create_candidate_beyond_observed_station_neighbourhood():
    from backend.analysis.planning import UNPROJECT
    x,y=PROJECT(127,37.5)
    boundary=box(x-2500,y-2500,x+2500,y+2500)
    lon,lat=UNPROJECT(x+2000,y)
    stations=[{"station_id":"A","coordinate_valid":True,"latitude":37.5,"longitude":127,"rental_count":20}]
    facilities=[{"lat":lat,"lon":lon,"type":"library"}]
    rows=grid_sites(boundary,Point(x,y).buffer(500),stations,facilities,
                    [{"name":"구","geometry":boundary,"population_density_km2":1000}])
    assert any(r["nearest_station_distance_m"]>1000 and r["nearby_rentals_1000m"]==0
               and r["facilities_within_500m"]>0 for r in rows)

def test_planning_api_is_prepared_only(monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    from backend.main import app
    monkeypatch.setattr(precomputed,"PROCESSED",tmp_path)
    monkeypatch.setattr(periods,"resolve",lambda *a:("2026-10-01","2026-10-31"))
    precomputed.put("planning","seoul","2026-10-01","2026-10-31",
                    {"available":True,"selection_states":[{"selected_ids":["A"],"added_area_m2":123}]})
    def forbidden(*a,**k):raise AssertionError("request-time spatial computation")
    monkeypatch.setattr(planning,"build",forbidden)
    client=TestClient(app)
    assert client.get("/api/planning?city=seoul").status_code==200
    assert client.get("/api/planning/scenario?city=seoul&selected=A").json()["added_area_m2"]==123
    assert client.get("/api/planning/scenario?city=seoul&selected=invalid").status_code==422
