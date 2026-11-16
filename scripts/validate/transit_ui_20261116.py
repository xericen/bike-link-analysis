"""Real WIZ UI inspection; no Solar calls."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect
out=Path("docs/transit");report={"page_errors":[]}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
 page=b.new_page(viewport={"width":1273,"height":818});page.on("pageerror",lambda e:report["page_errors"].append(str(e)))
 page.goto("http://localhost:3000/course/aafa5691f92f40e89818200a14c98a90?public=1")
 expect(page.locator(".city-option")).to_have_count(4,timeout=120000)
 expect(page.locator(".transit-layer-toggle input")).to_be_visible(timeout=120000)
 expect(page.locator(".leaflet-container .leaflet-interactive").first).to_be_visible(timeout=120000)
 # Wait for the actual linkage action instead of a fake progress stage.
 page.wait_for_function("document.querySelectorAll('.leaflet-container .leaflet-interactive').length>200",timeout=120000)
 before=page.locator(".leaflet-container .leaflet-interactive").count()
 page.locator(".transit-layer-toggle input").uncheck()
 after=page.locator(".leaflet-container .leaflet-interactive").count()
 assert after<before
 page.locator(".transit-layer-toggle input").check()
 report["layer_markers_before"]=before;report["after_toggle"]=after
 page.screenshot(path=str(out/"integration-dashboard-20261116.png"),full_page=True)
 page.locator(".bike-nav button").filter(has_text="대여소 분석").click()
 expect(page.locator(".transit-station-metrics")).to_be_visible(timeout=120000)
 report["station_linkage_visible"]=True
 page.screenshot(path=str(out/"integration-station-20261116.png"),full_page=True)
 page.locator(".city-option").filter(has_text="세종").click()
 page.locator(".bike-nav button").filter(has_text="대시보드").click()
 expect(page.locator(".dashboard-view .research-kpis")).to_contain_text("259,143",timeout=120000)
 report["sejong_real_kpi"]=259143
 page.screenshot(path=str(out/"integration-sejong-20261116.png"),full_page=True)
 page.set_viewport_size({"width":390,"height":844})
 report["mobile_overflow"]=page.evaluate("document.documentElement.scrollWidth>innerWidth")
 b.close()
(out/"integration-browser-20261116.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
