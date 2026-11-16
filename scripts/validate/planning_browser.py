"""Real WIZ planning smoke checks. No model calls, no invented fixtures in production."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect
URL="https://project.wizide.com"
report={"url":URL,"page_errors":[],"cities":[]}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
 page=b.new_page(viewport={"width":1440,"height":1000})
 page.on("pageerror",lambda e:report["page_errors"].append(str(e)))
 page.goto(URL+"/course/aafa5691f92f40e89818200a14c98a90?public=1")
 expect(page.locator(".city-option")).to_have_count(4,timeout=30000)
 expect(page.locator(".goal-kpis .metric-card").nth(1).locator("strong")).to_have_text("5",timeout=30000)
 for city in ("서울","대전","세종"):
  page.locator(".bike-nav button").filter(has_text="대시보드").click()
  page.locator(".city-option").filter(has_text=city).click()
  expect(page.locator(".goal-kpis")).to_be_visible(timeout=30000)
  expect(page.locator(".dashboard-view .leaflet-overlay-pane svg").first).to_be_visible(timeout=30000)
  page.locator(".bike-nav button").filter(has_text="취약 구간").click()
  print("checking",city,flush=True)
  expect(page.locator(".new-sites-table tbody tr")).to_have_count(10,timeout=30000)
  expect(page.locator(".sensitivity-panel tbody tr")).to_have_count(9,timeout=30000)
  expect(page.locator(".relocation-panel tbody tr")).to_have_count(10,timeout=30000)
  expect(page.locator(".scenario-summary strong").first).to_contain_text("0",timeout=10000)
  options=page.locator(".scenario-options input")
  n=options.count();assert n>=1
  options.first.check()
  expect(page.locator(".scenario-summary strong").first).not_to_have_text("0.0000 km²",timeout=10000)
  options.first.uncheck()
  expect(page.locator(".scenario-summary strong").first).to_have_text("0.0000 km²",timeout=10000)
  report["cities"].append({"city":city,"new_sites_displayed":10,"sensitivity_cases":9,"relocation_rows":10,"scenario_options":n,"toggle":True})
  page.screenshot(path="docs/transit/planning-"+city+".png",full_page=True)
 page.set_viewport_size({"width":390,"height":844})
 report["mobile_overflow"]=page.evaluate("document.documentElement.scrollWidth>innerWidth")
 page.screenshot(path="docs/transit/planning-mobile.png",full_page=True)
 page.locator(".city-option").filter(has_text="전체").click()
 expect(page.locator(".new-sites-table tbody tr")).to_have_count(10,timeout=30000)
 page.get_by_label("신규 입지 분석 도시").select_option("daejeon")
 expect(page.locator(".scenario-options")).to_contain_text("신규 입지",timeout=10000)
 report["common_scope_city_switch"]=True
 b.close()
Path("docs/transit/planning-browser.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
assert not report["page_errors"] and not report["mobile_overflow"]
