"""Five bounded WIZ questions including two targeted recovery checks; attempt IDs are never repeated."""
import json,os,sys,time
from datetime import datetime,timezone
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"docs/solar-recovery-20261112"
OUT.mkdir(parents=True,exist_ok=True)
load_dotenv(ROOT/".env")
secret=os.getenv("UPSTAGE_API_KEY")
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect
path=OUT/"live.json"
log=json.loads(path.read_text()) if path.exists() else {
    "started_at":datetime.now(timezone.utc).isoformat(),"questions":[],"page_errors":[],"external_retries":0}
questions=[
 "서울 관측 기간과 총 대여 건수, 일별 최대 날짜와 건수를 알려줘.",
 "서울 PageRank 1위 대여소의 ID와 점수를 알려줘.",
 "서울 ST-1481의 대여 건수와 반납 건수, 실제 관측일수를 알려줘. 대여소 상세 정보만 조회해줘.",
 "서울 PageRank 1위 대여소의 ID와 점수를 알려줘.",
 "서울 ST-1481의 대여 건수와 반납 건수, 실제 관측일수를 알려줘. 대여소 상세 정보만 조회해줘."
]
def save():
    value=json.dumps(log,ensure_ascii=False,indent=2)
    assert not secret or secret not in value
    path.write_text(value,encoding="utf-8")
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
    page=b.new_page(viewport={"width":1440,"height":1100})
    page.on("pageerror",lambda e:log["page_errors"].append(type(e).__name__))
    page.goto("http://localhost:3000/course/aafa5691f92f40e89818200a14c98a90?public=1")
    expect(page.locator(".city-option")).to_have_count(4,timeout=120000)
    page.locator(".city-option").filter(has_text="서울").click()
    page.locator(".bike-nav button").filter(has_text="AI 분석 리포트").click()
    page.get_by_label("분석 시작일",exact=True).fill("2026-10-01")
    page.get_by_label("분석 종료일",exact=True).fill("2026-10-31")
    page.get_by_role("button",name="적용",exact=True).click()
    page.wait_for_load_state("networkidle",timeout=150000)
    log["targeted_rechecks_after_initial_network_idle"] = True
    for i,question in enumerate(questions,1):
        if any(q["id"]==i for q in log["questions"]):continue
        entry={"id":i,"question":question,"started_at":datetime.now(timezone.utc).isoformat(),"state":"attempting"}
        log["questions"].append(entry)
        save()
        try:
            page.get_by_label("분석 질문",exact=True).fill(question)
            button=page.get_by_role("button",name="메시지 보내기",exact=True)
            expect(button).to_be_enabled(timeout=120000)
            started=time.perf_counter()
            with page.expect_response(lambda r:"/wiz/api/component.bike.link/handle" in r.url and "chat" in (r.request.post_data or ""),timeout=150000) as event:
                button.click()
            response=event.value
            body=response.json()
            entry.update({"state":"received","seconds":round(time.perf_counter()-started,3),"http_status":response.status,"body":body})
            if body.get("code")==200:
                expect(page.locator(".report-summary")).to_be_visible(timeout=30000)
                entry["fact_cards"]=page.locator(".report-facts article").count()
                entry["visible_answer"]=page.locator(".chat-message.bot").inner_text()
                entry["tool_summaries"]=page.locator(".evidence-panel details summary").all_text_contents()
            entry["screenshot"]="q"+str(i)+".png"
            page.screenshot(path=str(OUT/entry["screenshot"]),full_page=True)
        except Exception as exc:
            entry.update({"state":"client_error","error_type":type(exc).__name__})
        save()
        value=(entry.get("body") or {}).get("data") or {}
        print(json.dumps({"id":i,"code":(entry.get("body") or {}).get("code"),"seconds":entry.get("seconds"),
            "llm_status":value.get("llm_status"),"usage":value.get("usage"),"usage_complete":value.get("usage_complete")},ensure_ascii=False),flush=True)
    b.close()
data=[(q.get("body") or {}).get("data") or {} for q in log["questions"]]
log["known_usage"]={key:sum(x.get("usage",{}).get(key,0) for x in data) for key in ("prompt_tokens","completion_tokens","total_tokens")}
log["usage_complete"]=all(x.get("usage_complete",False) for x in data)
log["completed_at"]=datetime.now(timezone.utc).isoformat()
save()
