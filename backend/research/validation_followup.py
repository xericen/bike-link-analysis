"""Predeclared gap-cohort evaluation and descriptive sensitivity support.
Production scores and the original failed recovery experiment remain unchanged.
"""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from sklearn.neighbors import BallTree
from backend.research import method_validation as m

FILE=m.ROOT/"data/reference/method_validation_followup_202512.json"

def dependencies():
    return {**m.dependencies(),"followup_code":m.sha(__file__),
            "base_report":m.sha(m.FILE)}

def recurrence(rows):
    """Same-grid identity and changed-grid proximity are reported separately."""
    base=rows[0]["top"]
    assessed=[r for r in rows if r["candidate_buffer_m"]==300]
    tally={r["site_id"]:{"site_id":r["site_id"],"latitude":r["latitude"],"longitude":r["longitude"],
                          "district":r["district"],"baseline_rank":r["rank"],
                          "same_grid_hits":0,"changed_grid_hits":0,"conditions":[]} for r in base}
    same=sum(r["grid_step_m"]==500 for r in assessed)
    changed=len(assessed)-same
    for row in assessed:
        if row["grid_step_m"]==500:
            pairs=[{"station_id":r["site_id"],"site_id":r["site_id"],"distance_m":0}
                   for r in row["top"] if r["site_id"] in tally]
        else:
            pairs=m.geographic_matches([{**r,"station_id":r["site_id"]} for r in base],row["top"])["pairs"]
        for pair in pairs:
            item=tally[pair["station_id"]]
            key="same_grid_hits" if row["grid_step_m"]==500 else "changed_grid_hits"
            item[key]+=1
            item["conditions"].append({"anchor_m":row["anchor_radius_m"],"grid_m":row["grid_step_m"],
                                      "policy":row["policy"],"matched_site_id":pair["site_id"],
                                      "distance_m":pair["distance_m"]})
    result=[]
    for r in tally.values():
        r.update(same_grid_tests=same,changed_grid_tests=changed,
                 total_hits=r["same_grid_hits"]+r["changed_grid_hits"],
                 total_tests=same+changed)
        result.append(r)
    result.sort(key=lambda r:(-r["total_hits"],r["baseline_rank"],r["site_id"]))
    return {"items":result,"definition":"기준 TOP10만 평가. 동일 격자5조건은 ID 일치, 변경 격자2조건은300m 일대일 대응. 버퍼만 바꾼 조건 제외.",
            "decision":"반복 횟수는 현장 확인 순서를 검토할 별도 근거이며 운영 점수를 변경하지 않습니다."}

def eligible_targets(stations,boundary):
    from shapely.geometry import Point
    located=[s for s in stations if s.get("coordinate_valid")]
    if len(located)<2:return [],{"active_located":0,"eligible":0}
    tree=BallTree(np.radians([[s["latitude"],s["longitude"]] for s in located]),metric="haversine")
    active=[s for s in located if (s.get("rental_count") or 0)>0 and
            boundary.covers(Point(*m.PROJECT(s["longitude"],s["latitude"])))]
    chosen=[]
    reasons={"near_anchor":0,"near_other_bike_station":0,"anchor_distance_missing":0}
    for s in active:
        anchor=s.get("nearest_anchor_distance_m")
        if anchor is None:anchor=s.get("nearest_stop_distance_m")
        if anchor is None or not math.isfinite(anchor):
            reasons["anchor_distance_missing"]+=1;continue
        if anchor<=500:reasons["near_anchor"]+=1;continue
        d,_=tree.query(np.radians([[s["latitude"],s["longitude"]]]),k=2)
        nearest_other=float(d[0][1]*m.EARTH_M)
        if nearest_other<=300:reasons["near_other_bike_station"]+=1;continue
        chosen.append({**s,"nearest_other_station_m":nearest_other})
    chosen.sort(key=lambda s:(-s["rental_count"],s["station_id"]))
    return chosen,{"active_located":len(active),"eligible":len(chosen),"excluded_by_first_rule":reasons}

