"""Phase 2 browser checks and exactly one paid Solar question (no retries)."""
import json,re,time,sys
from pathlib import Path
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect
out=Path("docs/transit");out.mkdir(parents=True,exist_ok=True)
report={"paid_questions_attempted":0,"browser_errors":[]}
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
 page=browser.new_page(viewport={"width":1273,"height":818})
 page.on("pageerror",lambda e:report["browser_errors"].append(str(e)))
 page.goto("http://localhost:3000/course/aafa5691f92f40e89818200a14c98a90?public=1")
 expect(page.locator(".city-option")).to_have_count(4,timeout=120000)
 page.locator(".city-option").filter(has_text="서울").click()
 page.locator(".bike-nav button").filter(has_text="이동 패턴").click()
 panel=page.locator(".transit-panel")
 expect(panel.locator("tbody tr")).to_have_count(9,timeout=120000)
 expect(panel.locator("#bike-transit-map .leaflet-interactive")).to_have_count(9,timeout=30000)
 report["candidate_rows"]=9
 panel.locator("input[type=checkbox]").uncheck()
 expect(panel.locator("#bike-transit-map .leaflet-interactive")).to_have_count(0)
 panel.locator("input[type=checkbox]").check()
 expect(panel.locator("#bike-transit-map .leaflet-interactive")).to_have_count(9)
 panel.scroll_into_view_if_needed()
 page.screenshot(path=str(out/"phase2-vulnerability-desktop.png"),full_page=True)
 page.set_viewport_size({"width":390,"height":844})
 report["mobile_overflow"]=page.evaluate("document.documentElement.scrollWidth > innerWidth")
 page.screenshot(path=str(out/"phase2-vulnerability-mobile.png"),full_page=True)
 page.set_viewport_size({"width":1273,"height":818})
 panel.locator("tbody button").first.click()
 expect(page.locator(".station-view")).to_be_visible(timeout=120000)
 report["ranking_to_station"]=True
 page.locator(".bike-nav button").filter(has_text="AI 분석 리포트").click()
 page.get_by_label("분석 질문",exact=True).fill("서울의 대중교통 정류장에서 500m 넘게 떨어진 연계 취약 대여소 상위 1개를 찾아 최근접 거리와 실제 대여량을 알려줘. 공간 시나리오의 한계도 설명해줘.")
 button=page.get_by_role("button",name="메시지 보내기",exact=True)
 expect(button).to_be_enabled(timeout=120000)
 report["paid_questions_attempted"]=1
 started=time.perf_counter()
 try:
  with page.expect_response(lambda r:"/wiz/api/component.bike.link/handle" in r.url and "chat" in (r.request.post_data or ""),timeout=110000) as event:
   button.click()
  value=event.value.json()
  report["seconds"]=round(time.perf_counter()-started,3); report["solar"]=value
  if value.get("code")==200:
   expect(page.locator(".report-summary")).to_be_visible(timeout=30000)
   d=value["data"]
   report["solar_tools"]=[e["tool"] for e in d.get("evidence",[]) if e.get("initiator")=="solar"]
   report["new_tool_used"]=any(x in report["solar_tools"] for x in ["get_transit_vulnerability","get_improvement_ranking"])
   report["rendered_fact_cards"]=page.locator(".report-facts article").count()
   report["rendered_sources"]=page.locator(".report-source").count()
  page.screenshot(path=str(out/"phase2-solar.png"),full_page=True)
 except Exception as error:
  report["solar_error"]=str(error)[:300]
 browser.close()
(out/"phase2-browser-solar.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k!="solar"},ensure_ascii=False))
