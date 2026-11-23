"""Strict full-period prepared reads. Never changes the shared common-period services."""
import copy,json
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/"data/reference/individual_scopes.json"
ALLOWED={"overview","network","centrality","centrality_full","transit_linkage","vulnerability","planning","dashboard_extra","research","clusters","imbalance","hidden_hubs","cluster_stability","stations","presentation_context","decision_evidence","transit_demand","network_30","network_40","network_50"}

def scopes():
    if not MANIFEST.exists():return {"ready":False,"regions":{}}
    return json.loads(MANIFEST.read_text())

def scope(city):
    value=scopes()
    if not value.get("ready") or city not in value.get("cities",{}):raise HTTPException(409,"개별 전체 기간 사전 집계가 준비되지 않았습니다.")
    return value["cities"][city]

def matches(city,start,end):
    try:s=scope(city)
    except HTTPException:return False
    return start==s["start"] and end==s["end"]

def folder(city):
    s=scope(city)
    for root in (ROOT/"frontend/public/assets/bike-link/individual",):
        path=root/s["asset_path"]
        if path.exists():return path
    raise HTTPException(409,"전체 기간 준비 파일을 찾을 수 없습니다.")

@lru_cache(maxsize=128)
def _json(path,stamp,size):
    return json.loads(Path(path).read_text())

def packet(city,action):
    if action not in ALLOWED and not (action.startswith("station-bucket-") and action.removeprefix("station-bucket-").isdigit()):
        raise HTTPException(404,"지원하지 않는 전체 기간 조회입니다.")
    path=folder(city)/(action+".json")
    if not path.exists():raise HTTPException(409,"선택 분석의 사전 집계가 없습니다: "+action)
    return copy.deepcopy(_json(str(path),path.stat().st_mtime_ns,path.stat().st_size))

def station(city,sid):
    if not isinstance(sid,str) or not sid:raise HTTPException(422,"대여소 ID가 필요합니다.")
    if "::" in sid:
        prefix,sid=sid.split("::",1)
        if prefix!=city:raise HTTPException(422,"다른 도시의 대여소입니다.")
    value=packet(city,"station-bucket-"+str(sum(map(ord,sid))%32))["items"].get(sid)
    if value is None:raise HTTPException(404,"전체 기간 자료에 없는 대여소입니다.")
    return value

def read(city,action,params=None):
    params=params or {};s=scope(city)
    start=params.get("date_start") or s["start"];end=params.get("date_end") or s["end"]
    if (start,end)!=(s["start"],s["end"]):raise HTTPException(422,"이 조회는 검증된 도시별 전체 기간만 제공합니다. 다른 기간으로 대체하지 않습니다.")
    if action=="prepared_periods":return {"region_id":city,"periods":[{"start":start,"end":end,"scope":"individual_full"}]}
    if action=="readiness":return {"ready":True,"cities":{city:{"ready":True,"aggregates_ready":True,"decision_evidence_ready":True,"date_start":start,"date_end":end,"actions":s["actions"]}},"revision":s["revision"]}
    if action=="station":return station(city,params.get("station_id",""))
    if action=="stations":
        result=packet(city,"stations");query=str(params.get("query") or params.get("q") or "").lower().strip()
        rows=result["stations"]
        if query:rows=[r for r in rows if query in ((r.get("station_name") or "")+" "+r["station_id"]).lower()]
        rows.sort(key=lambda r:-(r.get("rental_count") or 0))
        limit=max(1,min(10000,int(params.get("limit",50))))
        return {**result,"stations":rows[:limit],"total":len(rows)}
    if action=="planning_scenario":
        ids=params.get("selected_ids",[])
        if isinstance(ids,str):ids=json.loads(ids)
        if not isinstance(ids,list) or len(ids)>6 or any(not isinstance(i,str) for i in ids):raise HTTPException(422,"후보 ID는 최대6개입니다.")
        selected=sorted(set(ids))
        plan=packet(city,"planning")
        for state in plan.get("selection_states",[]):
            if state["selected_ids"]==selected:return {**state,"city":city,"date_start":start,"date_end":end}
        raise HTTPException(422,"현재 전체 기간 후보에 없는 선택입니다.")
    if action in {"station_history","station_validation"}:
        return {"available":False,"station_id":params.get("station_id"),"period_start":start,"period_end":end,"windows":[],"message":"개별 대여소의 추가 단기창 검증은 미준비입니다. 전체 기간 프로파일과 군집·중심성은 준비되어 있습니다."}
    alias={"transit_vulnerability":"vulnerability"}
    result=packet(city,alias.get(action,action))
    if action=="transit_vulnerability":result["cities"]=[copy.deepcopy(result)]
    return result

