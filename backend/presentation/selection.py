"""Validated UI selection context. Reads stored results only; never computes new KPIs."""
import json
from fastapi import HTTPException

def selection_context(city,start,end,selection=None,reader=None,stations=None):
    from backend.services import precomputed,real_data
    reader=reader or precomputed.read
    if isinstance(selection,str):
        if len(selection)>6000:raise ValueError("선택 맥락이 너무 큽니다.")
        try:selection=json.loads(selection)
        except (TypeError,ValueError):raise ValueError("선택 맥락 JSON이 올바르지 않습니다.")
    selection=selection or {}
    if not isinstance(selection,dict):raise ValueError("선택 맥락은 객체여야 합니다.")
    cities=["seoul","daejeon","sejong"] if city=="all" else [city]
    context={"region_ids":cities,"date_start":start,"date_end":end,
             "scope_note":"서울·대전·세종 공통 2025-12 기간을 통합합니다." if city=="all" else "선택 도시·기간의 실제 기록 기준입니다.",
             "selected_station":None,"selected_candidates":[],"selected_scenario":None}
    station=selection.get("station")
    if station is not None:
        if not isinstance(station,dict):raise ValueError("대여소 선택 형식이 올바르지 않습니다.")
        rid=station.get("region_id");sid=station.get("station_id")
        if rid not in cities or not isinstance(sid,str):raise ValueError("선택 대여소의 도시가 분석 범위와 다릅니다.")
        items=stations if stations is not None else real_data.snapshot()["stations"]
        found=next((s for s in items if s.get("region_id")==rid and s.get("station_id")==sid),None)
        if not found:raise ValueError("실제 대여소 마스터에 없는 ID입니다.")
        context["selected_station"]={k:found.get(k) for k in ("region_id","station_id","station_name")}
    ids=selection.get("candidate_ids",[])
    if not isinstance(ids,list) or len(ids)>6 or any(not isinstance(s,str) for s in ids):
        raise ValueError("선택 후보는 최대 6개의 실제 후보 ID여야 합니다.")
    ids=sorted(set(ids))
    if ids:
        rid=selection.get("candidate_city")
        if rid not in cities:raise ValueError("선택 후보의 도시가 분석 범위와 다릅니다.")
        plan=reader("planning",rid,start,end)
        pool={r["site_id"]:r for r in plan.get("scenario_pool",[])}
        if any(sid not in pool for sid in ids):raise ValueError("현재 도시·기간에 없는 시나리오 후보입니다. 후보를 다시 선택하세요.")
        fields=("site_id","station_id","station_name","kind","rank","district","rental_count","nearest_stop_distance_m","potential_added_area_m2","score")
        context["selected_candidates"]=[{**{k:pool[sid][k] for k in fields if k in pool[sid]},"region_id":rid} for sid in ids]
        state=next((r for r in plan.get("selection_states",[]) if sorted(r["selected_ids"])==ids),None)
        if state is None:raise ValueError("선택 조합의 사전 계산 시나리오가 없습니다.")
        context["selected_scenario"]={k:state[k] for k in ("selected_ids","added_area_m2","overlap_area_m2","increase_ratio")}
        context["selection_source"]={"city":rid,"date_start":start,"date_end":end,"precomputed":plan.get("precomputed")}
    return context
