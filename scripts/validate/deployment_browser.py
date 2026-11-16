"""External deployment smoke checks; AI screen only, no paid generation."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect
BASE="https://project.wizide.com"
report={"url":BASE,"page_errors":[],"checks":[],"ai_generation":"not executed"}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
    page=browser.new_page(viewport={"width":1365,"height":900})
    page.on("pageerror",lambda error:report["page_errors"].append(str(error)))
    page.goto(BASE+"/course/aafa5691f92f40e89818200a14c98a90?public=1")
    expect(page.locator(".city-option")).to_have_count(4,timeout=30000)
    for city in ("서울","대전","세종"):
        page.locator(".bike-nav button").filter(has_text="대시보드").click()
        page.locator(".city-option").filter(has_text=city).click()
        expect(page.locator(".dashboard-view")).to_be_visible(timeout=30000)
        expect(page.locator(".research-kpis")).not_to_contain_text("N/A",timeout=30000)
        for label,selector in [("대시보드",".dashboard-view"),("이동 패턴",".network-view"),("대여소 분석",".station-view"),("도시 간 비교",".regions-view"),("AI 분석 리포트",".agent-view")]:
            page.locator(".bike-nav button").filter(has_text=label).click()
            expect(page.locator(selector)).to_be_visible(timeout=30000)
            expect(page.locator(".bike-content > p.loading")).to_have_count(0,timeout=30000)
            expect(page.locator(".bike-content p.error")).to_have_count(0,timeout=30000)
            if selector==".station-view":
                expect(page.get_by_label("대여소 선택").locator("option")).not_to_have_count(0,timeout=30000)
                expect(page.locator(".transit-station-metrics")).to_be_visible(timeout=30000)
            print(city,label,flush=True)
            report["checks"].append({"city":city,"tab":label,"visible":True})
        page.screenshot(path="docs/transit/deployment-"+city+".png",full_page=True)
    page.locator(".bike-nav button").filter(has_text="대시보드").click()
    page.locator(".city-option").filter(has_text="서울").click()
    expect(page.locator(".dashboard-view")).to_be_visible(timeout=30000)
    page.get_by_label("분석 시작일").fill("2026-10-03")
    page.get_by_label("분석 종료일").fill("2026-10-04")
    page.locator(".period-actions button").filter(has_text="적용").click()
    expect(page.get_by_role("heading",name="이 도시·기간은 아직 데이터 미처리")).to_be_visible(timeout=30000)
    page.locator(".bike-content article").filter(has_text="이 도시·기간은 아직 데이터 미처리").get_by_role("button").first.click()
    expect(page.locator(".dashboard-view")).to_be_visible(timeout=30000)
    report["unprepared_period"]={"explicit_notice":True,"navigation_to_prepared_period":True}
    browser.close()
assert not report["page_errors"],report
Path("docs/transit/deployment-browser.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
