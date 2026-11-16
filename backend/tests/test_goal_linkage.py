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
