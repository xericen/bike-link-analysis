"""Goal-led UI, prepared data, candidate navigation and responsive regression."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect
report={"page_errors":[],"cities":[],"url":"https://project.wizide.com"}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
 page=b.new_page(viewport={"width":1440,"height":1000})
 page.on("pageerror",lambda e:report["page_errors"].append(str(e)))
 page.goto(report["url"]+"/course/aafa5691f92f40e89818200a14c98a90?public=1")
 expect(page.locator(".bike-header h1")).to_contain_text("대중교통 연결 공백",timeout=30000)
 for city,count in [("서울",5),("대전",1),("세종",None)]:
  page.locator(".bike-nav button").filter(has_text="대시보드").click()
  page.locator(".city-option").filter(has_text=city).click()
  expect(page.locator(".goal-kpis")).to_contain_text("역 300m",timeout=30000)
  if count is not None:
   expect(page.locator(".goal-kpis .metric-card").nth(1).locator("strong")).to_have_text(str(count),timeout=30000)
   expect(page.locator(".goal-kpis .metric-card").nth(3).locator("strong")).not_to_have_text("N/A",timeout=30000)
  else:
   expect(page.locator(".goal-kpis")).to_contain_text("N/A",timeout=30000)
  if count is not None:
   expect(page.locator(".transit-layer-toggle input")).to_be_checked()
   page.locator(".transit-layer-toggle input").uncheck()
   expect(page.locator(".transit-layer-toggle input")).not_to_be_checked()
   page.locator(".transit-layer-toggle input").check()
  page.screenshot(path="docs/transit/redesign-"+city+"-dashboard.png",full_page=True)
  page.locator(".bike-nav button").filter(has_text="취약 구간").click()
  expect(page.locator(".vulnerability-view")).to_be_visible(timeout=30000)
  if count is not None:
   expect(page.locator(".transit-panel tbody tr")).to_have_count(count,timeout=30000)
   expect(page.locator(".scenario-card")).to_have_count(1)
   page.locator(".transit-panel tbody tr").first.locator("button").click()
   expect(page.locator(".transit-station-metrics")).to_contain_text("이 대여소가 보완하는 정류장",timeout=30000)
  else:
   expect(page.locator(".transit-panel")).to_contain_text("좌표 미확보",timeout=30000)
  for label,selector in [("이동 패턴",".network-view"),("도시 간 비교",".regions-view"),("AI 분석 리포트",".agent-view")]:
   page.locator(".bike-nav button").filter(has_text=label).click()
   expect(page.locator(selector)).to_be_visible(timeout=30000)
  expect(page.locator(".question-presets")).to_contain_text("확충 우선 순위")
  report["cities"].append({"city":city,"candidates":count,"legacy_tabs_visible":True})
 page.locator(".bike-nav button").filter(has_text="취약 구간").click()
 page.locator(".city-option").filter(has_text="서울").click()
 expect(page.locator(".transit-panel tbody tr")).to_have_count(5,timeout=30000)
 page.screenshot(path="docs/transit/redesign-candidates.png",full_page=True)
 page.set_viewport_size({"width":390,"height":844})
 report["mobile_candidate_overflow"]=page.evaluate("document.documentElement.scrollWidth>innerWidth")
 page.screenshot(path="docs/transit/redesign-mobile.png",full_page=True)
 page.locator(".bike-nav button").filter(has_text="대시보드").click()
 expect(page.locator(".goal-kpis")).to_be_visible(timeout=30000)
 report["mobile_dashboard_overflow"]=page.evaluate("document.documentElement.scrollWidth>innerWidth")
 b.close()
Path("docs/transit/redesign-browser.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
assert not report["page_errors"] and not report["mobile_candidate_overflow"] and not report["mobile_dashboard_overflow"]
