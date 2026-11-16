"""Measure current local deployment reads; do not run Solar or analysis."""
import json,sqlite3,time,statistics,urllib.parse,urllib.request
from pathlib import Path
from backend.services import precomputed
from fastapi.testclient import TestClient
from backend.main import app

def measure():
    client=TestClient(app)
    observations=[]
    for city,start,end in [("daejeon","2025-12-01","2026-10-31"),("daejeon","2026-10-01","2026-10-31"),("all","2026-10-01","2026-10-31"),("seoul","2026-10-01","2026-10-31")]:
        for action in precomputed.ACTIONS:
            url=f"/api/precomputed/{city}/{action}?date_start={start}&date_end={end}"
            times=[];values=[]
            for attempt in range(3):
                began=time.perf_counter();response=client.get(url);times.append((time.perf_counter()-began)*1000)
                assert response.status_code==200,(url,response.text)
                values.append(response.json())
            value=values[-1]
            assert all(v["precomputed"]["read_only"] for v in values)
            if city=="seoul" and action=="research":assert value["counts"]["persistent_imbalance"]==207
            if city=="daejeon" and action=="overview":assert value["total_rentals"]==(7605738 if start=="2025-12-01" else 923578)
            observations.append({"city":city,"start":start,"end":end,"action":action,"first_request_ms":round(times[0],3),"repeat_request_ms":[round(x,3) for x in times[1:]],"stored_only":True})
    wiz=[]
    for city in ("daejeon","all"):
        for action in ("overview","research","network","centrality","dashboard_extra"):
            data=urllib.parse.urlencode(dict(action=action,region_id=city,date_start="2026-10-01",date_end="2026-10-31")).encode()
            req=urllib.request.Request("http://localhost:3000/wiz/api/component.bike.link/handle",data=data,headers={"Cookie":"season-wiz-project=main; season-wiz-devmode=true"})
            began=time.perf_counter()
            with urllib.request.urlopen(req,timeout=30) as r:value=json.load(r)
            elapsed=(time.perf_counter()-began)*1000
            assert value["code"]==200 and value["data"]["precomputed"]["read_only"],value
            wiz.append({"city":city,"action":action,"milliseconds":round(elapsed,3)})
    began=time.perf_counter()
    miss=client.get("/api/precomputed/daejeon/research?date_start=2026-10-03&date_end=2026-10-29")
    missms=(time.perf_counter()-began)*1000
    assert miss.status_code==409
    with sqlite3.connect(precomputed.path()) as c:
        count=c.execute("SELECT COUNT(*) FROM kpi WHERE revision=?",(precomputed.revision(),)).fetchone()[0]
    return {"environment":"current local main, not externally deployed","os_cache_not_flushed":True,"first_request":"first per key in this new Python process; not a cold OS disk","entries_current_revision":count,"fastapi_reads":observations,"wiz_http_reads":wiz,"unprepared_period":{"status":409,"milliseconds":round(missms,3)}}
if __name__=="__main__":
    result=measure()
    Path("docs/transit/precomputed-performance-20261116.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
