"""Read-only multi-month comparison, fixed-method candidate recurrence and current-road connection checks."""
import csv,hashlib,json,math,sqlite3,time
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import requests
from sklearn.neighbors import BallTree
from backend.research import method_validation as m
from backend.presentation import individual,monthly_trends
from scripts.validate.build_advanced_research import source
from scripts.collect.audit_candidate_routes import metres,UA
ROOT=m.ROOT;OUT=ROOT/"docs/conclusion-20261123";CACHE=ROOT/"data/raw/route-audit"
CITIES=("seoul","daejeon","sejong")
class Router:
    def __init__(self):self.last=0;self.failures=0;self.requests=0
    def get(self,mode,a,b):
        profile="foot" if mode=="foot" else "cycling"
        url=f"https://routing.openstreetmap.de/routed-{mode}/route/v1/{profile}/{a[1]},{a[0]};{b[1]},{b[0]}"
        path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+".json");CACHE.mkdir(parents=True,exist_ok=True)
        if path.exists():body=json.loads(path.read_text())
        else:
            if self.failures>=3:return {"status":"unavailable","reason":"provider_circuit_breaker"}
            time.sleep(max(0,1.1-(time.monotonic()-self.last)))
            try:
                self.requests+=1
                response=requests.get(url,params={"overview":"simplified","geometries":"geojson","steps":"false"},headers={"User-Agent":UA},timeout=20)
                response.raise_for_status();body=response.json();body["_retrieved_at"]=datetime.now(timezone.utc).isoformat()
                path.write_text(json.dumps(body,ensure_ascii=False));self.failures=0
            except (requests.RequestException,ValueError) as e:
                self.failures+=1;return {"status":"unavailable","error_type":type(e).__name__}
            finally:self.last=time.monotonic()
        if body.get("code")!="Ok" or not body.get("routes"):return {"status":"no_route","provider_code":body.get("code")}
        route=body["routes"][0];snaps=[float(w["distance"]) for w in body["waypoints"]]
        if len(snaps)!=2:return {"status":"unavailable","reason":"waypoints_shape"}
        return {"status":"ok" if max(snaps)<=50 else "snap_uncertain","distance_m":float(route["distance"]),"duration_s":float(route["duration"]),
          "snap_distances_m":snaps,"retrieved_at":body.get("_retrieved_at"),"geometry":route.get("geometry"),
          "source_url":"https://routing.openstreetmap.de/about.html","response_sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False));tmp.replace(path)
def rank_months(city,folder,stations,candidates,history):
    with sqlite3.connect((folder/"analysis.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as conn:
        rows=conn.execute("SELECT substr(date,1,7),station_id,SUM(rental_count) FROM station_usage WHERE region_id=? GROUP BY 1,2",(city,)).fetchall()
    counts=defaultdict(dict)
    for month,sid,n in rows:counts[month][sid]=int(n)
    for month in history["months"]:assert sum(counts[month["month"]].values())==month["rental_count"],(city,month["month"])
    located=[r for r in stations if r.get("coordinate_valid")]
    tree=BallTree(np.radians([[r["latitude"],r["longitude"]] for r in located]),metric="haversine")
    neighbors=tree.query_radius(np.radians([[r["latitude"],r["longitude"]] for r in candidates]),r=1000/m.EARTH_M)
    ranked={};facts={}
    for month in history["months"]:
        key=month["month"];values=counts[key]
        rows=[]
        for r,ix in zip(candidates,neighbors):
            n=sum(values.get(located[int(i)]["station_id"],0) for i in ix)
            facts[key,r["site_id"]]=n
            if n>0 or r["facilities_within_500m"]>0:rows.append({**r,"nearby_rentals_1000m":n})
        ranked[key]=m.rank_candidates(rows,use_population=city!="sejong")[0]
    return counts,ranked,facts
def route_candidate(row,stations,anchors,router):
    point=(row["latitude"],row["longitude"])
    anchor=min(anchors,key=lambda r:metres(point,(float(r["lat"]),float(r["lon"]))))
    target=(float(anchor["lat"]),float(anchor["lon"]))
    docking=[r for r in stations if r.get("coordinate_valid") and (r.get("rental_count") or 0)>0 and metres((r["latitude"],r["longitude"]),target)<=300]
    base={"anchor_id":anchor["stop_id"],"anchor_name":anchor["name"],"anchor_latitude":target[0],"anchor_longitude":target[1],
       "straight_to_anchor_m":metres(point,target),"before_walk":router.get("foot",point,target),
       "field_installation_verified":False,"current_osm_only":True}
    if not docking:return {**base,"status":"anchor_dock_missing","message":"이 기간 이용과 위치가 확인된 앵커300m 내 반납 대여소가 없습니다.","after_minutes":None,"improvement_minutes":None}
    dock=min(docking,key=lambda r:(metres((r["latitude"],r["longitude"]),target),r["station_id"]))
    p=(dock["latitude"],dock["longitude"])
    bike=router.get("bike",point,p);walk=router.get("foot",p,target)
    ok=bike["status"]=="ok" and walk["status"]=="ok"
    after=(bike["duration_s"]+walk["duration_s"]+120)/60 if ok else None
    before=base["before_walk"].get("duration_s")/60 if base["before_walk"]["status"]=="ok" else None
    return {**base,"status":"model_connected" if ok else "route_unconfirmed","dock_station_id":dock["station_id"],"dock_station_name":dock.get("station_name"),
       "dock_latitude":p[0],"dock_longitude":p[1],"bike_to_dock":bike,"walk_to_anchor":walk,
       "assumed_pickup_return_seconds":120,"after_minutes":after,"before_minutes":before,
       "improvement_minutes":before-after if before is not None and after is not None else None,
       "message":"현 도로망 모델의 연결 확인. 실제 통행·거치 가능 용량·현장 설치·과거 경로는 미검증." if ok else "경로 또는 좌표 접속을 확인하지 못해 연결 효과 판정을 보류합니다."}
def shortlist(rows,scope_months,ranked,stations,anchors,router):
    allowed=[mo["month"] for mo in scope_months if mo["complete"]]
    result=[]
    for r in rows[:3]:
        appearances=[]
        for month in allowed:
            found=next((q for q in ranked[month] if q["site_id"]==r["site_id"]),None)
            if found:appearances.append({"month":month,"rank":found["rank"],"nearby_rentals_1000m":found["nearby_rentals_1000m"]})
        route=route_candidate(r,stations,anchors,router)
        result.append({**r,"observed_demand_label":"주변1km 기존 대여소의 관측 대여. 신규 수요 예측 아님.",
          "eligible_months":len(allowed),"top10_months":sum(q["rank"]<=10 for q in appearances),
          "monthly_ranks":appearances,"rank_range":[min(q["rank"] for q in appearances),max(q["rank"] for q in appearances)] if appearances else None,
          "route":route,"action":"경로가 확인된 공간 후보로 현장 검토" if route["status"]=="model_connected" else "연결 경로 추가 확인 후 판단",
          "unchecked":["실제 설치 가능 부지·허가","현장 보행/자전거 통행","과거 위치 동일성","반납 거치 용량·자전거 재고","설치 후 실제 이용·환승 변화"]})
        print("route",r["site_id"],route["status"],flush=True)
    return result
def run():
    OUT.mkdir(parents=True,exist_ok=True);router=Router()
    history={c:json.loads((ROOT/"data/reference/monthly_trends"/(c+".json")).read_text()) for c in CITIES}
    common=sorted(set.intersection(*[{r["month"] for r in history[c]["months"] if r["month"].startswith("2025") and r["complete"]} for c in CITIES]))
    assert common==["2025-01"]+["2025-"+str(m).zfill(2) for m in range(4,13)]
    report={"schema":1,"built_at":datetime.now(timezone.utc).isoformat(),"common_months":common,
       "common_label":"2025년 1월·4~12월 · 공통 10개월","scope_note":"기존 전체12월·개별전체 분석은 보존. 이 결론의 도시 비교만 동일한 완전 관측10개월을 별도 사용.",
       "operational_update":False,"common_cities":[],"individual_cities":[],"inputs":{},
       "route_source":"https://routing.openstreetmap.de/about.html","attribution":"© OpenStreetMap contributors; FOSSGIS OSRM",
       "limitations":["월 완전성은 관측 날짜 기준이며 개별 기록·좌표의 완전성을 보증하지 않음.","연계 비중은 앵커 근접 OD이며 실제 환승률이 아님.",
          "모든 공간 참조는 고정 버전. 과거 개폐소·이전·시설 시점은 미검증.","도로망은 현재 OSM 모델이고 실제 통행시간·설치 효과가 아님.",
          "최근접 직선 앵커와 그 앵커300m 내 최근접 이용 대여소를 점검한 경로이며 전 앵커/반납소의 최적 경로를 탐색하지 않음.",
          "승하차·재고·용량 없는 항목은 추정하지 않음. 재배치는 검토 대상까지만 제시."]}
    for city in CITIES:
        print("monthly",city,flush=True)
        scope,folder,data,boundary,districts,facilities,anchors=source(city,"individual")
        from shapely.geometry import Point
        from shapely.ops import unary_union
        baseline=unary_union([Point(*m.PROJECT(a["lon"],a["lat"])).buffer(500,quad_segs=16) for a in anchors]).intersection(boundary)
        candidates,_=m.grid_candidates(boundary,baseline,data["stations"],facilities,districts,use_population=city!="sejong")
        counts,ranked,_=rank_months(city,folder,data["stations"],candidates,history[city])
        summary_months=[r for r in history[city]["months"] if r["month"] in common]
        metrics=monthly_trends.summarize(summary_months)
        assert metrics["observed_days"]==306
        by_station=defaultdict(int)
        for month in common:
            for sid,n in counts[month].items():by_station[sid]+=n
        common_stations=[{**r,"rental_count":by_station.get(r["station_id"],0)} for r in data["stations"]]
        located=[r for r in common_stations if r.get("coordinate_valid")]
        tree=BallTree(np.radians([[r["latitude"],r["longitude"]] for r in located]),metric="haversine")
        near=tree.query_radius(np.radians([[r["latitude"],r["longitude"]] for r in candidates]),r=1000/m.EARTH_M)
        common_candidates=[]
        for r,ix in zip(candidates,near):
            n=sum(located[int(i)]["rental_count"] for i in ix)
            if n or r["facilities_within_500m"]:common_candidates.append({**r,"nearby_rentals_1000m":n})
        common_ranked=m.rank_candidates(common_candidates,use_population=city!="sejong")[0]
        canonical=individual.read(city,"planning")["new_sites"][:3]
        full_ids=[r["site_id"] for r in candidates[:3]]
        assert full_ids==[r["site_id"] for r in canonical],(city,"full-period canonical ranking")
        for kind,rows,stations,months in [("common",common_ranked,common_stations,summary_months),("individual",canonical,data["stations"],history[city]["months"])]:
            key=kind+"-"+city;checkpoint=OUT/(key+".json")
            reference_files=[ROOT/"data/reference/monthly_trends"/(city+".json"),ROOT/"data/processed/transit_anchors.csv",ROOT/"data/processed/planning_population.json",ROOT/"data/processed"/("planning_boundary_"+city+".json"),folder/("planning_facilities_"+city+".json"),Path(m.__file__),Path(__file__)]
            references={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in reference_files}
            db=folder/"analysis.sqlite"
            signature=hashlib.sha256(json.dumps([rows[:3],scope["revision"],references,db.stat().st_size,db.stat().st_mtime_ns],sort_keys=True).encode()).hexdigest()
            if checkpoint.exists():
                packet=json.loads(checkpoint.read_text());assert packet["signature"]==signature
            else:
                packet={"signature":signature,"city":city,"scope":kind,"period_start":"2025-01-01" if kind=="common" else scope["start"],
                  "period_end":"2025-12-31" if kind=="common" else scope["end"],"period_label":report["common_label"] if kind=="common" else scope["start"]+" ~ "+scope["end"],
                  "scope_months":[r["month"] for r in months],"selection_rule":"기존 균등 점수 유지. 해당 기간 관측 수요로 재계산한 신규 입지 상위3곳. 실제 설치 권고 확정 아님.",
                  "candidates":shortlist(rows,months,ranked,stations,anchors,router),"source_revision":scope["revision"]}
                save(checkpoint,packet)
            packet["model_connected_count"]=sum(r["route"]["status"]=="model_connected" for r in packet["candidates"])
            packet["positive_time_scenario_count"]=sum((r["route"].get("improvement_minutes") or 0)>0 for r in packet["candidates"])
            packet["time_threshold_sensitivity"]=[{"minutes":n,"candidate_count":sum(r["route"].get("after_minutes") is not None and r["route"]["after_minutes"]<=n for r in packet["candidates"]),"evaluated":packet["model_connected_count"]} for n in (10,15,20)]
            if kind=="common":
                packet["metrics"]=metrics;packet["months"]=summary_months
                maxmo=max(summary_months,key=lambda r:r["daily_average"]);minmo=min(summary_months,key=lambda r:r["daily_average"])
                packet["findings"]=[f"비교한10개월 중 {maxmo['month']}의 하루 평균 이용이 가장 많고 {minmo['month']}가 가장 적었습니다.",
                   f"역·BRT 근접 이용 비중은 {metrics['anchor_linked_ratio']*100:.2f}%이며 실제 환승률은 아닙니다."]
            else:
                packet["findings"]=[f"보유 전체 기간의 기존 신규 후보3곳 중 {packet['model_connected_count']}곳에서 반납 대여소를 거쳐 교통 거점으로 가는 현 도로망 모델 경로를 확인했습니다.",
                   "월별 재등장은 후보의 반복성 근거이며 설치 효과·신규 수요 예측은 아닙니다."]
            packet["findings"].append(f"우선 검토3곳 중 {packet['positive_time_scenario_count']}곳은 자전거 이용·반납2분 가정을 포함한 경로 모델 시간이 직접 도보보다 짧았습니다.")
            report[kind+"_cities"].append(packet)
        for path in (ROOT/"data/reference/monthly_trends"/(city+".json"),folder/"analysis.sqlite",folder/"stations.csv",folder/"transit_anchors.csv",ROOT/"data/processed/transit_anchors.csv",ROOT/"data/processed/planning_population.json",ROOT/"data/processed"/("planning_boundary_"+city+".json"),folder/("planning_facilities_"+city+".json")):
            report["inputs"][str(path.relative_to(ROOT))]={"size":path.stat().st_size,"mtime_ns":path.stat().st_mtime_ns}
    report["routing_requests"]=router.requests
    report["code_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save(OUT/"results.json",report)
    print("READY conclusion",router.requests,flush=True)
if __name__=="__main__":run()
