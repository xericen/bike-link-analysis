"""Review hpvgdafxkclbrixczgryxevuyzafjovb: one tiny provider probe + four bounded WIZ questions.
No retries; never persist headers, credentials, or environment values.
Run from bike-link-analysis with python scripts/validate/review_solar.py.
"""
import hashlib, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
OUT = ROOT / "docs/solar-verification-20261112"
OUT.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT / ".env")
key = os.getenv("UPSTAGE_API_KEY")
model = os.getenv("UPSTAGE_MODEL", "solar-mini4")
log = {"review_id":"hpvgdafxkclbrixczgryxevuyzafjovb","started_at":datetime.now(timezone.utc).isoformat(),
       "key_set":bool(key),"requested_model":model,"provider_probe":{},"questions":[],"page_errors":[],
       "source_sha256":{p:hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
          ["backend/agents/solar.py","backend/services/wiz_bridge.py","../src/app/component.bike.link/api.py",
           "../src/app/component.bike.link/view.ts","../src/app/component.bike.link/view.pug"]}}
def save():
    text = json.dumps(log, ensure_ascii=False, indent=2)
    if key and key in text:
        raise RuntimeError("Credential detected; refusing to write")
    (OUT / "execution.json").write_text(text,encoding="utf-8")

previous = OUT / "execution.json"
if previous.exists():
    log = json.loads(previous.read_text(encoding="utf-8"))
    log["resumed_at"] = datetime.now(timezone.utc).isoformat()
if key and not log.get("provider_probe"):
    try:
        started=time.perf_counter()
        response=httpx.post("https://api.upstage.ai/v1/chat/completions",
            headers={"Authorization":"Bearer "+key},
            json={"model":model,"messages":[{"role":"user","content":"Reply OK."}],"max_tokens":16},
            timeout=30)
        probe={"http_status":response.status_code,"seconds":round(time.perf_counter()-started,3),
               "endpoint":"https://api.upstage.ai/v1/chat/completions"}
        if response.status_code==200:
            data=response.json()
            probe.update({"response_id":data.get("id"),"model":data.get("model"),"usage":data.get("usage"),
                          "finish_reason":data.get("choices",[{}])[0].get("finish_reason")})
        log["provider_probe"]=probe
    except Exception as exc:
        log["provider_probe"]={"error_type":type(exc).__name__}
save()
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright, expect
questions=[
 "서울 관측 기간과 총 대여 건수를 알려줘.",
 "서울 PageRank 1위 대여소의 ID와 점수를 알려줘.",
 "서울 ST-1481과 시간대가 가장 유사한 대여소 1곳의 ID와 코사인 유사도를 알려줘.",
 "서울 ST-1481의 대여 건수와 반납 건수를 알려줘. 대여소 상세 정보만 조회해줘."
]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,
       executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
    page=browser.new_page(viewport={"width":1440,"height":1000})
    page.on("pageerror",lambda error:log["page_errors"].append(type(error).__name__))
    page.goto("http://localhost:3000/course/aafa5691f92f40e89818200a14c98a90?public=1")
    expect(page.locator(".city-option")).to_have_count(4,timeout=120000)
    page.locator(".city-option").filter(has_text="서울").click()
    page.locator(".bike-nav button").filter(has_text="AI 분석 리포트").click()
    page.get_by_label("분석 시작일",exact=True).fill("2026-10-01")
    page.get_by_label("분석 종료일",exact=True).fill("2026-10-31")
    page.get_by_role("button",name="적용",exact=True).click()
    log["browser_url"]=page.url
    for i,question in enumerate(questions,1):
        if any(item["id"] == i for item in log["questions"]):
            continue
        entry={"id":i,"question":question}
        try:
            page.get_by_label("분석 질문",exact=True).fill(question)
            button=page.get_by_role("button",name="메시지 보내기",exact=True)
            expect(button).to_be_enabled(timeout=120000)
            started=time.perf_counter()
            with page.expect_response(lambda r: "/wiz/api/component.bike.link/handle" in r.url
                and "chat" in (r.request.post_data or ""),timeout=115000) as event:
                button.click()
            response=event.value
            body=response.json()
            entry.update({"wiz_http_status":response.status,"wiz_code":body.get("code"),
                "seconds":round(time.perf_counter()-started,3),"response":body.get("data"),"response_envelope":body})
            if body.get("code")==200:
                expect(page.locator(".report-summary")).to_be_visible(timeout=30000)
                entry["rendered_tool_names"]=page.locator(".tool-evidence summary").all_text_contents() if page.locator(".tool-evidence").count() else page.locator("details summary").all_text_contents()
                entry["rendered_fact_cards"]=page.locator(".report-facts article").count()
                entry["rendered_sources"]=page.locator(".report-source").count()
                entry["answer_visible"]=page.locator(".chat-message.bot").is_visible()
                entry["screenshot"]="q"+str(i)+".png"
                page.screenshot(path=str(OUT/entry["screenshot"]),full_page=True)
            else:
                entry["message"]=body.get("message")
                page.screenshot(path=str(OUT/("q"+str(i)+"-failed.png")),full_page=True)
        except Exception as exc:
            entry["error_type"]=type(exc).__name__
        log["questions"].append(entry)
        save()
        print(json.dumps({k:v for k,v in entry.items() if k not in ("response","response_envelope")},ensure_ascii=False),flush=True)
    browser.close()
usage=[log["provider_probe"].get("usage") or {}]+[(q.get("response") or {}).get("usage",{}) for q in log["questions"]]
log["total_usage"]={k:sum(x.get(k,0) or 0 for x in usage) for k in ("prompt_tokens","completion_tokens","total_tokens")}
log["completed_at"]=datetime.now(timezone.utc).isoformat()
save()
print(json.dumps({"provider_probe":log["provider_probe"],"total_usage":log["total_usage"],"questions":len(log["questions"])},ensure_ascii=False),flush=True)
