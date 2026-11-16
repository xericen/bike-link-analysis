"""Validate real prepared evidence and WIZ latency without recomputing on requests."""
import json,time,urllib.request,urllib.parse
from pathlib import Path
from backend.services import precomputed,periods,deployment,real_data
from backend.agents import solar
from shapely.geometry import shape
from shapely.ops import transform
from backend.analysis.planning import PROJECT
report={"cities":[],"http":[]}
for city in ("seoul","daejeon","sejong"):
 start,end=periods.resolve(city)
 result=precomputed.read("planning",city,start,end)
 assert result["available"] and result["new_sites"]
 assert all(s["nearest_station_distance_m"]>300 for s in result["new_sites"])
 props=result["coverage_features"][0]["properties"]
 assert props["area_error_ratio"]<.01
 assert result["population_basis"].startswith("2026-10")
 assert all(s["recommended_bike_count"] is None for s in result["relocation"]["items"])
 observed=precomputed.read("vulnerability",city,start,end)
 count=observed["candidate_count"]
 assert all(r["score_confidence"]==("insufficient_candidates" if count<5 else "relative_within_city") for r in observed["ranking"])
 states=result["selection_states"]
 assert len(states)==2**len(result["scenario_pool"])
 assert next(s for s in states if not s["selected_ids"])["added_area_m2"]==0
 for s in states:
  assert s["overlap_area_m2"]>=0 and s["added_area_m2"]>=0
 for tool in ("get_site_planning","get_relocation_candidates"):
  tool_result=solar.run_tool(tool,{"region_id":city},context={"region_ids":[city],"date_start":start,"date_end":end})
  assert tool_result["available"]
 report["cities"].append({"city":city,"period":[start,end],"new_site_count":result["new_site_count"],
   "existing_candidates":count,"coverage_unique_locations":result["coverage_all_stop_count"],
   "coverage_area_m2":props["source_area_m2"],"simplification_area_error_ratio":props["area_error_ratio"],
   "facility_count":result["facility_count"],"scenario_combinations":len(states)})
for action in ("planning","transit_vulnerability","readiness"):
 began=time.perf_counter()
 data=urllib.parse.urlencode({"action":action,"region_id":"daejeon"}).encode()
 req=urllib.request.Request("https://project.wizide.com/wiz/api/component.bike.link/handle",data=data)
 with urllib.request.urlopen(req,timeout=30) as response:body=json.load(response)
 elapsed=(time.perf_counter()-began)*1000
 assert body["code"]==200,(action,body)
 report["http"].append({"city":"daejeon","action":action,"milliseconds":elapsed})
assert all(r["milliseconds"]<1000 for r in report["http"] if r["action"]!="readiness")
report["readiness"]=deployment.readiness()
assert report["readiness"]["ready"]
sejong=[s for s in real_data.snapshot()["stations"] if s["region_id"]=="sejong"]
report["sejong_master"]={"station_count":len(sejong),"located_count":sum(s["latitude"] is not None for s in sejong),
 "coordinate_date":"2026-05-26","observation_period":"2025-10","historical_position_verified":False}
Path("docs/transit/planning-validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
