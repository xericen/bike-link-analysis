"""Actual WIZ interactions, plus explicitly labelled replay of a paid response guard."""
import sys,json,time,sqlite3
from pathlib import Path
sys.path.insert(0,"/tmp/bike-playwright")
from playwright.sync_api import sync_playwright,expect

out=Path("docs/final-validation");out.mkdir(exist_ok=True,parents=True)
report={"run_date":"2026-11-12","screens":[],"interactions":[],"page_errors":[],"solar_replay_only":True}
c=sqlite3.connect("file:data/processed/analysis.sqlite?mode=ro",uri=True)
def total(start,end,region="seoul"):
    return c.execute("SELECT SUM(rental_count) FROM station_usage WHERE region_id=? AND date>=? AND date<=?",(region,start,end)).fetchone()[0]
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path="/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome",args=["--no-sandbox"])
    page=b.new_page(viewport={"width":1273,"height":818})
    page.on("pageerror",lambda e:report["page_errors"].append(str(e)))
    page.goto("http://localhost:3000/course/aafa5691f92f40e89818200a14c98a90?public=1")
    expect(page.locator(".dashboard-view .research-kpis")).to_contain_text("4,245,954",timeout=120000)
    for days,start in ((7,"2026-10-25"),(14,"2026-10-18"),(30,"2026-10-02")):
        page.get_by_role("button",name=str(days)+"일",exact=True).click()
        loading=page.locator(".loading").all_text_contents()
        expect(page.locator(".dashboard-view .research-kpis")).to_contain_text(format(total(start,"2026-10-31"),","),timeout=120000)
        expect(page.get_by_label("분석 시작일",exact=True)).to_have_value(start)
        report["interactions"].append({"quick_days":days,"start":start,"expected_sql":total(start,"2026-10-31"),"loading_observed":loading})
    page.get_by_label("분석 시작일",exact=True).fill("2026-10-01")
    page.get_by_label("분석 종료일",exact=True).fill("2026-10-31")
    page.get_by_role("button",name="적용",exact=True).click()
    expect(page.locator(".dashboard-view .research-kpis")).to_contain_text("4,245,954",timeout=120000)
    page.get_by_label("분석 시작일",exact=True).fill("2026-10-31")
    page.get_by_label("분석 종료일",exact=True).fill("2026-10-01")
    page.get_by_role("button",name="적용",exact=True).click()
    expect(page.locator(".period-error")).to_be_visible()
    report["interactions"].append({"invalid_order_error":True})
    page.get_by_label("분석 시작일",exact=True).fill("2026-10-01")
    page.get_by_label("분석 종료일",exact=True).fill("2026-10-31")
    page.get_by_role("button",name="적용",exact=True).click()
    expect(page.locator(".leaflet-interactive").nth(10)).to_be_visible(timeout=120000)
    page.locator(".leaflet-interactive").nth(10).click()
    expect(page.locator(".station-view")).to_be_visible(timeout=120000)
    expect(page.locator(".selected-station")).to_be_visible(timeout=120000)
    report["interactions"].append({"map_station_click":page.locator(".selected-station").inner_text()})
    page.get_by_label("대여소 검색",exact=True).fill("ST-1481")
    page.get_by_role("button",name="검색",exact=True).click()
    expect(page.locator(".station-toolbar option")).to_have_count(1,timeout=120000)
    page.locator(".station-toolbar select").select_option(index=0)
    expect(page.locator(".selected-station")).to_contain_text("ST-1481",timeout=120000)
    page.get_by_role("button",name="기간별 실제 분석 불러오기",exact=True).click()
    expect(page.locator(".history-chart > div")).to_have_count(3,timeout=180000)
    page.get_by_role("button",name="7·14·30일 군집 안정성 검증",exact=True).click()
    expect(page.locator(".stability-panel")).to_contain_text("ARI",timeout=180000)
    report["interactions"].append({"station_search":"ST-1481","history_bars":3,"cluster_stability_rendered":True})
    page.locator(".bike-nav button").filter(has_text="이동 패턴 분석").click()
    expect(page.locator(".network-map g[role=button]").first).to_be_visible(timeout=120000)
    page.locator(".network-map g[role=button]").first.click()
    expect(page.locator(".station-view")).to_be_visible(timeout=120000)
    report["interactions"].append({"network_node_click":True})
    page.locator(".bike-nav button").filter(has_text="대시보드").click()
    page.locator(".city-option").filter(has_text="전체").click()
    expect(page.locator(".dashboard-view .research-kpis")).to_contain_text("5,169,532",timeout=180000)
    assert page.locator(".dashboard-view").count()==1
    report["interactions"].append({"unified_dashboard":True})
    page.locator(".city-option").filter(has_text="세종").click()
    expect(page.get_by_label("분석 시작일",exact=True)).to_be_disabled()
    expect(page.locator(".dashboard-view")).to_contain_text("연간",timeout=120000)
    report["interactions"].append({"sejong_annual_only":True,"date_controls_disabled":True})
    page.locator(".city-option").filter(has_text="서울").click()
    expect(page.locator(".dashboard-view .research-kpis")).to_contain_text("4,245,954",timeout=120000)
    expect(page.locator(".findings-grid .station-link").first).to_be_visible(timeout=180000)
    page.locator(".findings-grid .station-link").first.click()
    expect(page.locator(".selected-station")).to_contain_text("ST-1481",timeout=120000)
    report["interactions"].append({"finding_card_to_detail":"ST-1481"})
    for name,key,selector in (("대시보드","dashboard",".dashboard-view"),("대여소 분석","station",".station-view"),("이동 패턴 분석","network",".network-view"),("도시 간 비교","compare",".regions-view"),("AI 분석 리포트","agent",".agent-view")):
        page.locator(".bike-nav button").filter(has_text=name).click()
        expect(page.locator(selector)).to_be_visible(timeout=120000)
        page.screenshot(path=str(out/("screen-"+key+".png")))
        overflow=page.evaluate("document.documentElement.scrollWidth>innerWidth")
        assert not overflow
        report["screens"].append({"page":key,"desktop_overflow":overflow})
    page.locator(".city-option").filter(has_text="전체").click()
    replay=json.loads((out/"solar-guard-replay.json").read_text())[3]
    def handler(route):
        if "chat" in (route.request.post_data or ""):
            route.fulfill(status=200,content_type="application/json",body=json.dumps({"code":200,"data":replay},ensure_ascii=False))
        else:route.continue_()
    page.route("**/wiz/api/component.bike.link/handle",handler)
    page.get_by_label("분석 질문",exact=True).fill("검증된 실제 비교 응답 재생")
    page.get_by_role("button",name="메시지 보내기",exact=True).click()
    expect(page.locator(".report-summary")).to_be_visible(timeout=30000)
    expect(page.locator(".chat-bubble.answer > strong")).to_have_text("실제 도구 기반 요약")
    assert not page.locator(".chat-bubble.answer details p").is_visible()
    page.screenshot(path=str(out/"solar-guard-replay.png"))
    report["interactions"].append({"actual_response_guard_replay":True,"extra_paid_calls":0,"raw_prose_closed":True})
    page.unroute("**/wiz/api/component.bike.link/handle",handler)
    page.set_viewport_size({"width":390,"height":844})
    for name in ("대시보드","대여소 분석","이동 패턴 분석","도시 간 비교","AI 분석 리포트"):
        page.locator(".bike-nav button").filter(has_text=name).click()
        page.wait_for_timeout(200)
        overflow=page.evaluate("document.documentElement.scrollWidth>innerWidth")
        assert not overflow
        report["screens"].append({"page":name,"mobile_overflow":overflow})
    page.screenshot(path=str(out/"screen-mobile.png"))
    invalid=page.request.post("http://localhost:3000/wiz/api/component.bike.link/handle",form={
        "action":"overview","region_id":"all","date_start":"2026-09-01","date_end":"2026-10-31"}).json()
    assert invalid["code"]==422
    report["interactions"].append({"server_out_of_bounds":422})
    b.close()
assert not report["page_errors"]
(out/"browser.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False),flush=True)