def gap_backtest(boundary,stations,facilities,districts,anchors,od,city):
    cohort,eligibility=eligible_targets(stations,boundary)
    n=min(10,len(cohort))
    result={"definition":"이용 있는 경계 내 대여소 중 앵커500m 밖·자기 자신 제외 다른 대여소300m 밖. 숨기기 전 외생 위치 조건으로 코호트를 정함.",
            "preregistered_policy":"기존 높은 이용량 재발견 실패 확인 후 설계한 탐색적 후속평가. 같은 월 검증이며 별도 기간 일반화 입증 아님.",
            "eligibility":eligibility,"folds":[]}
    if not n:
        result.update(available=False,message="사전 정의한 공간 공백 조건을 충족하는 관측 대여소가 없습니다.");return result
    folds=[("gap_high_usage",0,cohort[:n])]
    for seed in (71,72):
        indices=np.random.default_rng(seed).choice(len(cohort),n,replace=False)
        folds.append(("gap_random_sample",seed,[cohort[int(i)] for i in indices]))
    baseline=m.baseline_geometry(anchors,boundary,500)
    for name,seed,targets in folds:
        training,audit=m.retain_training(stations,od,[s["station_id"] for s in targets])
        ranked,_=m.grid_candidates(boundary,baseline,training,facilities,districts,use_population=city!="sejong")
        full=m.geographic_matches(targets,ranked[:10])
        demand=m.geographic_matches(targets,sorted(ranked,key=lambda r:(-r["nearby_rentals_1000m"],r["site_id"]))[:10])
        opportunity=[r for r in targets if m.geographic_matches([r],ranked)["hits"]]
        rng=np.random.default_rng(2000+seed)
        random=[m.geographic_matches(targets,[ranked[int(i)] for i in rng.choice(len(ranked),min(10,len(ranked)),replace=False)])["recall"]
                for _ in range(30)] if ranked else [0.0]*30
        result["folds"].append({"fold":name,"seed":seed,"target_count":len(targets),
            "target_ids":[r["station_id"] for r in targets],"top_k":10,"match_radius_m":300,
            "candidate_count":len(ranked),"candidate_generation_possible":len(opportunity),
            "full":full,"demand_only":demand,"random_recall_mean":float(np.mean(random)),
            "no_candidate_nearby":len(targets)-len(opportunity),
            "feasible_not_top10":len(opportunity)-full["hits"],"training_audit":audit})
    result["available"]=True
    return result

def neighborhoods(matrix,stations,city):
    if not matrix.get("available"):return []
    located=[s for s in stations if s.get("coordinate_valid")]
    rows=[]
    for anchor in matrix["rows"]:
        if anchor["quadrant"]!="high_low":continue
        lat,lon=anchor["latitude"],anchor["longitude"]
        near=[]
        for s in located:
            a,b=map(math.radians,(lat,s["latitude"]))
            dlat=b-a;dlon=math.radians(s["longitude"]-lon)
            distance=2*m.EARTH_M*math.asin(min(1,math.sqrt(math.sin(dlat/2)**2+
                      math.cos(a)*math.cos(b)*math.sin(dlon/2)**2)))
            if distance<=500:
                near.append({**{k:s.get(k) for k in ("station_id","station_name","latitude","longitude","rental_count","return_count","nearest_anchor_distance_m")},
                             "region_id":city,"distance_to_selected_anchor_m":distance})
        near.sort(key=lambda s:(s["distance_to_selected_anchor_m"],s["station_id"]))
        # Must match the actual radius aggregation already used by the matrix.
        assert len(near)==anchor["bike_station_count_500m"],(city,anchor["station_name"],"station count mismatch")
        assert sum((s["rental_count"] or 0)+(s["return_count"] or 0) for s in near)==anchor["bike_activity_500m"],(city,anchor["station_name"],"activity mismatch")
        rows.append({"city":city,"anchor_name":anchor["station_name"],"latitude":lat,"longitude":lon,
                     "transit_total":anchor["transit_total"],"bike_activity":anchor["bike_activity_500m"],
                     "nearby_stations":near,"period_start":m.START,"period_end":m.END})
    rows.sort(key=lambda r:(-r["transit_total"],r["anchor_name"]))
    return rows
