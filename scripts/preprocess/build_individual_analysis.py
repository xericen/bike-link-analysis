"""Compute full-period outputs in a dedicated process/folder; never monkeypatch a web worker."""
import argparse,csv,hashlib,json,math,os,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
def save(folder,name,value,scope):
    value={**value,"period_start":scope["start"],"period_end":scope["end"],
        "analysis_scope":"individual_full","precomputed":{"read_only":True,"revision":scope["revision"],"date_start":scope["start"],"date_end":scope["end"]},
        "scope_note":"도시별 전체 관측기간. 다른 도시의 상이한 기간과 합산하지 않음. 고정 참조 위치의 과거 동일성 미검증."}
    if name=="overview":value["coverage_note"]=scope["city"]+" 전체 이용이력 "+scope["start"]+"~"+scope["end"]+". 위치·시설·인구는 고정 참조 버전이며 과거 동일성 미검증."
    for key in ("limitations","assumptions"):
        if key in value:value[key]=[s.replace("세종 이력2025-12","세종 이력"+scope["start"]+"~"+scope["end"]) for s in value[key]]
    path=folder/(name+".json");tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",",":")));tmp.replace(path)
    print("prepared",scope["city"],name,round(path.stat().st_size/1024),flush=True)
    return value

def run(city):
    from scripts.preprocess.build_monthly_trends import sha
    processed=ROOT/"data/individual"/city
    norm=json.loads((processed/"normalization.json").read_text())
    # A completion receipt is output, not an analytical input. Keep it outside cache input globs while rebuilding.
    receipt=processed/"analysis_ready.json"
    if receipt.exists():receipt.replace(processed/".analysis-ready-previous")
    algorithm_files=sorted((ROOT/"backend/analysis").glob("*.py"))+sorted((ROOT/"backend/services").glob("*.py"))
    algorithm_revision=hashlib.sha256(b"".join(p.read_bytes() for p in algorithm_files)+Path(__file__).read_bytes()).hexdigest()
    references={p.name:sha(p) for p in processed.iterdir() if p.is_file() and p.suffix in {".csv",".json"} and p.name not in {"analysis_ready.json","quality.json","normalization.json"}}
    data_revision=sha(processed/"analysis.sqlite")
    revision=hashlib.sha256(json.dumps([data_revision,algorithm_revision,references],sort_keys=True).encode()).hexdigest()
    scope={"city":city,"start":norm["start"],"end":norm["end"],"rental_count":norm["valid_trips"],"revision":revision,"data_revision":data_revision,"algorithm_revision":algorithm_revision,"reference_sha256":references}
    out=processed/"prepared";out.mkdir(exist_ok=True)
    from backend.services import real_data,precomputed,transit,city_anchors,periods
    real_data.PROCESSED=processed;precomputed.PROCESSED=processed
    real_data.snapshot.cache_clear()
    from backend.services.kpi_projection import build
    data={}
    for action in ("overview","network","centrality","transit_linkage","vulnerability","planning","dashboard_extra","research"):
        path=out/(action+".json")
        if path.exists() and json.loads(path.read_text()).get("precomputed",{}).get("revision")==scope["revision"]:
            data[action]=json.loads(path.read_text());continue
        began=time.time();data[action]=save(out,action,build(action,city,scope["start"],scope["end"]),scope)
        print("seconds",action,round(time.time()-began,2),flush=True)
    start,end=scope["start"],scope["end"]
    profiles=real_data.profiles(city,start,end)
    stations=real_data.region_stations(city,start,end)
    clusters=real_data.clusters(city,start,end)
    ranked=real_data.centrality_result(city,start,end)
    if data["overview"]["total_rentals"]!=norm["valid_trips"]:raise RuntimeError("Total mismatch")
    save(out,"clusters",clusters,scope)
    save(out,"centrality_full",ranked,scope)
    graph=real_data.network(city,start,end,node_limit=50)
    for limit in (30,40,50):
        selected={s["station_id"] for s in graph["nodes"][:limit]}
        edges=[e for e in graph["edges"] if e["origin_station_id"] in selected and e["destination_station_id"] in selected]
        save(out,"network_"+str(limit),{**graph,"nodes":graph["nodes"][:limit],"edges":edges,"visible_edge_count":len(edges)},scope)
    imbalance=real_data.imbalance_result(city,start,end)
    save(out,"imbalance",imbalance,scope)
    save(out,"hidden_hubs",real_data.hidden_hubs(city,start,end),scope)
    save(out,"cluster_stability",real_data.cluster_stability(city,end,start),scope)
    source=real_data.source_meta(city)
    save(out,"stations",{"stations":stations,"total":len(stations),"available":True,**source},scope)
    profile_map={p["station_id"]:p for p in profiles}
    cluster_map={p["station_id"]:p for p in clusters.get("clusters",[])}
    linked_map={p["station_id"]:p for p in data["transit_linkage"]["stations"]}
    eligible=[p for p in profiles if p["rental_count"]>0 and p.get("hourly") and sum(p["hourly"])>0]
    values=np.array([[v/p["rental_count"] for v in p["hourly"]]+([p["weekend_share"]] if p.get("weekend_share") is not None else []) for p in eligible],dtype=float)
    from sklearn.metrics.pairwise import cosine_similarity
    similarities=np.round(cosine_similarity(values),5) if len(values) else np.empty((0,0))
    if len(values):np.fill_diagonal(similarities,-1)
    orders=np.argsort(-similarities,axis=1,kind="stable")[:,:10] if len(values) else []
    similarity_map={}
    for i,p in enumerate(eligible):
        rows=[]
        for j in orders[i]:
            if j==i:continue
            q=eligible[j]
            rows.append({"station_id":q["station_id"],"station_key":city+"::"+q["station_id"],"region_id":city,"station_name":q.get("station_name"),"score":float(similarities[i,j]),"rental_count":q["rental_count"],"volume_ratio":round(q["rental_count"]/p["rental_count"],3)})
        similarity_map[p["station_id"]]={"available":bool(rows),"station_id":p["station_id"],"similar":rows,**source}
    # Independently verify the vectorized batch against the existing per-station algorithm.
    from backend.analysis.similarity import station_similarity
    for p in eligible[::max(1,len(eligible)//7)][:7]:
        expected=station_similarity(profiles,p["station_id"])
        actual=similarity_map[p["station_id"]]["similar"]
        assert [(r["station_id"],r["score"]) for r in actual]==[(r["station_id"],r["score"]) for r in expected]
    buckets={i:{} for i in range(32)}
    for item in stations:
        sid=item["station_id"]
        item={**item,"region_id":city,"station_key":city+"::"+sid,"region_name":next(r["region_name"] for r in real_data.REGIONS if r["region_id"]==city)}
        buckets[sum(map(ord,sid))%32][sid]={"station":item,"profile":profile_map.get(sid),"cluster":cluster_map.get(sid),
             "transit":linked_map.get(sid),"similarity":similarity_map.get(sid,{"available":False,"similar":[]}),
             "source":source,"period_start":start,"period_end":end}
    for k,value in buckets.items():save(out,"station-bucket-"+str(k),{"items":value},scope)
    linkage=data["transit_linkage"]
    located=[s for s in linkage["stations"] if s.get("coordinate_valid") and s.get("nearest_anchor_distance_m") is not None]
    located_ids={s["station_id"] for s in located}
    active_ids={p["station_id"] for p in profiles}
    context={"city":city,"period_start":start,"period_end":end,"denominator_count":len(located),
        "analysis_station_count":data["overview"]["station_count"],"master_total":len(linkage["stations"]),
        "unlocated_master_count":len(linkage["stations"])-len(located),"denominator_only":{sid:True for sid in sorted(located_ids-active_ids)},"analysis_only":{sid:True for sid in sorted(active_ids-located_ids)},
        "denominator_note":"전체 관측기간의 이용 대여소와 고정 위치 마스터를 구분하며, 위치 미연결 이력은 공간 분모에서 제외합니다.",
        "anchor_name":city_anchors.LABELS[city],"anchor_count":len([s for s in city_anchors.stops() if s["city"]==city]),
        "source_name":city_anchors.LABELS[city]+" 고정 위치 참조","source_url":"https://www.data.go.kr/data/15118026/fileData.do" if city=="sejong" else "https://data.kric.go.kr/rips/M_01_01/detail.do?id=32","station_map_note":"고정 참조 위치 기준 · 과거 개폐소/이전 이력 미검증"}
    save(out,"presentation_context",context,scope)
    plan=data["planning"];top3=[]
    anchor_rows=[s for s in city_anchors.stops() if s["city"]==city]
    from backend.analysis.transit import match_stations
    for row in match_stations(plan.get("new_sites",[])[:3],anchor_rows):
        row.update(nearest_anchor_distance_m=row.get("nearest_stop_distance_m"),
            selection_reason=f"선택 기간 주변 1km 관측 대여 {row['nearby_rentals_1000m']:,}건·시설 {row['facilities_within_500m']}곳과 접근 공백을 결합",
            feasibility_unchecked=["설치 가능 부지","현장 통행 가능성","운영 재고/수용량"],observed_demand_label="주변 기존 대여소 관측 수요 대리변수")
        top3.append(row)
    ids=sorted(r["site_id"] for r in top3)
    union=next((s for s in plan.get("selection_states",[]) if sorted(s["selected_ids"])==ids),{"added_area_m2":0,"overlap_area_m2":0,"increase_ratio":None})
    hidden=next(iter(data["research"].get("types",{}).get("low_usage_high_connectivity",[])),None)
    if hidden:hidden={**hidden,"decision":"전체 관측 OD의 이용량·연결 순위 차이에 따른 연결 유지 검토 사례. 실제 운영 효과는 미검증."}
    quality={"silhouette":data["dashboard_extra"].get("silhouette"),"quality":clusters.get("quality")}
    decision={"available":True,"city":city,"matches_selected_period":True,"selected_period":{"start":start,"end":end},
        "top3":top3,"top3_union":union,"hidden_hub":hidden,"pattern_case":None,"cluster_quality":quality,
        "cluster_decision":clusters.get("message","군집 품질 확인 필요"),"planning_scope":"전체 기간 관측 수요에 기반한 공간 모델이며 설치 후 효과 예측이 아닙니다.",
        "route_audit":[],"route_limitations":["확장 기간의 새 후보에 대한 추가 도로망 감사는 미실행. 기존12월 사례를 대체 근거로 쓰지 않음."],
        "agent_evaluation":None,"transfer_audit":{"definition_status":"unverified","actual_transfer_rate":None,"message":"실제 환승 여부 정의 미검증. 공간상 연계 가능성만 계산."}}
    save(out,"decision_evidence",decision,scope)
    # Only Seoul has matching rail demand for the full selected window.
    demand={"available":False,"city":city,"message":"전체 관측기간과 일치하는 지하철/BRT 승하차 자료가 없어 비교하지 않습니다. 공통12월은 전체 선택에서 조회할 수 있습니다."}
    if city=="seoul":
        try:
            import pandas as pd
            from scripts.preprocess.build_transit_demand import find_file,read_rail,city_comparison,nfc
            uploads=ROOT.parent/".reviewops-bike-publish"
            bigdata=next(p for p in uploads.iterdir() if p.is_dir() and nfc(p.name)=="빅데")
            rail_path=find_file(bigdata,("2025","서울","승강차실적"),".xls")
            rail,metadata=read_rail(rail_path,2025)
            rail["boardings_12"]=rail[[f"boardings_{m:02}" for m in range(1,13)]].sum(axis=1)
            rail["alightings_12"]=rail[[f"alightings_{m:02}" for m in range(1,13)]].sum(axis=1)
            table=pd.DataFrame(real_data.snapshot()["stations"])
            usage=pd.DataFrame(profiles)[["station_id","rental_count","return_count"]]
            table=table.merge(usage,on="station_id",how="left").fillna({"rental_count":0,"return_count":0})
            demand=city_comparison(city,rail,pd.read_csv(processed/"transit_anchors.csv"),table)
            demand["limitations"]=["2025년1~12월 역별 월 합계 합산이며 시간대 승하차가 아닙니다.","역 인근 자전거 활동은 실제 환승·인과관계가 아닙니다.","여러 역 반경의 대여소는 각 역에 포함되므로 역별 자전거 합계를 도시 총량으로 합산하지 않습니다."]
            demand["source_file"]=metadata
            demand["source_sha256"]=sha(rail_path)
        except (FileNotFoundError,StopIteration,ValueError) as e:
            demand["message"]="동일 기간 승하차 원본 연결 미확인: "+type(e).__name__
    save(out,"transit_demand",demand,scope)
    scope.update(actions=[p.stem for p in out.glob("*.json")],observed_days=norm["observed_days"],station_count=len(stations),valid_graph_trip_count=ranked.get("valid_graph_trip_count"),completed_at=datetime.now(timezone.utc).isoformat())
    (processed/"analysis_ready.json").write_text(json.dumps(scope,ensure_ascii=False,indent=2))
    print("READY",city,scope["rental_count"],flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--city",required=True,choices=["seoul","daejeon","sejong"]);args=p.parse_args();run(args.city)
