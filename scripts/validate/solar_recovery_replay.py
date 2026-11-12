"""Free final-guard replay of actual paid responses; never contacts Solar."""
import json,sys,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.agents import solar
OUT=ROOT/"docs/solar-recovery-20261112"
log=json.loads((OUT/"live.json").read_text())
checks={"paid_calls_added":0,"tool_count":len(solar.TOOLS),"questions":[]}
final={}
for q in log["questions"]:
    old=q.get("body",{}).get("data") or {}
    if q["id"] not in (1,4,5):continue
    value=solar.finalize_answer(q["question"],old.get("solar_answer") or old["answer"],
        old["evidence"],old.get("analysis_context"),old.get("model_finish_reason"))
    value={**old,**value}
    final[q["id"]]=value
    checks["questions"].append({"id":q["id"],"answer_basis":value["answer_basis"],
        "grounding_validation":value["grounding_validation"],"semantic_validation":value["semantic_validation"],
        "answer":value["answer"],"evidence_tools":[e["tool"] for e in value["evidence"]]})
assert final[1]["answer_basis"]=="tool_summary"
assert "166657" in final[1]["answer"] and "2026-10-02" in final[1]["answer"]
assert final[4]["answer_basis"]=="solar_interpretation"
assert "ST-3388" in final[4]["answer"] and "0.003208" in final[4]["answer"]
assert final[5]["grounding_validation"]["passed"]
assert all(value in final[5]["answer"] for value in ("926","1322","31"))
# Check the requested counts and daily extrema directly against SQLite.
with sqlite3.connect("file:"+str(ROOT/"data/processed/analysis.sqlite")+"?mode=ro",uri=True) as db:
    daily=db.execute("SELECT date,SUM(rental_count) FROM station_usage WHERE region_id='seoul' AND date BETWEEN '2026-10-01' AND '2026-10-31' GROUP BY date").fetchall()
    rentals,returns=db.execute("SELECT SUM(rental_count),SUM(return_count) FROM station_usage WHERE region_id='seoul' AND station_id='ST-1481' AND date BETWEEN '2026-10-01' AND '2026-10-31'").fetchone()
    assert (rentals,returns)==(926,1322)
    assert max(daily,key=lambda x:x[1])==("2026-10-02",166657)
checks["sql"]={"ST-1481":{"rentals":rentals,"returns":returns},"maximum_day":max(daily,key=lambda x:x[1]),"total":sum(n for d,n in daily)}
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect
intercepted=[]
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
    page=b.new_page(viewport={"width":1440,"height":1100})
    def route(request_route):
        if "chat" in (request_route.request.post_data or ""):
            intercepted.append(True)
            request_route.fulfill(status=200,content_type="application/json",
                body=json.dumps({"code":200,"data":final[5]},ensure_ascii=False))
        else:
            request_route.continue_()
    page.route("**/wiz/api/component.bike.link/handle",route)
    page.goto("http://localhost:3000/course/aafa5691f92f40e89818200a14c98a90?public=1")
    expect(page.locator(".city-option")).to_have_count(4,timeout=120000)
    page.locator(".bike-nav button").filter(has_text="AI 분석 리포트").click()
    page.get_by_label("분석 질문",exact=True).fill(log["questions"][4]["question"])
    button=page.get_by_role("button",name="메시지 보내기",exact=True)
    expect(button).to_be_enabled(timeout=120000)
    button.click()
    expect(page.locator(".report-facts")).to_contain_text("926",timeout=30000)
    expect(page.locator(".report-facts")).to_contain_text("1,322")
    expect(page.locator(".chat-message.bot")).to_contain_text("31")
    page.screenshot(path=str(OUT/"q5-final-replay.png"),full_page=True)
    b.close()
assert len(intercepted)==1
checks["screen_verification"]={"mode":"saved_paid_response_replay","intercepted_chat_requests":1,"actual_new_solar_requests":0,"screenshot":"q5-final-replay.png"}
(OUT/"replay-checks.json").write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"replay":"passed","new_solar_requests":0,"sql":"passed","tool_count":checks["tool_count"]}))
