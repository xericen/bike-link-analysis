"""Export verified prepared views as static assets for 웹/React; no live API cache dependency."""
import json,hashlib
from pathlib import Path
from backend.presentation.monthly_trends import read
ROOT=Path(__file__).resolve().parents[2]
def export():
    targets=[ROOT/"frontend/public/assets/bike-link/usage"]
    hashes={}
    for city in ("all","seoul","daejeon","sejong"):
        full=read(city)
        if not full.get("available"):raise RuntimeError("Monthly evidence missing: "+city)
        views={"all":full}
        if city!="all":
            views.update({str(year):read(city,year) for year in full["years"]})
        payload={"schema":1,"region_id":city,"views":views}
        raw=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
        hashes[city]={"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"months":len(full["months"])}
        for target in targets:
            target.mkdir(parents=True,exist_ok=True)
            path=target/(city+".json");tmp=path.with_suffix(".tmp");tmp.write_bytes(raw);tmp.replace(path)
    print(json.dumps(hashes,ensure_ascii=False,indent=2))
if __name__=="__main__":export()
