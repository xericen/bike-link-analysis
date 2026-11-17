"""Current WIZ browser audit; executes exactly one authorized Solar preset."""
import json,sys,time,re
from pathlib import Path
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect
out=Path("docs/transit");report={"page_errors":[],"solar_calls":[]}
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
    page=b.new_page(viewport={"width":1273,"height":818})
    page.on("pageerror",lambda e:report["page_errors"].append(str(e)))
    def response(r):
        if "/component.bike.link/handle" not in r.url:return
        if "action=chat" in (r.request.post_data or ""):
            try:
                value=r.json();data=value.get("data",{})
                report["solar_calls"].append({"code":value.get("code"),"answer":data.get("answer"),"answer_basis":data.get("answer_basis"),
                    "usage":data.get("usage"),"evidence":[{"tool":e["tool"],"arguments":e.get("arguments"),"initiator":e.get("initiator")} for e in data.get("evidence",[])]})
            except Exception as e:report["solar_calls"].append({"error":type(e).__name__})
    page.on("response",response)
    page.goto("http://localhost:3000/course/aafa5691f92f40e89818200a14c98a90?public=1")
    expect(page.locator(".city-option")).to_have_count(4,timeout=40000)
    expect(page.locator(".bike-header h1")).to_have_text("공유자전거, 대중교통 연결 공백을 얼마나 메우는가")
    page.locator(".city-option").filter(has_text="세종").click()
    expect(page.locator(".goal-kpis")).to_contain_text("46.556",timeout=30000)
    expect(page.locator(".goal-kpis")).to_contain_text("236")
    expect(page.locator(".goal-kpis")).to_contain_text("BRT 정류장 300m")
    report["sejong_dashboard"]=page.locator(".goal-kpis").inner_text()
    assert "N/A" not in report["sejong_dashboard"]
    expect(page.locator(".dashboard-view")).to_contain_text("세종은 지하철 없이 BRT가 대중교통 축")
    page.screenshot(path=str(out/"city-anchors-sejong-20261117.png"),full_page=True)
    page.locator(".bike-nav button").filter(has_text="취약 구간").click()
    expect(page.locator(".planning-map path[fill='#e7b787']").first).to_be_visible(timeout=30000)
    report["gap_grid_paths"]=page.locator(".planning-map path[fill='#e7b787']").count()
    assert report["gap_grid_paths"]>0
    assert "인구밀도" not in page.locator(".new-sites-table thead").inner_text()
    report["sejong_population_column_hidden"]=True
    relocation=page.locator("article").filter(has=page.get_by_role("heading",name="재배치 검토 대상",exact=True))
    assert relocation.locator("td").filter(has_text=re.compile("^X$")).count()==0
    assert "거치 용량" not in relocation.locator("thead").inner_text()
    report["relocation_direction_text"]=relocation.locator("tbody tr").first.inner_text()
    page.screenshot(path=str(out/"city-anchors-grid-20261117.png"),full_page=True)
    page.set_viewport_size({"width":390,"height":844})
    report["mobile_overflow"]=page.evaluate("document.documentElement.scrollWidth>innerWidth")
    page.set_viewport_size({"width":1273,"height":818})
    page.locator(".bike-nav button").filter(has_text="AI 분석").click()
    t=time.perf_counter()
    page.locator(".question-presets button").first.click()
    expect(page.locator(".agent-loading")).to_be_visible(timeout=1500)
    report["loading_visible_ms"]=(time.perf_counter()-t)*1000
    expect(page.locator(".question-presets button").first).to_be_disabled()
    expect(page.locator(".agent-loading")).not_to_be_visible(timeout=120000)
    report["preset_to_completion_ms"]=(time.perf_counter()-t)*1000
    page.screenshot(path=str(out/"city-anchors-agent-20261117.png"),full_page=True)
    b.close()
assert not report["page_errors"] and not report["mobile_overflow"],report
report["automatic_chat_sent"]=bool(report["solar_calls"])
assert report["automatic_chat_sent"],report
(out/"city-anchors-browser-20261117.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
