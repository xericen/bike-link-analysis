"""Offline review checks: no inferred transfers, no double counting, route and text provenance."""
import json,time
from pathlib import Path
from backend.services import precomputed,decision_evidence,periods
from backend.agents.decision_checks import check
ROOT=Path(__file__).resolve().parents[2]
def run():
    data=json.loads(decision_evidence.FILE.read_text())
    assert data["revision"]==precomputed.revision()
    t=data["transfer_audit"]
    assert t["actual_transfer_rate"] is None and t["definition_status"]=="unverified"
    assert sum(r["count"] for r in t["cross_tab"])==t["row_count"]==259143
    rows=[]
    before=json.loads((ROOT/"data/processed/research/goal-before.json").read_text())
    for city,old in before.items():
        now=precomputed.read("transit_linkage",city,*periods.resolve(city,None,None))["goal_metrics"]
        assert all(now[k]==v for k,v in old.items()),city
    for city,p in data["profiles"].items():
        total=sum(r["potential_added_area_m2"] for r in p["top3"])
        union=p["top3_union"]
        assert abs(total-union["added_area_m2"]-union["overlap_area_m2"])<1e-5
        assert set(union["selected_ids"])=={r["site_id"] for r in p["top3"]}
        for r in p["route_audit"]:
            for route in r["routes"].values():
                if route["status"]!="ok":assert "distance_rank" not in route
        start=time.perf_counter()
        v=decision_evidence.read(city,p["period_start"],p["period_end"])
        duration=time.perf_counter()-start
        assert v["matches_selected_period"]
        rows.append({"city":city,"seconds":duration,"union_added_m2":union["added_area_m2"],"overlap_m2":union["overlap_area_m2"]})
    live=json.loads((ROOT/"docs/decision-browser-20261117.json").read_text())["solar"]
    replay=check(live.get("solar_answer") or live["answer"],live["evidence"])
    assert not replay["passed"],replay
    result={"revision":data["revision"],"profiles":rows,"primary_metrics_unchanged":True,"transfer_rows":t["row_count"],"route_cases":9,
        "usable_route_cases":sum(all(m["status"]=="ok" for m in r["routes"].values()) for p in data["profiles"].values() for r in p["route_audit"]),
        "live_solar_original_replay":replay,
        "note":"Live Solar original withheld; route-to-candidate association and population assertions now also fail explicit guards."}
    (ROOT/"docs/decision-integrity-20261117.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":run()
