"""Activate only after all three independent histories and prepared actions validate."""
import hashlib,json,os,shutil
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def export():
    cities={};regions={"all":{"min":"2025-12-01","max":"2025-12-31","available":True}}
    targets=[ROOT/"frontend/public/assets/bike-link/individual"]
    required={"overview","network","centrality","transit_linkage","vulnerability","planning","research","dashboard_extra","clusters","stations","decision_evidence","presentation_context"}
    for city in ("seoul","daejeon","sejong"):
        folder=ROOT/"data/individual"/city;s=json.loads((folder/"analysis_ready.json").read_text())
        if not s.get("algorithm_revision"):raise RuntimeError("Missing algorithm provenance: "+city)
        if not required.issubset(s["actions"]):raise RuntimeError("Missing prepared action: "+city)
        prepared=folder/"prepared"
        overview=json.loads((prepared/"overview.json").read_text())
        assert overview["total_rentals"]==s["rental_count"]
        golden=json.loads((ROOT/"data/reference/monthly_trends"/(city+".json")).read_text())
        assert s["rental_count"]==sum(m["rental_count"] for m in golden["months"])
        for source in golden["source_files"]:
            h=hashlib.sha256()
            with (ROOT/"data/raw"/source["file"]).open("rb") as stream:
                for chunk in iter(lambda:stream.read(4*1024*1024),b""):h.update(chunk)
            assert h.hexdigest()==source["sha256"]
        s["asset_path"]=city+"/"+s["revision"][:12]
        for target in targets:
            dest=target/s["asset_path"];dest.mkdir(parents=True,exist_ok=True)
            for file in prepared.glob("*.json"):
                if file.stem=="imbalance":
                    value=json.loads(file.read_text())
                    for row in value["stations"]:row.pop("daily_net_outflow",None)
                    value["daily_series_omitted"]=True
                    (dest/file.name).write_text(json.dumps(value,ensure_ascii=False,separators=(",",":")))
                else:shutil.copy2(file,dest/file.name)
        cities[city]=s;regions[city]={"min":s["start"],"max":s["end"],"available":True}
    result={"ready":True,"schema":1,"cities":cities,"regions":regions,"common":{"start":"2025-12-01","end":"2025-12-31"},"generated_at":datetime.now(timezone.utc).isoformat()}
    raw=json.dumps(result,ensure_ascii=False,indent=2)
    for target in targets:
        temp=target/"scopes.tmp";temp.write_text(raw);os.replace(temp,target/"scopes.json")
    p=ROOT/"data/reference/individual_scopes.json";temp=p.with_suffix(".tmp");temp.write_text(raw);temp.replace(p)
    print(json.dumps({c:{"start":s["start"],"end":s["end"],"rentals":s["rental_count"],"actions":len(s["actions"])} for c,s in cities.items()},ensure_ascii=False,indent=2))
if __name__=="__main__":export()
