"""Read-only follow-up: held-out shared-feature ranking and bounded route alternatives."""
import json,sqlite3,hashlib,time
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import networkx as nx
from sklearn.neighbors import BallTree
from scripts.validate.build_conclusion import source,rank_months,Router,route_candidate,metres,save
from backend.research import method_validation as m
ROOT=m.ROOT;OUT=ROOT/"docs/final-validation-20261123"
TRAIN=["2025-01","2025-04","2025-05","2025-06"]
TEST=["2025-"+str(i).zfill(2) for i in range(7,13)]
class BoundedRouter(Router):
    def get(self,mode,a,b):
        profile="foot" if mode=="foot" else "cycling"
        url=f"https://routing.openstreetmap.de/routed-{mode}/route/v1/{profile}/{a[1]},{a[0]};{b[1]},{b[0]}"
        cache=ROOT/"data/raw/route-audit"/(hashlib.sha256(url.encode()).hexdigest()+".json")
        if not cache.exists() and self.requests>=30:
            return {"status":"unavailable","reason":"new_request_budget_exhausted"}
        return super().get(mode,a,b)
def temporal(city,folder,stations,candidates,history):
    counts,ranked,_=rank_months(city,folder,stations,candidates,history)
    # Same three features in all cities: facilities, observed nearby demand, gap ratio.
    shared={month:m.rank_candidates(rows,use_population=False)[0] for month,rows in ranked.items()}
    indexed={month:{r["site_id"]:r for r in rows} for month,rows in shared.items()}
    def pooled(months):
        rows=[]
        for r in candidates:
            n=sum(indexed[mo].get(r["site_id"],{}).get("nearby_rentals_1000m",0) for mo in months)
            if n or r["facilities_within_500m"]:rows.append({**r,"nearby_rentals_1000m":n})
        return m.rank_candidates(rows,use_population=False)[0]
    train=pooled(TRAIN);test=pooled(TEST)
    with sqlite3.connect((folder/"analysis.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
        edges=db.execute("SELECT origin_station_id,destination_station_id,SUM(trip_count) FROM od_daily WHERE region_id=? AND substr(date,1,7) IN (?,?,?,?) GROUP BY 1,2",(city,*TRAIN)).fetchall()
    graph=nx.DiGraph()
    graph.add_weighted_edges_from((a,b,int(n)) for a,b,n in edges)
    pr=nx.pagerank(graph,weight="weight")
    located=[r for r in stations if r.get("coordinate_valid")]
    tree=BallTree(np.radians([[r["latitude"],r["longitude"]] for r in located]),metric="haversine")
    nearby=tree.query_radius(np.radians([[r["latitude"],r["longitude"]] for r in train]),r=1000/m.EARTH_M)
    signals={r["site_id"]:sum(pr.get(located[int(j)]["station_id"],0) for j in ix) for r,ix in zip(train,nearby)}
    # Predeclared exploratory 10% graph supplement, never replace operational ranking.
    ordered=sorted(signals,key=lambda k:(signals[k],k));percentiles={k:(i/(len(ordered)-1) if len(ordered)>1 else .5) for i,k in enumerate(ordered)}
    augmented=sorted(train,key=lambda r:(-(.9*r["score"]+.1*percentiles[r["site_id"]]),r["site_id"]))
    test_index={r["site_id"]:r for r in test}
    checks=[]
    for label,rows in [("shared_features",train),("shared_plus_training_pagerank_10pct",augmented)]:
        chosen=rows[:3];ids={r["site_id"] for r in chosen}
        # Unique station-demand coverage in held-out months, not demand at an unbuilt site.
        covered=set()
        for r in chosen:
            for j in tree.query_radius(np.radians([[r["latitude"],r["longitude"]]]),r=1000/m.EARTH_M)[0]:
                covered.add(located[int(j)]["station_id"])
        checks.append({"method":label,"selected_sites":[r["site_id"] for r in chosen],
          "test_top10_hits":sum(test_index[r["site_id"]]["rank"]<=10 for r in chosen if r["site_id"] in test_index),
          "test_nearby_rentals_unique":sum(counts[mo].get(sid,0) for mo in TEST for sid in covered),
          "test_monthly_top10_appearances":sum(any(r["site_id"] in ids and r["rank"]<=10 for r in shared[mo]) for mo in TEST)})
    return {"train_months":TRAIN,"test_months":TEST,"features":["facilities_within_500m","nearby_rentals_1000m","gap_ratio"],
      "methods":checks,"selection_overlap":len(set(checks[0]["selected_sites"])&set(checks[1]["selected_sites"])),
      "training_graph_nodes":len(graph),"training_graph_edges":graph.number_of_edges(),
      "operational_update":False,"limitations":["고정 참조 위치는 과거 시점 위치를 보증하지 않습니다.","같은 도시의 시간 홀드아웃이며 다른 도시로의 학습 모델 전이나 설치 효과 검증은 아닙니다.",
      "탐색적10% 가중치는 이 테스트 결과로 최적화하지 않습니다. K-means의 낮은 분리도로 군집 라벨을 우선 점수에 넣지 않습니다."]}
def audit_routes(candidates,stations,anchors,router):
    rows=[]
    for r in candidates[:5]:
        original=route_candidate(r,stations,anchors,router)
        rows.append({"site_id":r["site_id"],"original_rank":r["rank"],"original_score":r["score"],"original_route":original,"routes":[original]})
    # Top three get one alternative anchor; each anchor gets its nearest and second dock.
    for row,r in zip(rows[:3],candidates[:3]):
        p=(r["latitude"],r["longitude"])
        nearest=sorted(anchors,key=lambda a:metres(p,(float(a["lat"]),float(a["lon"]))))[:2]
        for anchor in nearest:
            target=(float(anchor["lat"]),float(anchor["lon"]))
            docks=sorted([s for s in stations if s.get("coordinate_valid") and (s.get("rental_count") or 0)>0 and metres((s["latitude"],s["longitude"]),target)<=300],
              key=lambda s:(metres((s["latitude"],s["longitude"]),target),s["station_id"]))[:2]
            for dock in docks:
                if any(q.get("anchor_id")==anchor["stop_id"] and q.get("dock_station_id")==dock["station_id"] for q in row["routes"]):continue
                row["routes"].append(route_candidate(r,[dock],[anchor],router))
    for row in rows:
        valid=[r for r in row["routes"] if r["status"]=="model_connected" and r.get("before_minutes") is not None]
        best=min(valid,key=lambda r:r["after_minutes"]) if valid else None
        row["best_checked_route"]=best
        row["overhead_sensitivity"]=[{"overhead_minutes":n,"gain_minutes":best["improvement_minutes"]+2-n if best else None,"positive":best["improvement_minutes"]+2-n>0 if best else None} for n in (0,2,5)]
        row["review_status"]="positive_model" if best and best["improvement_minutes"]>0 else "not_faster" if best else "unconfirmed"
    positive=sorted([r for r in rows if r["review_status"]=="positive_model"],key=lambda r:(r["best_checked_route"]["after_minutes"],r["original_rank"]))
    for i,r in enumerate(positive,1):r["validated_review_rank"]=i
    return {"candidate_count":len(rows),"candidates":rows,"review_order":[r["site_id"] for r in positive],
      "rule":"검증된 대안 중 도보 대비2분 가정에서 빠른 연결만 별도 검토 순서로 표시. 확인된 연계 모델 시간 오름차순; 운영 점수와 순위는 보존.",
      "limitations":["최대30회 신규 조회 예산, 상위5곳 최근접 및 상위3곳 2개앵커·2개반납소 부분 탐색. 전역 최적 경로 아님.",
      "현재 OSM 경로이며 실제 통행·배차·환승·설치 효과는 미검증. 대여·반납0/2/5분은 관측값이 아닌 가정."]}
def run():
    OUT.mkdir(parents=True,exist_ok=True)
    result={"built_at":datetime.now(timezone.utc).isoformat(),"cities":{},"operational_update":False,
      "full_journey":{"available":False,"reason":"노선별 정류장 순서·동일시점 시각표·대기시간과 동일 OD 검증자료 미확보. 접근 구간 결과를 전체 여정 결과로 바꾸지 않음."}}
    router=BoundedRouter()
    for city in ("seoul","daejeon","sejong"):
        checkpoint=OUT/(city+".json")
        if checkpoint.exists():result["cities"][city]=json.loads(checkpoint.read_text());continue
        scope,folder,data,boundary,districts,facilities,anchors=source(city,"individual")
        from shapely.geometry import Point
        from shapely.ops import unary_union
        baseline=unary_union([Point(*m.PROJECT(a["lon"],a["lat"])).buffer(500,quad_segs=16) for a in anchors]).intersection(boundary)
        candidates,_=m.grid_candidates(boundary,baseline,data["stations"],facilities,districts,use_population=city!="sejong")
        history=json.loads((ROOT/"data/reference/monthly_trends"/(city+".json")).read_text())
        evidence={"city":city,"source_revision":scope["revision"],"temporal":temporal(city,folder,data["stations"],candidates,history),
          "routes":audit_routes(candidates,data["stations"],anchors,router)}
        save(checkpoint,evidence);result["cities"][city]=evidence
        print(city,"complete",router.requests,flush=True)
    result["new_routing_requests_this_run"]=router.requests
    save(OUT/"results.json",result)
if __name__=="__main__":run()
