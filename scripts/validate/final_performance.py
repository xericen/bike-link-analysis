"""Current-run cold/warm comparison with real data through FastAPI TestClient."""
import json,time,inspect
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.services import real_data as d

client=TestClient(app)
saved={name:fn for name,fn in vars(d).items() if inspect.isfunction(fn) and fn.__module__==d.__name__ and hasattr(fn,"__wrapped__")}
# functools.lru_cache wrappers may not satisfy isfunction.
saved.update({name:fn for name,fn in vars(d).items() if callable(fn) and getattr(fn,"__module__",None)==d.__name__ and hasattr(fn,"__wrapped__")})
output={"run_date":"2026-11-12","method":"FastAPI TestClient wall time; cold bypasses all real_data memo/disk decorators, warm restores and primes them; no network latency included","rows":[]}
for endpoint in ("overview","network"):
    url="/api/regions/seoul/"+endpoint+"?date_start=2026-10-25&date_end=2026-10-31"
    try:
        for name,fn in saved.items():setattr(d,name,fn.__wrapped__)
        t=time.perf_counter();cold=client.get(url);cold_s=time.perf_counter()-t
    finally:
        for name,fn in saved.items():setattr(d,name,fn)
    ready=client.get(url)
    t=time.perf_counter();warm=client.get(url);warm_s=time.perf_counter()-t
    assert cold.status_code==warm.status_code==200
    assert cold.json()==warm.json()
    row={"endpoint":url,"cold_seconds":round(cold_s,4),"warm_seconds":round(warm_s,4),"values_equal":True}
    output["rows"].append(row);print(row,flush=True)
Path("docs/final-validation/performance.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
