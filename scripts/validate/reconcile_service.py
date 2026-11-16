"""Independent SQLite arithmetic audit. Compare pre-rounded versus full-precision selection."""
import json,sqlite3
from collections import defaultdict
from pathlib import Path
import numpy as np
from backend.services import real_data
def recalculate(start="2026-10-01",end="2026-10-31"):
    names={s["station_id"]:s.get("station_name") for s in real_data.snapshot()["stations"] if s["region_id"]=="seoul"}
    flows=defaultdict(list)
    with sqlite3.connect(real_data.database_path()) as c:
        for sid,day,a,b in c.execute("SELECT station_id,date,SUM(rental_count),SUM(return_count) FROM station_usage WHERE region_id='seoul' AND date BETWEEN ? AND ? GROUP BY station_id,date",(start,end)):
            flows[sid].append((day,int(a),int(b or 0)))
    values=[]
    for sid,days in flows.items():
        if not names.get(sid):continue
        a=sum(r[1] for r in days);b=sum(r[2] for r in days);total=a+b
        pos=sum(x>y for _,x,y in days);neg=sum(x<y for _,x,y in days)
        values.append({"station_id":sid,"rental_count":a,"return_count":b,"total":total,
            "ratio":(a-b)/total if total else 0,"persistence":max(pos,neg)/len(days) if days else 0})
    floor=float(np.quantile([r["total"] for r in values],.25,method="linear"))
    eligible=[r for r in values if r["total"]>=floor]
    outcomes={}
    for mode in ["rounded_before_selection","full_precision"]:
        ratio=lambda r:abs(round(r["ratio"],4)) if mode=="rounded_before_selection" else abs(r["ratio"])
        persist=lambda r:round(r["persistence"],4) if mode=="rounded_before_selection" else r["persistence"]
        rmin=float(np.quantile([ratio(r) for r in eligible],.9,method="linear"))
        pmin=float(np.quantile([persist(r) for r in eligible],.75,method="linear"))
        chosen=sorted(r["station_id"] for r in eligible if ratio(r)>=rmin and persist(r)>=pmin)
        outcomes[mode]={"count":len(chosen),"station_ids":chosen,"absolute_ratio_min":rmin,"persistence_min":pmin}
    changed=set(outcomes["rounded_before_selection"]["station_ids"])^set(outcomes["full_precision"]["station_ids"])
    return {"period_start":start,"period_end":end,"source":"independent station_usage SQL, numpy linear quantile",
      "minimum_total_volume":floor,"eligible_count":len(eligible),"same_date_filter":True,"outcomes":outcomes,
      "boundary_cases":[r for r in values if r["station_id"] in changed],
      "cause":"ratio and persistence were rounded to 4 decimals BEFORE percentile/candidate decisions; full precision selection removes boundary false positives"}
if __name__=="__main__":
    result=recalculate();out=Path("docs/imbalance_recalculation.json");out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!="outcomes"},ensure_ascii=False))
    print({k:v["count"] for k,v in result["outcomes"].items()})
