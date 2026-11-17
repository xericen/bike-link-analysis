"""Actual city-anchor QA. HTTP reads never invoke analysis functions."""
import json,time,sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.services import precomputed,real_data,station_labels
def run():
    client=TestClient(app);cities=[]
    for city,start in (("seoul","2026-10-01"),("daejeon","2026-10-01"),("sejong","2025-10-01")):
        end=start[:8]+"31";query=f"?city={city}&date_start={start}&date_end={end}"
        times={}
        values={}
        for endpoint in ("transit-linkage","vulnerability","planning"):
            samples=[]
            for _ in range(2):
                t=time.perf_counter();response=client.get("/api/"+endpoint+query);samples.append((time.perf_counter()-t)*1000)
                assert response.status_code==200,response.text
                values[endpoint]=response.json()
                assert values[endpoint]["precomputed"]["read_only"]
            times[endpoint]=samples
        link=values["transit-linkage"];v=values["vulnerability"];p=values["planning"]
        assert v["candidate_count"]==link["goal_metrics"]["outside_500m_active_count"]
        assert link["hourly_snapshot_valid"] and link["goal_metrics"]["linked_trip_share"] is not None
        assert all(x["station_id"]!="X" for x in p["relocation"]["items"])
        assert p["gap_grid"]["features"]
        if city=="sejong":
            assert link["goal_metrics"]["linked_trip_total"]==259143
            assert all(r["population_density_km2"] is None for r in p["new_sites"])
        cities.append({"city":city,"period":[start,end],"goal_metrics":link["goal_metrics"],"candidate_count":v["candidate_count"],
            "first_last_mile_count":v["first_last_mile_count"],"scenario":v["scenario"],"ranking":v["ranking"][:3],
            "gap_grid_features":len(p["gap_grid"]["features"]),"new_site_count":p["new_site_count"],
            "population_basis":p["population_basis"],"relocation":p["relocation"],"api_ms":times})
    with sqlite3.connect(real_data.database_path()) as c:
        raw=c.execute("SELECT SUM(rental_count),SUM(return_count),COUNT(*) FROM station_usage WHERE region_id='seoul' AND station_id='X' AND date BETWEEN '2026-10-01' AND '2026-10-31'").fetchone()
    labels=station_labels.display_ids()
    assert len(labels)==len(set(labels.values()))
    assert all(shown.startswith("SJ_") for raw,shown in labels.items() if raw.startswith(("SJ-","SJ_")))
    original_other_ids={k:v for k,v in labels.items() if not k.startswith(("SJ-","SJ_"))}
    with sqlite3.connect(precomputed.path()) as c:
        count=c.execute("SELECT COUNT(*) FROM kpi WHERE revision=?",(precomputed.revision(),)).fetchone()[0]
    return {"environment":"local current main, no actual deployment","cities":cities,
        "unknown_X":{"cause":"raw OD destination ID absent from station master; not a generated total row","rentals":raw[0],"returns":raw[1],"station_hour_rows":raw[2],"excluded_from_relocation":True},
        "sejong_display_ids":{"count":len(labels),"distinct_count":len(set(labels.values())),"raw_preserved":True,"collision_suffix":"_H only for hyphen family collisions",
            "examples":{k:v for k,v in labels.items() if k in ("SJ-00692","SJ-00045","SJ_00045","SJ-00681","SJ_00681","SJ-00682","SJ_00682")}},
        "cached_entries":count}
if __name__=="__main__":
    report=run();Path("docs/transit/city-anchors-validation-20261117.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({**report,"cities":[{k:v for k,v in r.items() if k not in ("relocation","ranking")} for r in report["cities"]]},ensure_ascii=False))
