from backend.tests.local_requirements import requires_local_files, requires_local_inputs
"""Production data contract for the explicitly selected common month."""
import sqlite3
from pathlib import Path
from backend.services import periods,precomputed,real_data
START,END="2025-12-01","2025-12-31"
COUNTS={"seoul":1954344,"daejeon":368491,"sejong":164366}
@requires_local_files("data/processed/analysis.sqlite", "data/processed/kpi_cache.sqlite")
def test_every_city_and_all_share_exact_month():
    for city in [*COUNTS,"all"]:
        assert periods.resolve(city)==(START,END)
        b=periods.bounds(city)
        assert (b["min"],b["max"])==(START,END)
@requires_local_files("data/processed/analysis.sqlite", "data/processed/kpi_cache.sqlite")
def test_actual_month_trip_conservation_and_no_january_returns():
    with sqlite3.connect(real_data.database_path().resolve().as_uri()+"?mode=ro",uri=True) as c:
        for city,total in COUNTS.items():
            rental=c.execute("SELECT SUM(rental_count),COUNT(DISTINCT date),MIN(date),MAX(date) FROM station_usage WHERE region_id=?",(city,)).fetchone()
            od=c.execute("SELECT SUM(trip_count),COUNT(DISTINCT date) FROM od_daily WHERE region_id=?",(city,)).fetchone()
            assert rental==(total,31,START,END)
            assert od==(total,31)
@requires_local_files("data/processed/analysis.sqlite", "data/processed/kpi_cache.sqlite")
def test_prepared_all_includes_three_cities_and_weighted_linkage():
    all_value=precomputed.read("overview","all",START,END)
    assert all_value["total_rentals"]==sum(COUNTS.values())
    assert all_value["measured_city_count"]==3
    link=precomputed.read("transit_linkage","all",START,END)
    assert {r["city"] for r in link["cities"]}==set(COUNTS)
    assert link["goal_metrics"]["linked_trip_total"]==sum(COUNTS.values())
    linked=sum(h["linked_count"] for h in link["hourly_station_linkage"])
    assert link["goal_metrics"]["linked_trip_share"]==linked/sum(COUNTS.values())
    plan=precomputed.read("planning","all",START,END)
    assert {r["city"] for r in plan["cities"]}==set(COUNTS)
    assert plan["comparison"]["excluded"]==[]
