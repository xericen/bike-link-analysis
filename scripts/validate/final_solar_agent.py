"""Three bounded live questions, autonomous tool choice and provenance audit."""
import argparse,json,time
from pathlib import Path
import requests
from backend.presentation.individual import scope
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/final-validation-20261123"
def run():
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    for city,name in (("seoul","서울"),("daejeon","대전"),("sejong","세종")):
        path=OUT/("solar-"+city+".json")
        if path.exists():rows.append(json.loads(path.read_text()));continue
        s=scope(city);question=f"{name}의 보유 전체기간 분석 결론에서 신규 후보의 연결 경로가 확인됐는지, 시간상 유리한 후보와 한계를 알려줘. 실제 분석 자료를 확인하고 후보 ID와 관측기간을 함께 써줘."
        started=time.perf_counter()
        try:
            response=requests.post("http://localhost:3000/bike-link-ui/api/agent/chat",
              json={"message":question,"context":{"region_ids":[city],"date_start":s["start"],"date_end":s["end"]}},timeout=150)
            body=response.json();ev=body.get("evidence",[]);chosen=[e for e in ev if e.get("initiator")=="solar"]
            conclusion=[e for e in chosen if e.get("tool")=="get_project_conclusion"]
            selected_ids={r["site_id"] for e in conclusion for c in e.get("result",{}).get("cities",[]) for r in c.get("candidates",[])}
            answer=body.get("answer",body.get("report",body.get("message","")))
            if not isinstance(answer,str):answer=json.dumps(answer,ensure_ascii=False)
            checks={"http_200":response.status_code==200,"autonomous_tool_selected":bool(chosen),
              "conclusion_tool_selected":bool(conclusion),
              "individual_scope":bool(conclusion) and all(e["result"].get("scope")=="individual_full" for e in conclusion),
              "candidate_id_cited":any(sid in answer for sid in selected_ids),
              "period_cited":s["start"] in answer and s["end"] in answer}
            row={"city":city,"question":question,"seconds":time.perf_counter()-started,"http_status":response.status_code,
              "checks":checks,"response":body,"automatic_free_prose_truth_check":False}
        except (requests.RequestException,ValueError) as e:
            row={"city":city,"error_type":type(e).__name__,"checks":{"http_200":False},"seconds":time.perf_counter()-started}
        path.write_text(json.dumps(row,ensure_ascii=False,indent=2));rows.append(row)
        print(city,row["checks"],flush=True)
    (OUT/"solar.json").write_text(json.dumps({"scenarios":rows,"scenario_count":len(rows),
      "limitations":["도구 이름을 지정하지 않은 실제 질문3개입니다. 작은 표본이며 모든 자유 서술의 사실성을 자동 입증하지 않습니다.",
      "HTTP 성공·모델 도구 선택·결론 도구 선택·기간·후보ID 인용을 각각 구분합니다. 실패를 성공으로 간주하지 않습니다."]},ensure_ascii=False,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--live",action="store_true");a=p.parse_args()
    if not a.live:p.error("실제 유료 Solar 호출은 --live 필요")
    run()
