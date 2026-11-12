"""Fixtures for unified presentation; never loaded by application code."""
from backend.services import all_regions as a

def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(a, "PROCESSED", tmp_path, raising=False)
    monkeypatch.setattr(a.data, "source_meta", lambda rid: {"sources":[]})
    monkeypatch.setattr(a.data, "observed_dates", lambda rid: {
        "seoul":["2026-10-01","2026-10-31"],
        "daejeon":["2026-09-01","2026-10-31"], "sejong":[]}[rid])

def test_unified_common_period_and_annual_exclusion(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    calls = []
    def overview(rid, start=None, end=None):
        calls.append((rid,start,end))
        total = {"seoul":10, "daejeon":20, "sejong":None}[rid]
        return {"region_id":rid, "region_name":a.NAMES[rid], "total_rentals":total,
                "station_count":1 if total else None, "map_stations":[],
                "daily":[{"date":"2026-10-01","rental_count":total}] if total else [],
                "hourly":[total]+[0]*23 if total else None,
                "annual_latest":{"year":2025,"rental_count":1000} if rid=="sejong" else None}
    monkeypatch.setattr(a.data, "overview", overview)
    result = a.projection("overview", 123)
    assert result["total_rentals"] == 30
    assert result["station_count"] == 2
    assert result["hourly"][0] == 30
    assert result["annual_separate"][0]["rental_count"] == 1000
    assert all(start=="2026-10-01" and end=="2026-10-31" for _,start,end in calls)

def test_station_identity_and_no_invented_intercity_edges(monkeypatch, tmp_path):
    setup(monkeypatch,tmp_path)
    monkeypatch.setattr(a.data, "snapshot", lambda: {"stations":[
        {"region_id":rid,"station_id":"S1","station_name":rid,"latitude":36,"longitude":127}
        for rid in ("seoul","daejeon")]})
    monkeypatch.setattr(a.data, "aggregated_od", lambda rid,*args: [] if rid=="sejong" else [
        {"origin_station_id":"S1","destination_station_id":"S1","trip_count":5}])
    stations, edges = a.graph_data()
    assert {s["station_id"] for s in stations} == {"seoul::S1","daejeon::S1"}
    assert all(e["origin_station_id"].split("::")[0] == e["destination_station_id"].split("::")[0] for e in edges)
    assert sum(e["trip_count"] for e in edges) == 10

def test_no_common_period(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    monkeypatch.setattr(a.data,"observed_dates",lambda rid: {"seoul":["2026-01-01"],"daejeon":["2026-02-01"],"sejong":[]}[rid])
    assert a.scope() == (None,None)
    assert a.station_rows() == []
