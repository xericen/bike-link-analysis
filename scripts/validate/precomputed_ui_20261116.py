"""Current WIZ core-cache and linkage UI verification; no paid model calls."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect
out=Path("docs/transit");report={"page_errors":[],"actions":[]}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
 page=b.new_page(viewport={"width":1273,"height":818})
 page.on("pageerror",lambda error:report["page_errors"].append(str(error)))
 page.goto("http://localhost:3000/course/aafa5691f92f40e89818200a14c98a90?public=1")
 expect(page.locator(".city-option")).to_have_count(4,timeout=30000)
 expect(page.locator(".dashboard-view .research-kpis")).to_contain_text("207",timeout=30000)
 for city,number in [("대전","62"),("전체","269")]:
  began=time.perf_counter()
  page.locator(".city-option").filter(has_text=city).click()
  expect(page.locator(".dashboard-view .research-kpis")).to_contain_text(number,timeout=15000)
  report["actions"].append({"city":city,"core_visible_ms":round((time.perf_counter()-began)*1000,3),"expected_imbalance_candidates":int(number)})
  expect(page.locator(".transit-layer-toggle input")).to_be_visible(timeout=15000)
  page.screenshot(path=str(out/("precomputed-"+("daejeon" if city=="대전" else "all")+"-20261116.png")),full_page=True)
 page.locator(".bike-nav button").filter(has_text="대여소 분석").click()
 expect(page.locator(".transit-station-metrics")).to_be_visible(timeout=30000)
 report["station_linkage_visible"]=True
 page.locator(".bike-nav button").filter(has_text="이동 패턴").click()
 expect(page.locator(".network-view")).to_be_visible(timeout=15000)
 report["network_visible"]=True
 page.set_viewport_size({"width":390,"height":844})
 report["mobile_overflow"]=page.evaluate("document.documentElement.scrollWidth>innerWidth")
 b.close()
assert not report["page_errors"] and not report["mobile_overflow"],report
(out/"precomputed-browser-20261116.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
