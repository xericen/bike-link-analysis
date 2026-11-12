"""Exactly five paid Solar questions, submitted through the real WIZ browser UI."""
import json,time,sys,re
from pathlib import Path
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect

out=Path("docs/final-validation");out.mkdir(parents=True,exist_ok=True)
questions=[
("seoul","서울에서 이용량은 적지만 연결상 중요한 대여소는?"),
("seoul","ST-1481이 숨은 연결 후보인 이유는?"),
("daejeon","대전에서 반복적인 대여·반납 불균형이 나타나는 곳은?"),
("all","서울과 대전의 이용 패턴 차이는?"),
("seoul","서울 ST-1481 대여소의 역할은 최근 7일과 30일 사이에 달라졌는가?")]
results={"run_date":"2026-11-12","max_questions":5,"provider":"Upstage Solar","questions":[]}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
    page=browser.new_page(viewport={"width":1440,"height":1000})
    page.goto("http://localhost:3000/course/aafa5691f92f40e89818200a14c98a90?public=1")
    expect(page.locator(".city-option")).to_have_count(4,timeout=120000)
    page.locator(".bike-nav button").filter(has_text="AI 분석 리포트").click()
    for index,(region,question) in enumerate(questions,1):
        entry={"question":question,"region":region,"date_start":"2026-10-01","date_end":"2026-10-31"}
        try:
            label={"seoul":"서울","daejeon":"대전","all":"전체"}[region]
            page.locator(".city-option").filter(has_text=label).click()
            page.get_by_label("분석 시작일",exact=True).fill("2026-10-01")
            page.get_by_label("분석 종료일",exact=True).fill("2026-10-31")
            page.get_by_role("button",name="적용",exact=True).click()
            page.get_by_label("분석 질문",exact=True).fill(question)
            button=page.get_by_role("button",name="메시지 보내기",exact=True)
            expect(button).to_be_enabled(timeout=120000)
            t=time.perf_counter()
            with page.expect_response(lambda r:"/wiz/api/component.bike.link/handle" in r.url and "chat" in (r.request.post_data or ""),timeout=110000) as event:
                button.click()
            response=event.value.json()
            entry["seconds"]=round(time.perf_counter()-t,3)
            entry["code"]=response.get("code")
            entry["response"]=response.get("data")
            if entry["code"]==200:
                value=entry["response"]
                expect(page.locator(".report-summary")).to_be_visible(timeout=30000)
                entry["rendered_facts"]=page.locator(".report-facts article").count()
                entry["rendered_sources"]=page.locator(".report-source").count()
                entry["korean_answer"]=bool(re.search("[가-힣]",value.get("answer","")))
                calls=value.get("evidence",[])
                entry["solar_tools"]=[x["tool"] for x in calls if x.get("initiator")=="solar"]
                entry["guard_tools"]=[x["tool"] for x in calls if x.get("initiator")!="solar"]
                entry["period_arguments_match"]=all(
                    x["arguments"].get("date_range")=={"date_start":"2026-10-01","date_end":"2026-10-31"}
                    for x in calls if "date_range" in x["arguments"])
                entry["numeric_grounding"]=value.get("grounding_validation")
                entry["station_grounding"]=value.get("station_validation")
                page.screenshot(path=str(out/("solar-q"+str(index)+".png")),full_page=True)
        except Exception as exc:
            entry["browser_error"]=type(exc).__name__+": "+str(exc)[:300]
        results["questions"].append(entry)
        (out/"solar-live.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({k:v for k,v in entry.items() if k not in ("response","question")},ensure_ascii=False),flush=True)
    browser.close()
results["total_tokens_reported"]=sum((x.get("response") or {}).get("usage",{}).get("total_tokens",0) for x in results["questions"] if x.get("code")==200)
results["completed_questions"]=sum(x.get("code")==200 for x in results["questions"])
(out/"solar-live.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
print("SOLAR QUESTIONS",results["completed_questions"],"TOKENS",results["total_tokens_reported"],flush=True)