def tool(name,arguments,context):
    city=arguments.get("region_id")
    dates=context or arguments.get("date_range") or {}
    start=dates.get("date_start");end=dates.get("date_end")
    if not matches(city,start,end):return None
    n=arguments.get("top_n",10)
    if type(n) is not int or not 1<=n<=20:raise HTTPException(422,"top_n은1~20입니다.")
    mapping={"get_region_overview":"overview","get_network_analysis":"network","get_station_clusters":"clusters",
        "get_centrality_ranking":"centrality_full","get_transit_linkage":"transit_linkage","get_transit_vulnerability":"vulnerability","get_improvement_ranking":"vulnerability",
        "get_site_planning":"planning","get_relocation_candidates":"planning","get_role_candidates":"research","get_station_imbalance":"imbalance",
        "get_hidden_hubs":"hidden_hubs","get_cluster_stability":"cluster_stability","get_decision_evidence":"decision_evidence","get_transit_demand_comparison":"transit_demand","get_data_availability":"overview"}
    if name=="get_city_monthly_trends":return None
    if name in {"get_station_details","find_similar_stations"}:
        result=station(city,arguments.get("station_id",""))
        if name=="find_similar_stations":return {**result["similarity"],"similar":result["similarity"]["similar"][:n],"period_start":start,"period_end":end}
        return {**result,"available":True,"observed_dates":packet(city,"overview").get("observed_dates")}
    if name in {"get_hidden_hub_validation","get_station_role_history"}:return read(city,"station_validation",arguments)
    if name not in mapping:return {"available":False,"message":"전체 기간에 준비되지 않은 도구입니다. 공통12월 값으로 대체하지 않습니다.","period_start":start,"period_end":end}
    if name=="get_network_analysis":
        filters=arguments.get("filters",{})
        if not isinstance(filters,dict) or set(filters)-{"node_limit"} or filters.get("node_limit",30) not in (30,40,50):raise HTTPException(422,"node_limit은30,40,50입니다.")
        return packet(city,"network_"+str(filters.get("node_limit",30)))
    result=read(city,mapping[name])
    if name=="get_region_overview":result.pop("map_stations",None)
    if name=="get_station_clusters":result={**result,"clusters":result.get("clusters",[])[:20],"returned_count":min(20,len(result.get("clusters",[])))}
    if name=="get_centrality_ranking":
        metric=arguments.get("metric","pagerank").replace("page_rank","pagerank")
        if metric not in {"pagerank","weighted_in_degree","weighted_out_degree","betweenness"}:raise HTTPException(422,"지원하지 않는 중심성입니다.")
        result["rankings"]=sorted(result["rankings"],key=lambda r:-(r.get(metric) or 0))[:n]
    if name in {"get_transit_vulnerability","get_improvement_ranking"}:
        result.pop("candidates",None);result["ranking"]=result.get("ranking",[])[:n];result["first_last_mile_candidates"]=result.get("first_last_mile_candidates",[])[:n]
    if name=="get_transit_linkage":
        result={k:result.get(k) for k in ("available","city","period_start","period_end","goal_metrics","hourly_station_linkage","sources","limitations")}
    if name=="get_transit_demand_comparison":result["stations"]=result.get("stations",[])[:n]
    if name=="get_decision_evidence":
        result.pop("agent_evaluation",None)
        result["top3_union"]={k:v for k,v in result.get("top3_union",{}).items() if k!="added_geometry"}
    if name=="get_station_imbalance":result["stations"]=sorted(result["stations"],key=lambda r:-abs(r.get("net_outflow") or 0))[:n]
    if name=="get_hidden_hubs":result["candidates"]=result.get("candidates",[])[:n]
    if name=="get_role_candidates":result["types"]={k:v[:5] for k,v in result.get("types",{}).items()}
    if name=="get_site_planning":
        result={k:v for k,v in result.items() if k not in {"coverage_features","boundary","gap_grid","selection_states","scenario_pool"}}
        result["new_sites"]=result.get("new_sites",[])[:n]
        if context and context.get("selected_candidates"):
            result["selected_candidates"]=context["selected_candidates"];result["selected_scenario"]=context.get("selected_scenario")
    if name=="get_relocation_candidates":result={**result.get("relocation",{}),"city":city,"period_start":start,"period_end":end}
    return result

def context(city,start,end,selection=None):
    s=scope(city)
    if (start,end)!=(s["start"],s["end"]):raise HTTPException(422,"전체 기간과 요청 기간이 다릅니다.")
    from backend.presentation.selection import selection_context
    rows=packet(city,"stations")["stations"]
    return selection_context(city,start,end,selection,reader=lambda action,rid,a,b:read(rid,action,{"date_start":a,"date_end":b}),stations=rows)
