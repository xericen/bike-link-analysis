"""Exactly one optional paid chat request; never run without --live."""
import argparse,json,time
from pathlib import Path
import requests
parser=argparse.ArgumentParser(__doc__);parser.add_argument("--live",action="store_true")
args=parser.parse_args()
if not args.live:parser.error("Use --live only when a real Solar request is intended.")
started=time.perf_counter()
response=requests.post("http://localhost:3000/bike-link-ui/api/agent/chat",json={
    "message":"get_method_validation 도구로 서울2025년12월 검증만 확인해줘. 원래 이용량 상위10곳 가림의 복구 수와 대중교통높음·자전거낮음 역수를 각각 한 문장으로 알려줘. 방법이 검증에 성공했다고 과장하지 마.",
    "context":{"region_ids":["seoul"],"date_start":"2025-12-01","date_end":"2025-12-31"}},
    timeout=100)
result=response.json()
evidence=[e for e in result.get("evidence",[]) if e["tool"]=="get_method_validation"]
checks={"http_200":response.status_code==200,"new_tool_called":bool(evidence)}
if evidence:
    r=evidence[0]["result"]
    checks.update(period_match=r.get("period_start")=="2025-12-01" and r.get("period_end")=="2025-12-31",
                  matrix_count_matches=r.get("matrix",{}).get("counts",{}).get("high_low")==42,
                  zero_recovery_preserved=any(x["fold"]=="high_usage" and x["hits"]==0 for x in r.get("original_recovery",[])),
                  source_present=bool(r.get("sources")))
out={"seconds":time.perf_counter()-started,"http_status":response.status_code,"checks":checks,
     "response":result,"note":"Single real model request; checks validate tool facts, not all free-prose semantics."}
folder=Path("docs/validation-followup-20261123");folder.mkdir(exist_ok=True)
(folder/"solar.json").write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({"status":response.status_code,"checks":checks,"usage":result.get("usage"),
                  "answer_basis":result.get("answer_basis"),"seconds":out["seconds"]},ensure_ascii=False))
