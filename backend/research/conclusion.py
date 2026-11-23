"""Stored conclusions with explicit common-month / individual scope and no live LLM or routing."""
import copy,json
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[2];FILE=ROOT/"docs/conclusion-20261123/results.json"
@lru_cache(maxsize=2)
def _load(stamp,size):return json.loads(FILE.read_text())
def read(city="all",scope=None):
    if city not in {"all","seoul","daejeon","sejong"}:raise HTTPException(404,"지원하지 않는 도시입니다.")
    scope=scope or ("common" if city=="all" else "individual")
    if scope not in {"common","individual"} or city=="all" and scope!="common":raise HTTPException(422,"전체 결론은 공통 관측10개월을 사용합니다.")
    if not FILE.exists():raise HTTPException(409,"결론의 관측 자료·경로 점검을 준비 중입니다.")
    report=_load(FILE.stat().st_mtime_ns,FILE.stat().st_size)
    for rel,meta in report["inputs"].items():
        p=ROOT/rel
        if not p.exists() or (p.stat().st_size,p.stat().st_mtime_ns)!=(meta["size"],meta["mtime_ns"]):raise HTTPException(409,"결론 입력이 변경되어 재검증이 필요합니다.")
    packets=copy.deepcopy([r for r in report[scope+"_cities"] if city=="all" or r["city"]==city])
    from backend.presentation.individual import scope as current_scope
    for row in packets:
        if row["source_revision"]!=current_scope(row["city"])["revision"]:raise HTTPException(409,"기존 분석 버전과 결론의 기준이 다릅니다.")
    for row in packets:
        for site in row["candidates"]:
            site["route_data_dates"]=sorted({r["retrieved_at"][:10] for r in site["route"].values() if isinstance(r,dict) and r.get("retrieved_at")})
            route=site["route"]
            if route["status"]!="model_connected":site["action"]="연결 경로 추가 확인 후 판단"
            elif route.get("improvement_minutes") is None:site["action"]="직접 도보 경로를 추가 확인한 뒤 판단"
            elif route["improvement_minutes"]<=0:site["action"]="도보 대비 시간 보완 근거가 없어 우선도 재검토"
            else:site["action"]="연계 시간 단축 가능성이 있어 현장 검토"
    import importlib
    from backend.research import final_validation
    importlib.reload(final_validation).enrich(packets,scope)
    common=[]
    for month in report["common_months"]:
        cities={}
        for row in report["common_cities"]:
            r=next(r for r in row["months"] if r["month"]==month)
            cities[row["city"]]={"daily_average":r["daily_average"],"anchor_linked_ratio":r["anchor_linked_ratio"],
                "rental_count":r["rental_count"],"observed_days":r["observed_days"],"unknown_endpoint_ratio":r["unknown_endpoint_trips"]/r["rental_count"] if r["rental_count"] else None}
        common.append({"month":month,"cities":cities})
    from backend.research.project_goals import conclusions
    goal_results=conclusions(packets)
    final_validation.supplement_goals(goal_results)
    from backend.research import completion
    importlib.reload(completion).apply(packets,goal_results,scope)
    from backend.research import evidence_dashboard
    dashboard=importlib.reload(evidence_dashboard).build(city)
    if dashboard.get("seoul_transfer"):
        goal_results["items"][3]["evidence"]+=" 추가 확보한2025-09-30 서울 공식 시간표로 종로3가5→1호선 환승6개 시나리오도 계산했습니다. 관측기간과 별도 참조 결과입니다."
        goal_results["items"][3]["remaining"]="전체 여정의 실측 검증은 미완료입니다. 대전은 현행 단일노선, 서울은2025-09-30 공개본의 두 노선 대표 모델이며12월 실제 시행 여부·환승보행·세종BRT 중간도착시각·재고는 추가 확인이 필요합니다."
    return copy.deepcopy({"evidence_dashboard":dashboard,"project_goals":goal_results,"available":True,"city":city,"scope":"common_multi_month" if scope=="common" else "individual_full",
      "period_label":report["common_label"] if scope=="common" else packets[0]["period_label"],
      "period_start":packets[0]["period_start"],"period_end":packets[0]["period_end"],"common_label":report["common_label"],
      "common_months":report["common_months"],"comparison":common,"cities":packets,"built_at":report["built_at"],
      "attribution":report["attribution"],"route_source":report["route_source"],"limitations":report["limitations"],
      "facts_basis":"서버에서 계산·검증한 관측값과 경로 점검 결과. AI 자유 생성 결론 아님.","operational_update":False})
def tool(city,start=None,end=None,scope=None):
    from backend.presentation.individual import matches
    if scope=="common":
        result=read(city,"common")
        result["reference_scope"]=True
        result["selected_context_period"]={"start":start,"end":end}
        result["scope_note"]="명시적으로 요청한 별도 공통10개월 결론. 현재 선택 기간을 대체하거나 합산하지 않습니다."
    elif city!="all" and (start is None and end is None or matches(city,start,end)):
        result=read(city,"individual")
    else:return {"available":False,"message":"선택 기간과 전체기간 결론이 다릅니다. 공통10개월 결론은 scope=common으로 명시하고 별도 결과로 설명하세요."}
    result.pop("evidence_dashboard",None) # Technical proof/reference views have their own periods; do not mix into selected-scope AI facts.
    for c in result["cities"]:
        for row in c["candidates"]:
            row.pop("monthly_ranks",None)
            for route in row["route"].values():
                if isinstance(route,dict):route.pop("geometry",None)
    if result["scope"]=="individual_full":
        result.pop("comparison",None)
    elif city!="all":
        for row in result["comparison"]:row["cities"]={city:row["cities"][city]}
    result["sources"]=[{"dataset_name":"공통 월별 실제 이용 집계·신규 후보 월별 재계산·현재 OSM 연결 경로 점검","source_url":"https://routing.openstreetmap.de/about.html"}]
    return result
