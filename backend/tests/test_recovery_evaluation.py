"""Synthetic fixtures only; never presented as observed validation evidence."""
import copy
import pytest
from shapely.geometry import box
from backend.research import recovery_evaluation as e, method_validation as m

def station(sid, x=0, y=0, count=10):
    a,b=m.PROJECT(127,37.5)
    lon,lat=m.UNPROJECT(a+x,b+y)
    return {"station_id":sid,"station_name":sid,"latitude":lat,"longitude":lon,
            "rental_count":count,"return_count":0,"coordinate_valid":True,
            "nearest_anchor_distance_m":1000}

def test_loss_diagnostics_separate_generation_and_ranking_without_counting_nearby_as_hits():
    target=station("a")
    rows=[{**station(str(i),1000+i*10),"site_id":str(i)} for i in range(10)]
    rows.append({**station("near",1),"site_id":"near"})
    original=copy.deepcopy(rows)
    result=e.diagnose([target], rows, [])
    assert result[0]["stage"]=="rank_below_top10"
    assert result[0]["best_individual_rank_within_300m"]==11
    assert e.metrics([target],rows)["at_k"]["10"]["hits"]==0
    assert e.metrics([target],rows)["at_k"]["20"]["hits"]==1
    assert rows==original
    missing=e.diagnose([station("far",5000)],rows,[])[0]
    assert missing["stage"]=="no_candidate"

def test_one_proposal_cannot_recover_two_targets_and_empty_denominators_remain_null():
    targets=[station("a"),station("b",10)]
    proposals=[{**station("p",5),"site_id":"p"}]
    result=e.metrics(targets,proposals)
    assert result["at_k"]["10"]["hits"]==1
    assert result["precision_at10"]==1
    empty=e.metrics(targets,[])
    assert empty["precision_at10"] is None and empty["mean_matched_distance_m"] is None

def test_selection_uses_only_development_scores_and_ties_prefer_original():
    keys=[f"{step}:{policy}" for step in e.STEPS for policy in e.POLICIES]
    configs={k:{"at_k":{"10":{"recall":0}}} for k in keys}
    chosen,_=e.select_config([{"configs":configs}])
    assert chosen=="500:equal"
    configs["250:demand"]["at_k"]["10"]["recall"]=0.5
    assert e.select_config([{"configs":configs}])[0]=="250:demand"

def test_simple_demand_baseline_and_facilities_are_distinct():
    rows=[{"site_id":"a","nearby_rentals_1000m":1,
           "score_components":{"facilities_within_500m":0.9,"population_density_km2":0.9}},
          {"site_id":"b","nearby_rentals_1000m":100,
           "score_components":{"facilities_within_500m":0.1,"population_density_km2":0.1}}]
    assert e.ranked(rows,"demand","seoul")[0]["site_id"]=="b"
    assert e.ranked(rows,"facilities_only","seoul")[0]["site_id"]=="a"

def test_spatial_fold_removes_even_inactive_master_sites_and_test_ids_are_disjoint():
    rows=[station("a",0,0),station("inactive",1,1,0),station("b",5000,5000)]
    x,y=m.PROJECT(127,37.5);boundary=box(x-10000,y-10000,x+10000,y+10000)
    dev,_=e.folds(rows,boundary,"development")
    spatial=next(f for f in dev if f["name"]=="spatial_block")
    assert "inactive" in spatial["hidden_ids"]
    assert "inactive" not in [r["station_id"] for r in spatial["targets"]]
    test,_=e.folds(rows,boundary,"evaluation",spatial["hidden_ids"],spatial["block"])
    assert all(not set(f["hidden_ids"])&set(spatial["hidden_ids"]) for f in test)
    if any(f["name"]=="spatial_block" for f in test):
        import math
        assert math.dist(spatial["block"],next(f["block"] for f in test if f["name"]=="spatial_block"))>=2

def test_hidden_od_removed_in_research_and_target_demand_not_reused():
    rows=[station("hidden",count=999),station("kept")]
    od=[{"origin_station_id":"hidden","destination_station_id":"kept","trip_count":50},
        {"origin_station_id":"kept","destination_station_id":"kept","trip_count":3}]
    training,audit=m.retain_training(rows,od,["hidden"])
    assert training[0]["rental_count"]==3
    assert audit["removed_od_trips"]==50
