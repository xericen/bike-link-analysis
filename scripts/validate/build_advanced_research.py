"""Offline six-scope research: no mutation of source data, operational KPIs or rankings."""
import argparse,csv,hashlib,json,math,os,sqlite3,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.ops import unary_union,polygonize
from scipy.spatial import cKDTree
from sklearn.neighbors import BallTree
from backend.analysis.planning import PROJECT
from backend.research import method_validation as m,advanced_methods as a
from backend.services import precomputed,planning,city_anchors
from backend.presentation import individual
ROOT=m.ROOT
OUT=ROOT/"docs/advanced-research-20261123"
def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(".tmp");temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2));temp.replace(path)
def digest(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def source(city,scope):
    s=individual.scope(city) if scope=="individual" else {"start":"2025-12-01","end":"2025-12-31"}
    directory=ROOT/"data/individual"/city if scope=="individual" else ROOT/"data/processed"
    data=individual.read(city,"transit_linkage") if scope=="individual" else precomputed.read("transit_linkage",city,s["start"],s["end"])
    boundary,districts=planning.boundaries(city)
    facilities=json.loads((directory/("planning_facilities_"+city+".json")).read_text())
    anchors=[r for r in city_anchors.stops() if r["city"]==city]
    return s,directory,data,boundary,districts,facilities,anchors

def location(city,scope,s,data,boundary,districts,facilities,anchors,out):
    baseline=unary_union([Point(*PROJECT(r["lon"],r["lat"])).buffer(500,quad_segs=16) for r in anchors]).intersection(boundary)
    all_rows,_=m.grid_candidates(boundary,baseline,data["stations"],facilities,districts,use_population=city!="sejong")
    anchor_tree=BallTree(np.radians(np.array([[r["lat"],r["lon"]] for r in anchors],dtype=float)),metric="haversine")
    if not all_rows:return {"available":False,"message":"적격 신규 후보 없음"}
    distance=anchor_tree.query(np.radians([[r["latitude"],r["longitude"]] for r in all_rows]),k=1)[0][:,0]*m.EARTH_M
    eligible=[r for r,d in zip(all_rows,distance) if d<=1500 and r["potential_added_area_m2"]>0]
    # Preserve geographic diversity before imposing a deterministic 60-site experimental budget.
    representatives={}
    for r in eligible:
        x,y=PROJECT(r["longitude"],r["latitude"]);representatives.setdefault((int(x//2000),int(y//2000)),r)
    pool={r["site_id"]:r for r in eligible[:20]}
    for r in list(representatives.values())[:40]:pool[r["site_id"]]=r
    for r in eligible:
        if len(pool)>=60:break
        pool[r["site_id"]]=r
    rows=sorted(pool.values(),key=lambda r:(-r["score"],r["site_id"]))[:60]
    if len(rows)<3:return {"available":False,"message":"축소 후보가 3개 미만"}
    buffers=[Point(*PROJECT(r["longitude"],r["latitude"])).buffer(300,quad_segs=16).intersection(boundary).difference(baseline) for r in rows]
    atoms=[p for p in polygonize(unary_union([g.boundary for g in buffers])) if not p.is_empty]
    area_covers=[];area_weights=[]
    for atom in atoms:
        point=atom.representative_point();ids=[j for j,g in enumerate(buffers) if g.covers(point)]
        if ids:area_covers.append(ids);area_weights.append(float(atom.area))
    union=unary_union(buffers)
    assert math.isclose(sum(area_weights),union.area,rel_tol=1e-7,abs_tol=.01)
    stations=[r for r in data["stations"] if r.get("coordinate_valid") and (r.get("rental_count") or 0)>0]
    xy=np.array([PROJECT(r["longitude"],r["latitude"]) for r in rows]);tree=cKDTree(xy)
    demand_covers=[tree.query_ball_point(PROJECT(r["longitude"],r["latitude"]),1000) for r in stations]
    demand_weights=[int(r["rental_count"]) for r in stations]
    comparisons=[]
    for objective,covers,weights in [("gap_area",area_covers,area_weights),("nearby_observed_demand",demand_covers,demand_weights)]:
        for k in (1,2,3):
            experiment=a.compare(covers,weights,len(rows),k,out/(objective+"-"+str(k)+".log"))
            experiment["objective"]=objective
            for method in experiment["methods"].values():
                ids=method.pop("indices")
                method["sites"]=[rows[j]["site_id"] for j in ids]
                method["gap_area_m2"]=float(unary_union([buffers[j] for j in ids]).area)
                method["nearby_rentals_unique"]=int(a.covered(ids,demand_covers,demand_weights))
                method["candidate_buffer_gross_m2"]=sum(buffers[j].area for j in ids)
                assert method["gap_area_m2"]<=method["candidate_buffer_gross_m2"]+.01
            if experiment["solver"]["proven_optimal"]:
                best=experiment["solver"]["objective"]
                assert all(v["covered"]<=best+max(.01,abs(best)*1e-6) for v in experiment["methods"].values())
            comparisons.append(experiment)
    return {"available":True,"original_candidates":len(all_rows),"eligible_candidates":len(eligible),"reduced_candidates":len(rows),
       "reduction":"anchor<=1500m; score top20 + score-leading representatives of 2km tiles up to40; fill to60",
       "whole_city_before_reduction":True,"optimality_scope":"축소 후보 집합·고정 참조 위치·공간 모델 안에서만 최적",
       "demand_definition":"후보 1km 이내 기존 대여소의 관측 대여를 대여소별 한 번 계산. 신규 수요·300m 접근 수요 예측 아님.",
       "area_definition":"앵커500m 밖·행정경계 안의 후보300m 버퍼 합집합. 정확한 교차 다각형 원자별 중복 제거.",
       "candidate_sites":[{k:r[k] for k in ("site_id","latitude","longitude","score","district")} for r in rows],
       "comparisons":comparisons,"operational_update":False}

def uncertainty(directory,city,start,end):
    frame=pd.read_csv(directory/("anchor_hourly_"+city+".csv"))
    frame=frame[(frame.date>=start)&(frame.date<=end)]
    daily=frame.groupby("date",sort=True)[["linked_count","total_count","unknown_endpoint_count"]].sum()
    assert (daily.total_count>0).all()
    result=a.calendar_ci(daily.index.tolist(),daily.linked_count,daily.total_count)
    result["block_sensitivity"]=[a.calendar_ci(daily.index.tolist(),daily.linked_count,daily.total_count,replicates=1000,block=b) for b in (3,14)]
    expected=len(pd.date_range(start,end))
    result.update(observed_days=len(daily),calendar_days=expected,missing_days=expected-len(daily),
        unknown_endpoint_trips=int(daily.unknown_endpoint_count.sum()),total_trips=int(daily.total_count.sum()),
        linked_trips=int(daily.linked_count.sum()),period_start=start,period_end=end,
        interpretation="관측 날짜 구성을 재표본한 비중 변동 범위. 전체 기록의 집계 오차·실제 환승률·미래 예측 구간 아님.",
        limitation="연월별 관측일 수를 고정하고 연속 달력일 블록만 재표본. 누락일을 0으로 채우거나 공백을 잇지 않음. 월내 블록 끝점의 표본확률 차이와 장기 참조자료 편향은 남음.")
    return result,daily

def explanation(city,directory,start,end,data,facilities):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error,r2_score
    from sklearn.inspection import permutation_importance
    conn=sqlite3.connect((directory/"analysis.sqlite").resolve().as_uri()+"?mode=ro",uri=True)
    days=pd.read_sql_query("SELECT DISTINCT date FROM station_usage WHERE region_id=? AND date>=? AND date<=? AND rental_count>0 ORDER BY date",conn,params=(city,start,end)).date.tolist()
    cutoff=days[int(len(days)*.8)]
    ranked=pd.read_sql_query("SELECT station_id,SUM(rental_count) n FROM station_usage WHERE region_id=? AND date>=? AND date<? GROUP BY station_id ORDER BY n DESC,station_id",conn,params=(city,start,cutoff))
    known={r["station_id"]:r for r in data["stations"] if r.get("coordinate_valid") and r.get("nearest_anchor_distance_m") is not None}
    ids=[sid for sid in ranked.station_id if sid in known][:50]
    marks=",".join("?" for _ in ids)
    frame=pd.read_sql_query("SELECT station_id,date,SUM(rental_count) rentals FROM station_usage WHERE region_id=? AND date>=? AND date<=? AND station_id IN ("+marks+") GROUP BY station_id,date",conn,params=(city,start,end,*ids))
    conn.close()
    # Only known city observation days get a zero for absent station rentals; actual outage dates remain excluded.
    panel=frame.set_index(["station_id","date"]).reindex(pd.MultiIndex.from_product([ids,days],names=["station_id","date"]),fill_value=0).reset_index()
    dates=pd.to_datetime(panel.date)
    facility_tree=cKDTree([PROJECT(r["lon"],r["lat"]) for r in facilities]) if facilities else None
    static={}
    for sid in ids:
        r=known[sid];point=PROJECT(r["longitude"],r["latitude"])
        static[sid]=[r["nearest_anchor_distance_m"],r.get("stops_within_500m") or 0,
            len(facility_tree.query_ball_point(point,500)) if facility_tree else 0,r["latitude"],r["longitude"]]
    X=pd.DataFrame([static[sid] for sid in panel.station_id],columns=["anchor_distance_m","stops_500m","facilities_500m","latitude","longitude"])
    X["weekday"]=dates.dt.weekday
    X["month_sin"]=np.sin(2*np.pi*dates.dt.month/12);X["month_cos"]=np.cos(2*np.pi*dates.dt.month/12)
    X["elapsed_days"]=(dates-pd.Timestamp(start)).dt.days
    y=panel.rentals.to_numpy();train=(panel.date<cutoff).to_numpy()
    model=HistGradientBoostingRegressor(loss="poisson",max_iter=80,max_leaf_nodes=15,random_state=42,early_stopping=False).fit(X[train],y[train])
    pred=model.predict(X[~train])
    means=panel[train].groupby("station_id").rentals.mean()
    baseline=panel.loc[~train,"station_id"].map(means).to_numpy()
    importance=permutation_importance(model,X[~train],y[~train],scoring="neg_mean_absolute_error",n_repeats=5,random_state=42,max_samples=min(5000,(~train).sum()))
    imp=sorted([{"feature":name,"mae_increase":float(mean),"std":float(sd)} for name,mean,sd in zip(X.columns,importance.importances_mean,importance.importances_std)],key=lambda r:-r["mae_increase"])
    sample=X[~train].sample(n=min(2000,(~train).sum()),random_state=42)
    curves=[]
    for feature in ("anchor_distance_m","facilities_500m"):
        grid=np.unique(np.quantile(X.loc[train,feature],np.linspace(.05,.95,9)))
        values=[]
        for v in grid:
            changed=sample.copy();changed[feature]=v
            values.append({"x":float(v),"mean_model_output":float(model.predict(changed).mean())})
        curves.append({"feature":feature,"points":values})
    return {"available":True,"scope":"training-period high-use 50 located stations; same stations in chronological holdout",
        "period_start":start,"period_end":end,"train_end":max(panel.loc[train,"date"]),"test_start":cutoff,
        "train_rows":int(train.sum()),"test_rows":int((~train).sum()),"station_ids":ids,
        "model":"HistGradientBoostingRegressor poisson, 80 iterations, no early stopping",
        "mae":float(mean_absolute_error(y[~train],pred)),"baseline_station_mean_mae":float(mean_absolute_error(y[~train],baseline)),
        "r2":float(r2_score(y[~train],pred)),"permutation_importance":imp,"partial_dependence":curves,
        "unavailable_variables":["동일 기간 시간대별 대중교통 승하차","과거 시설/정류장 위치 변화","일별 날씨·과거 재고"],
        "interpretation":"관측 수요 설명 모델. 중요도와 부분 의존은 모델 내부 연관이며 인과관계·신규 설치 후 수요·운영 예측 성능을 입증하지 않음.",
        "leakage_controls":["선정 대여소는 훈련 기간 이용량만 사용","날짜 경계로 모든 대여소를 함께 분할","미래 대여량·현재 기간 합계·PageRank를 입력에서 제외","실제 도시 미관측일을 0으로 채우지 않음"],
        "limitations":["훈련 기간 고이용 50곳만 검토: 도시 전체 대표성 없음","고정 참조 공간 자료: 과거 동일성 미검증","상관된 공간변수의 중요도 분산·부분 의존 외삽 가능","동일 지역의 시간 홀드아웃이며 신규 지역 일반화는 미검증"]}

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    report={"schema":1,"built_at":datetime.now(timezone.utc).isoformat(),"operational_update":False,
      "protocol":{"k":[1,2,3],"max_candidates":60,"anchor_limit_m":1500,"candidate_buffer_m":300,"demand_radius_m":1000,"seed":42,"bootstrap_replicates":2000,"block_days":7,"holdout_fraction":.2},
      "relocation":{"available":False,"reason":"과거 재고·거치 용량·목표 재고 미확보. 실제 재배치 수량·최소 비용 계획 미산출."},"scopes":{}}
    inputs={}
    common_daily=[]
    for scope in ("common","individual"):
        report["scopes"][scope]={}
        for city in m.CITIES:
            path=OUT/(scope+"-"+city+".json")
            if path.exists():
                result=json.loads(path.read_text());print("reuse",scope,city,flush=True)
                # A checkpoint is reusable only for the same implementation and source revision.
                if result.get("code_hash")!=digest(Path(__file__)) or result.get("methods_hash")!=digest(Path(a.__file__)):raise RuntimeError("Checkpoint version mismatch")
            else:
                print("build",scope,city,flush=True);s,directory,data,boundary,districts,facilities,anchors=source(city,scope)
                city_out=OUT/(scope+"-"+city);city_out.mkdir(exist_ok=True)
                loc=location(city,scope,s,data,boundary,districts,facilities,anchors,city_out)
                ci,daily=uncertainty(directory,city,s["start"],s["end"])
                exp=explanation(city,directory,s["start"],s["end"],data,facilities) if scope=="individual" else {"available":False,"reason":"수요 설명 모델은 도시별 전체 기간에서 시간 홀드아웃 검증"}
                result={"available":True,"city":city,"scope":scope,"period_start":s["start"],"period_end":s["end"],"location":loc,"headline_ci":ci,"explanation":exp,
                    "code_hash":digest(Path(__file__)),"methods_hash":digest(Path(a.__file__)),"source_revision":individual.scope(city)["revision"] if scope=="individual" else precomputed.revision()}
                dump(path,result)
            report["scopes"][scope][city]=result
            if scope=="common":
                _,directory,_,_,_,_,_=source(city,scope)
                _,daily=uncertainty(directory,city,result["period_start"],result["period_end"]);common_daily.append(daily)
    daily=sum(common_daily[1:],common_daily[0])
    report["common_all_ci"]=a.calendar_ci(daily.index.tolist(),daily.linked_count,daily.total_count)
    report["common_all_ci"].update(period_start="2025-12-01",period_end="2025-12-31",total_trips=int(daily.total_count.sum()))
    # Inputs use content provenance for prepared snapshots and immutable SQL/source metadata for reproducibility.
    for city in m.CITIES:
        for folder in (ROOT/"data/processed",ROOT/"data/individual"/city):
            for name in ("analysis.sqlite","stations.csv","transit_anchors.csv","planning_population.json","anchor_hourly_"+city+".csv","planning_facilities_"+city+".json"):
                path=folder/name
                if path.exists():inputs[str(path.relative_to(ROOT))]={"size":path.stat().st_size,"mtime_ns":path.stat().st_mtime_ns,"sha256":digest(path) if path.suffix!=".sqlite" else "refer to protected/common and individual input manifests"}
    report["inputs"]=inputs
    report["code"]={str(Path(__file__).relative_to(ROOT)):digest(Path(__file__)),str(Path(a.__file__).relative_to(ROOT)):digest(Path(a.__file__))}
    dump(OUT/"results.json",report)
    print("READY six scopes",flush=True)
if __name__=="__main__":run()
