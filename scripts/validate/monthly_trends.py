"""Validate separate history, real API/Solar evidence and unchanged baseline files."""
import hashlib,json,math
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.presentation.monthly_trends import read
from backend.agents.solar import run_tool
from backend.services import precomputed,periods
ROOT=Path(__file__).resolve().parents[2]
EXPECTED={"seoul":1954344,"daejeon":368491,"sejong":164366}
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
    return h.hexdigest()
def run():
    report={"common_period":periods.bounds("all"),"cities":{}}
    assert report["common_period"]["min"]=="2025-12-01"
    assert report["common_period"]["max"]=="2025-12-31"
    client=TestClient(app)
    for city,expected in EXPECTED.items():
        data=json.loads((ROOT/"data/reference/monthly_trends"/(city+".json")).read_text())
        assert sum(s["raw_rows"] for s in data["sources"])==sum(m["raw_rows"] for m in data["months"])+data["unassigned_invalid_date_rows"]
        assert len({r["month"] for r in data["months"]})==len(data["months"])
        for month in data["months"]:
            assert month["rental_count"]==month["raw_rows"]-month["excluded_rows"]-month["duplicate_rows"]
            assert month["complete"]==(month["observed_days"]==month["expected_days"])
            assert month["observed_days"]+len(month["missing_dates"])==month["expected_days"]
        result=read(city,2025)
        assert len(result["months"])==12
        dec=next(r for r in result["months"] if r["month"]=="2025-12")
        assert dec["rental_count"]==expected
        old=precomputed.read("vulnerability",city,"2025-12-01","2025-12-31")
        assert [(r["station_id"],r["rental_count"]) for r in dec["top_candidates"]]==[(r["station_id"],r["rental_count"]) for r in old["ranking"][:3]]
        raw_dec=next(m for m in data["months"] if m["month"]=="2025-12")
        assert raw_dec["candidate_count"]==old["candidate_count"]
        for new_row,old_row in zip(raw_dec["top_candidates"],old["ranking"]):
            assert new_row["station_id"]==old_row["station_id"]
            assert math.isclose(new_row["score"],old_row["score"],rel_tol=0,abs_tol=1e-12)
        linkage=precomputed.read("transit_linkage",city,"2025-12-01","2025-12-31")
        assert dec["anchor_linked_trips"]==sum(r["linked_count"] for r in linkage["hourly_station_linkage"])
        response=client.get("/api/regions/"+city+"/monthly-trends?year=2025")
        assert response.status_code==200 and response.json()["months"]==result["months"]
        context={"region_ids":[city],"date_start":"2025-12-01","date_end":"2025-12-31"}
        solar=run_tool("get_city_monthly_trends",{"region_id":city,"year":2025},context)
        assert solar["months"]==result["months"] and solar["scope"]=="single_city_longitudinal"
        assert solar["period_start"]=="2025-01-01" and solar["common_comparison"]["date_start"]=="2025-12-01"
        report["cities"][city]={"available_start":data["period_start"],"available_end":data["period_end"],"month_count":len(data["months"]),
             "valid_rentals":sum(m["rental_count"] for m in data["months"]),"year_2025_rentals":sum(m["rental_count"] for m in result["months"]),
             "eligible_2025_months":result["eligible_months"],"december_rentals":expected,"december_candidates_match":True,"december_linkage_match":True,
             "missing_2025_dates":{m["month"]:m["missing_dates"] for m in result["months"] if not m["complete"]},
             "api_and_solar_match":True,"reference_sha256":sha(ROOT/"data/reference/monthly_trends"/(city+".json"))}
    before=Path("/tmp/bike-longitudinal-before.json")
    report["preserved_files"]={}
    if before.exists():
        for filename,digest in json.loads(before.read_text()).items():
            actual=sha(ROOT/"data/processed"/filename)
            assert actual==digest,(filename,"baseline changed")
            report["preserved_files"][filename]=actual
    assert read("all")["scope"]=="common_comparison"
    assert read("all")["summary"]["rental_count"]==2487201
    assert len(read("all")["months"])==3
    assert client.get("/api/regions/all/monthly-trends").status_code==200
    return report
if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
