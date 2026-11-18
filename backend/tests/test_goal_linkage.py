"""Goal KPIs use exact boundaries and weighted trip counts, with missing-data safety."""
from backend.services.goal_linkage import summarize
from backend.agents.solar import run_tool

def test_exact_boundaries_and_weighted_share():
    rows=[{"coordinate_valid":True,"nearest_stop_distance_m":500.00001,"nearest_subway_distance_m":300.00001,"rental_count":7},
          {"coordinate_valid":True,"nearest_stop_distance_m":500,"nearest_subway_distance_m":300,"rental_count":4},
          {"coordinate_valid":False,"rental_count":100}]
    result=summarize({"stations":rows,"hourly_station_linkage":[
        {"total_count":10,"linked_count":5},{"total_count":90,"linked_count":9}]})
    assert result["goal_metrics"]["subway_300m_ratio"]==.5
    assert result["goal_metrics"]["outside_500m_active_count"]==1
    assert result["goal_metrics"]["linked_trip_share"]==.14

def test_missing_coordinates_are_not_zero():
    result=summarize({"stations":[{"coordinate_valid":False}],"hourly_station_linkage":None})
    assert result["goal_metrics"]["subway_300m_ratio"] is None
    assert result["goal_metrics"]["outside_500m_active_count"] is None
    assert result["goal_metrics"]["linked_trip_share"] is None

def test_hourly_tool_reads_only_precomputed(monkeypatch):
    from backend.services import precomputed,periods
    monkeypatch.setattr(periods,"resolve",lambda *a:("2026-10-01","2026-10-31"))
    monkeypatch.setattr(precomputed,"read",lambda *a:{"hourly_station_linkage":[{"hour":17,"total_count":10,"linked_count":3,"linkage_share":.3}]})
    result=run_tool("get_transit_linkage",{"region_id":"seoul"})
    assert result["available"] and result["hourly_station_linkage"][0]["linked_count"]==3

def test_anchor_missing_never_falls_back_to_zero_or_all_bus_distance():
    rows=[{"coordinate_valid":True,"nearest_stop_distance_m":0,"nearest_anchor_distance_m":None},
          {"coordinate_valid":True,"nearest_stop_distance_m":0},
          {"coordinate_valid":True,"nearest_stop_distance_m":1000,"nearest_anchor_distance_m":600},
          {"coordinate_valid":True,"nearest_stop_distance_m":0,"nearest_anchor_distance_m":0}]
    value=summarize({"stations":rows,"anchor_label":"BRT"})["goal_metrics"]
    assert value["anchor_300m_ratio"]==.5
    assert value["anchor_300m_denominator_count"]==2
    assert value["anchor_distance_missing_or_invalid_count"]==2

def test_anchor_nan_infinite_negative_boolean_and_string_are_excluded():
    invalid=[None,float("nan"),float("inf"),-1,False,"0"]
    rows=[{"coordinate_valid":True,"nearest_stop_distance_m":0,"nearest_anchor_distance_m":d} for d in invalid]
    value=summarize({"stations":rows,"anchor_label":"지하철"})["goal_metrics"]
    assert value["anchor_300m_ratio"] is None
    assert value["anchor_300m_denominator_count"]==0
    assert value["subway_300m_ratio"] is None

def test_valid_anchor_population_is_independent_of_auxiliary_bus_distance():
    rows=[{"coordinate_valid":True,"nearest_stop_distance_m":None,"nearest_anchor_distance_m":300},
          {"coordinate_valid":True,"nearest_stop_distance_m":0,"nearest_anchor_distance_m":300.000001},
          {"coordinate_valid":False,"nearest_stop_distance_m":0,"nearest_anchor_distance_m":0}]
    value=summarize({"stations":rows,"anchor_label":"지하철"})["goal_metrics"]
    assert value["anchor_300m_ratio"]==.5 and value["anchor_300m_denominator_count"]==2
