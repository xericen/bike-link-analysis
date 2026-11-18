"""Read-only checks of December2025 source -> usage -> OD -> prepared results."""
import json,sqlite3,time
from pathlib import Path
from backend.services import real_data,precomputed,periods
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"data/processed"
START,END="2025-12-01","2025-12-31"
TOTALS={"seoul":1954344,"daejeon":368491,"sejong":164366}
def run():
    report=json.loads((OUT/"common_period_validation.json").read_text())
    checks=[];city_metrics={}
    with sqlite3.connect(real_data.database_path().resolve().as_uri()+"?mode=ro",uri=True) as c:
        for city,total in TOTALS.items():
            assert periods.resolve(city)==(START,END)
            rentals=dict(c.execute("SELECT date,SUM(rental_count) FROM station_usage WHERE region_id=? GROUP BY date",(city,)))
            od=dict(c.execute("SELECT date,SUM(trip_count) FROM od_daily WHERE region_id=? GROUP BY date",(city,)))
            assert rentals==od and len(rentals)==31 and sum(rentals.values())==total
            for day,n in sorted(rentals.items()):checks.append({"region_id":city,"date":day,"station_rentals":n,"od_flow":od[day],"trip_rows":n,"rental_vs_od_match":True})
            overview=precomputed.read("overview",city,START,END)
            linkage=precomputed.read("transit_linkage",city,START,END)
            assert overview["total_rentals"]==total
            assert linkage["goal_metrics"]["linked_trip_total"]==total
            plan=precomputed.read("planning",city,START,END)
            assert plan["available"] and len(plan["new_sites"])>=3
            ids={r["site_id"] for r in plan["new_sites"][:3]}
            union=next(s for s in plan["selection_states"] if set(s["selected_ids"])==ids)
            summed=sum(r["potential_added_area_m2"] for r in plan["new_sites"][:3])
            assert abs(summed-union["added_area_m2"]-union["overlap_area_m2"])<1e-5
            began=time.perf_counter();precomputed.read("vulnerability",city,START,END);seconds=time.perf_counter()-began
            city_metrics[city]={"rentals":total,"station_count":overview["station_count"],"goal_metrics":linkage["goal_metrics"],"candidate_count":precomputed.read("vulnerability",city,START,END)["candidate_count"],"top3_union_added_m2":union["added_area_m2"],"read_seconds":seconds}
    assert periods.resolve("all")==(START,END)
    all_value=precomputed.read("overview","all",START,END)
    assert all_value["total_rentals"]==sum(TOTALS.values()) and all_value["measured_city_count"]==3
    link=precomputed.read("transit_linkage","all",START,END)
    assert {c["city"] for c in link["cities"]}==set(TOTALS)
    assert link["goal_metrics"]["linked_trip_total"]==sum(TOTALS.values())
    plan=precomputed.read("planning","all",START,END)
    assert {c["city"] for c in plan["cities"]}==set(TOTALS) and plan["comparison"]["excluded"]==[]
    network=precomputed.read("network","all",START,END)
    assert all(r["origin_station_id"].split("::")[0]==r["destination_station_id"].split("::")[0] for r in network["edges"])
    seoul=next(c for c in report["cities"] if c["city"]=="seoul")
    dj=next(c for c in report["cities"] if c["city"]=="daejeon")
    value={"revision":precomputed.revision(),"period_start":START,"period_end":END,"metrics":city_metrics,
      "seoul":{"od_station_ids":seoul["station_ids"],"inventory_located_ids":seoul["located_station_ids"],"id_matches":seoul["located_station_ids"],"id_match_rate":seoul["located_station_ids"]/seoul["station_ids"],"unmatched_id_count":seoul["station_ids"]-seoul["located_station_ids"],"unmatched_ids":[s["station_id"] for s in real_data.snapshot()["stations"] if s["region_id"]=="seoul" and s["latitude"] is None],"coordinate_link_status":"official number crosswalk / exact ST lookup; unknown retained"},
      "daejeon":{"trip_rows":dj["raw_rows"],"possible_duplicate_rows":dj["duplicate_rows"],"invalid_or_reversed_times":dj.get("invalid_time_or_duration",0),"negative_or_invalid_durations":dj.get("invalid_time_or_duration",0),"missing_trip_id_count":dj.get("missing_endpoint_id",0)},
      "common":{"all_rental_od_totals_match":True,"by_date":checks},"all_total_rentals":all_value["total_rentals"],"all_city_count":3}
    (OUT/"research/common_period_checks.json").write_text(json.dumps(value,ensure_ascii=False,indent=2))
    (ROOT/"docs/common-december-validation-20261118.json").write_text(json.dumps(value,ensure_ascii=False,indent=2))
    print(json.dumps({"period":[START,END],"total":all_value["total_rentals"],"metrics":city_metrics},ensure_ascii=False))
if __name__=="__main__":run()
