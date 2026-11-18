"""Offline validation only: recalculate every prepared candidate selection combination."""
import json,hashlib,math,sqlite3,itertools
from pathlib import Path
from shapely.geometry import Point
from shapely.ops import unary_union
from backend.services import precomputed,planning,city_anchors
from backend.analysis.vulnerability import _geometry
from backend.analysis.planning import PROJECT
OUT=Path("docs/chapter-flow-20261118");OUT.mkdir(exist_ok=True)
before=hashlib.sha256(precomputed.path().read_bytes()).hexdigest()
with sqlite3.connect(precomputed.path().resolve().as_uri()+"?mode=ro",uri=True) as c:
 periods=c.execute("select distinct city,start,end from kpi where action='planning' order by city,start").fetchall()
geometry={};checks=[]
for city,start,end in periods:
 if city=="all":continue
 plan=precomputed.read("planning",city,start,end)
 if city not in geometry:
  clip=planning.boundary(city)
  points=tuple(sorted(set((float(s["lat"]),float(s["lon"])) for s in city_anchors.stops() if s["city"]==city)))
  geometry[city]=(clip,_geometry(points).intersection(clip))
 clip,base=geometry[city]
 buffers={r["site_id"]:Point(*PROJECT(r["longitude"],r["latitude"])).buffer(300,quad_segs=16).intersection(clip).difference(base) for r in plan["scenario_pool"]}
 seen=set()
 for state in plan["selection_states"]:
  ids=tuple(state["selected_ids"]);seen.add(ids)
  union=unary_union([buffers[i] for i in ids]);gross=sum(buffers[i].area for i in ids)
  expected={"baseline_area_m2":base.area,"added_area_m2":union.area,"overlap_area_m2":max(0,gross-union.area),
            "linked_area_m2":base.area+union.area,"increase_ratio":union.area/base.area if base.area else None}
  for metric,value in expected.items():
   assert (state[metric] is None and value is None) or math.isclose(state[metric],value,rel_tol=1e-10,abs_tol=0.0001),(city,start,ids,metric,state[metric],value)
 assert len(seen)==2**len(buffers)
 checks.append({"city":city,"start":start,"end":end,"combinations":len(seen),"all_area_metrics_match":True})
assert hashlib.sha256(precomputed.path().read_bytes()).hexdigest()==before
report={"checks":checks,"total_combinations":sum(x["combinations"] for x in checks),"cache_bytes_unchanged":True,"sha256":before,
        "method":"Rebuild exact projected 300m candidate buffers clipped by original boundary minus original anchor500m baseline; union/intersection and overlap compared at full precision with floating tolerance 0.0001m2. Offline validation only."}
(OUT/"scenario-audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({"periods":len(checks),"combinations":report["total_combinations"],"cache_bytes_unchanged":True}))
