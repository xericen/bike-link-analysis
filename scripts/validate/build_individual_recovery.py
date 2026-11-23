"""Full-history, whole-city exploration per city. Common December artifacts remain untouched."""
import csv,json,time
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from sklearn.neighbors import BallTree
from backend.research import recovery_breadth as b,recovery_evaluation as e,method_validation as m
from scripts.validate.audit_recovery_breadth import label

OUT=m.ROOT/"docs/recovery-individual-20261123"
def save(path,data):
    if path.exists():raise FileExistsError(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False))
def run():
    scopes=json.loads((m.ROOT/"data/reference/individual_scopes.json").read_text())["cities"]
    inputs=json.loads((b.OUT/"inputs.json").read_text())
    for rel,v in inputs.items():
        p=m.ROOT/rel;s=p.stat()
        assert (s.st_size,s.st_mtime_ns)==(v["size"],v["mtime_ns"])
        if p.suffix!=".sqlite":assert m.sha(p)==v["sha256"]
    for path in (Path(__file__),m.ROOT/"data/reference/individual_scopes.json"):
        s=path.stat();inputs[str(path.relative_to(m.ROOT))]={"size":s.st_size,"mtime_ns":s.st_mtime_ns,"sha256":m.sha(path)}
    save(OUT/"protocol.json",{"created_at":datetime.now(timezone.utc).isoformat(),"scopes":{city:{"start":s["start"],"end":s["end"]} for city,s in scopes.items()},
        "purpose":"Per-city whole-period exploratory comparison, not validation on unseen data. All-city common December results remain separate.",
        "config_count":len(b.CONFIGS),"all_districts_in_official_boundary":True,"operational_update":False})
    save(OUT/"inputs.json",inputs)
    report={"scope":"individual_full","cities":{},"built_at":datetime.now(timezone.utc).isoformat()}
    checks=0
    for city in m.CITIES:
        scope=scopes[city];started=time.perf_counter()
        data=e.load(city,scope["start"],scope["end"])
        assert data[-1]["trips"]==scope["rental_count"],(city,data[-1]["trips"],scope["rental_count"])
        specs=b.specifications(data,"development")
        rows=[]
        for spec in specs:
            print(city,scope["start"],scope["end"],spec["name"],flush=True)
            f=b.fold(city,data,spec)
            remaining=[s for s in data[1] if s.get("coordinate_valid") and s["station_id"] not in f["hidden_ids"]]
            tree=BallTree(np.radians([[s["latitude"],s["longitude"]] for s in remaining]),metric="haversine")
            for key,v in f["methods"].items():
                top=v["top"]
                if top:
                    d=tree.query(np.radians([[p["latitude"],p["longitude"]] for p in top]),k=1)[0][:,0]*m.EARTH_M
                    assert d.min()>(300 if key in b.STRICT else 50)
                for k,match in v["matches"].items():
                    actual=m.geographic_matches(f["targets"],top[:int(k)])
                    assert actual["hits"]==match["hits"]
                    assert len({p["site_id"] for p in match["pairs"]})==match["hits"]
                    assert len({p["station_id"] for p in match["pairs"]})==match["hits"]
                    checks+=1
            rows.append(f)
        f=rows[0]
        strict=max(b.STRICT,key=lambda k:f["methods"][k]["matches"]["10"]["hits"])
        diag=max(b.DIAGNOSTIC,key=lambda k:f["methods"][k]["matches"]["10"]["hits"])
        def item(key):
            v=f["methods"][key]
            return {"method":key,"label":label(key),"hits":v["matches"]["10"]["hits"],
                    "target_count":f["target_count"],"possible":v["generation_possible"]}
        summary={"city":city,"period_start":scope["start"],"period_end":scope["end"],
                 "trips":data[-1]["trips"],"observed_days":data[-1]["observed_days"],
                 "whole_city":True,"baseline":item("legacy500:original"),"strict":item(strict),"diagnostic":item(diag),
                 "cohorts":[{"name":r["name"],"n":r["target_count"]} for r in rows],
                 "scope_note":"보유 전체 기간·도시 전역의 탐색 결과. 독립 검증 성공/설치 효과를 뜻하지 않습니다."}
        city_data={"summary":summary,"info":data[-1],"folds":rows,"seconds":time.perf_counter()-started}
        save(OUT/(city+".json"),city_data);report["cities"][city]=summary
        print(city,"completed",summary["baseline"]["hits"],summary["strict"]["hits"],summary["diagnostic"]["hits"],flush=True)
    for rel,v in inputs.items():
        p=m.ROOT/rel;s=p.stat()
        assert (s.st_size,s.st_mtime_ns)==(v["size"],v["mtime_ns"])
    save(OUT/"summary.json",report)
    save(OUT/"audit.json",{"passed":True,"matching_checks":checks,"input_metadata_unchanged":True,"operational_update":False,
        "artifacts":{name:m.sha(OUT/name) for name in ("summary.json","inputs.json","protocol.json")}})
if __name__=="__main__":run()
