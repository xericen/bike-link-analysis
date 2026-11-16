"""One live Solar request for goal tools; secrets never enter the report."""
import json,time
from pathlib import Path
from dotenv import load_dotenv
from backend.agents import solar
from backend.services import vulnerability,precomputed
load_dotenv(Path(".env"))
context={"region_ids":["seoul"],"date_start":"2026-10-01","date_end":"2026-10-31"}
question="서울 선택 기간의 연계 취약 후보, 확충 우선순위 TOP 1, 역 연계 이동 최다 시간을 확인해줘. get_transit_vulnerability, get_improvement_ranking, get_transit_linkage를 각각 한 번 사용해. 최종 답변은 후보 수, 1위 대여소 ID와 대여 건수, 역 연계 이동 최다 시간과 건수를 다섯 줄 이내로 도구 수치 그대로 인용해. 직선거리 기준 검토 후보이며 실제 환승 효과가 아님을 한 줄 명시해."
began=time.perf_counter()
try:
 result=solar.chat(question,context)
 expected=vulnerability.prepared("seoul",context["date_start"],context["date_end"])
 linked=precomputed.read("transit_linkage","seoul",context["date_start"],context["date_end"])
 peak=max(linked["hourly_station_linkage"],key=lambda r:r["linked_count"])
 used={e["tool"] for e in result.get("evidence",[]) if e.get("initiator")=="solar"}
 tools={"get_transit_vulnerability","get_improvement_ranking","get_transit_linkage"}
 facts=result.get("report",{}).get("key_findings",[])
 checks={"solar_selected_all_tools":tools.issubset(used),
         "candidate_count_evidence":any(f["value"]==expected["candidate_count"] and f["unit"]=="개" for f in facts),
         "peak_hour_evidence":any(f["value"]==peak["hour"] and f["unit"]=="시" for f in facts),
         "peak_count_evidence":any(f["value"]==peak["linked_count"] and f["unit"]=="건" for f in facts)}
 report={"checks":checks,"seconds":time.perf_counter()-began,"result":result,"question":question}
except Exception as error:
 report={"error_type":type(error).__name__,"seconds":time.perf_counter()-began}
Path("docs/transit/redesign-solar.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print(json.dumps({k:v for k,v in report.items() if k!="result"},ensure_ascii=False))
if "result" in report:
 print(json.dumps({k:report["result"].get(k) for k in ("answer","usage","answer_basis","llm_status")},ensure_ascii=False))
