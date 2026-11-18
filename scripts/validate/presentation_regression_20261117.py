"""Read-only KPI/cache regression and replay of two recorded live Solar answers."""
import json,hashlib,re,urllib.request
from pathlib import Path
from backend.presentation.anchors import scope_answer
from backend.services import precomputed
root=Path("docs")
baseline=json.loads((root/"anchor_presentation_context.json").read_text())
report={"combinations":[],"http":[]}
assert precomputed.revision()==baseline["revision"]
assert hashlib.sha256(precomputed.path().read_bytes()).hexdigest()==baseline["cache_sha256"]
for key,before in baseline["kpi_baseline"].items():
    city,start,end=key.split("|")
    link=precomputed.read("transit_linkage",city,start,end);v=precomputed.read("vulnerability",city,start,end)
    after={"goal_metrics":link.get("goal_metrics"),"candidate_count":v.get("candidate_count"),"scenario":v.get("scenario"),
        "city_scenarios":[{"city":r["city"],"scenario":r.get("scenario")} for r in v.get("cities",[])]}
    assert before==after,key
    report["combinations"].append({"key":key,"unchanged":True})
for city,start in [("seoul","2026-10-01"),("daejeon","2026-10-01"),("sejong","2025-10-01")]:
    end=start[:8]+"31";key="|".join((city,start,end))
    for endpoint,field in [("presentation-context",None),("transit-linkage","goal_metrics"),("vulnerability","candidate_count")]:
        with urllib.request.urlopen(f"http://127.0.0.1:8188/api/{endpoint}?city={city}&date_start={start}&date_end={end}") as r:
            value=json.load(r);assert r.status==200
        if field:assert value[field]==baseline["kpi_baseline"][key][field]
        else:assert value==baseline["contexts"][key]
        report["http"].append({"city":city,"endpoint":endpoint,"status":200,"unchanged":True})
report["revision_unchanged"]=True;report["cache_bytes_unchanged"]=True
report["cache_sha256"]=baseline["cache_sha256"]
report["kpi_october"]={k:v for k,v in baseline["kpi_baseline"].items() if k in ["seoul|2026-10-01|2026-10-31","daejeon|2026-10-01|2026-10-31","sejong|2025-10-01|2025-10-31"]}
(root/"presentation-regression-20261117.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
original=json.loads((root/"presentation-browser-live-20261117.json").read_text())
replay={"method":"Recorded actual provider answers replayed through final presentation helper; no additional provider calls.","answers":[]}
for entry in original["solar"]:
    r=entry["response"];before=r["answer"];after=scope_answer(before,r["evidence"])
    assert re.findall(r"[0-9]+(?:[.,][0-9]+)*",before)==re.findall(r"[0-9]+(?:[.,][0-9]+)*",after)
    assert ("BRT 정류장" if entry["city"]=="sejong" else "지하철역") in after
    assert "상위 5곳 중 최대 수요는" not in after
    replay["answers"].append({"city":entry["city"],"original":before,"after":after,"numeric_tokens_unchanged":True})
(root/"presentation-answer-replay-20261117.json").write_text(json.dumps(replay,ensure_ascii=False,indent=2))
print(json.dumps({"combinations":len(report["combinations"]),"http_checks":len(report["http"]),"cache_bytes_unchanged":True,"answer_replays":len(replay["answers"])},ensure_ascii=False))
