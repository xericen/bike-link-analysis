"""Anchor scope, lossless IDs, raw-data quality exclusions and geometric gap denominator."""
from shapely.geometry import Point,box
from shapely import to_wkb
from backend.analysis.vulnerability import spatial_scenario
from backend.analysis.planning import PROJECT,gap_grid,grid_sites
from backend.services import station_labels,transit,planning,real_data
def test_gap_recovery_denominator_and_boundaries():
    x,y=PROJECT(127,37.5);clip=box(x-2000,y-2000,x+2000,y+2000)
    result,_=spatial_scenario(((37.5,127),),(("A",37.503,127,333),),to_wkb(clip))
    assert result["uncovered_area_m2"]==clip.area-result["baseline_area_m2"]
    assert result["uncovered_recovery_ratio"]==result["added_area_m2"]/result["uncovered_area_m2"]

def test_station_label_collision_is_lossless(monkeypatch):
    monkeypatch.setattr(transit,"station_master",lambda *a:[{"station_id":s} for s in ("SJ-00045","SJ_00045","SJ-00692")])
    ids=station_labels.display_ids()
    assert len(set(ids.values()))==3
    assert ids["SJ-00692"]=="SJ_00692" and ids["SJ-00045"]=="SJ_00045_H"

def test_gap_grid_is_actual_difference():
    x,y=PROJECT(127,37.5);boundary=box(x-1000,y-1000,x+1000,y+1000);baseline=Point(x,y).buffer(500)
    features=gap_grid(boundary,baseline)["features"]
    assert features and all(f["properties"]["grid_size_m"]==500 for f in features)
    assert all(f["properties"]["gap_area_m2"]>0 for f in features)

def test_sejong_candidates_exclude_city_constant_population():
    x,y=PROJECT(127,37.5);clip=box(x-1200,y-1200,x+1200,y+1200)
    rows=grid_sites(clip,Point(x,y).buffer(200),[{"coordinate_valid":True,"latitude":37.5,"longitude":127,"rental_count":20}],[],[{"name":"세종","geometry":clip,"population_density_km2":100}],use_population=False)
    assert rows and all(r["population_density_km2"] is None for r in rows)
    assert all("population_density_km2" not in r["score_components"] for r in rows)
