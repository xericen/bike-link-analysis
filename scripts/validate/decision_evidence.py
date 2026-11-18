"""Reproduce decision study: raw codes, nearby demand, model union and algorithm cases."""
import csv,io,json,zipfile,math,hashlib
from collections import Counter
from pathlib import Path
import numpy as np
from backend.services import real_data,precomputed
from scripts.collect.audit_candidate_routes import metres,input_signature
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"data/processed/research"
def transfer(stations):
    by={r["station_id"]:r for r in stations}
    codes=Counter();cross=Counter();count=0
    def near(sid):
        value=by.get(sid,{}).get("nearest_anchor_distance_m")
        return "unknown" if not isinstance(value,(int,float)) or not math.isfinite(value) else ("within300" if value<=300 else "outside300")
    zpath=ROOT/"data/raw/sejong-details-15106191.zip"
    with zipfile.ZipFile(zpath) as z:
        member=next(n for n in z.namelist() if "2025" in n and "4분기" in n)
        raw=z.read(member)
        for r in csv.DictReader(io.StringIO(raw.decode("cp949"))):
            if not r["대여시간"].startswith("2025-12"):continue
            code=r["환승 유무"].strip() or "EMPTY"
            codes[code]+=1;count+=1
            cross[(code,near(r["시작 대여소"]),near(r["반납 대여소"]))]+=1
    return {"period_start":"2025-12-01","period_end":"2025-12-31","row_count":count,"raw_codes":dict(codes),
        "cross_tab":[{"raw_code":k[0],"origin":k[1],"destination":k[2],"count":v} for k,v in sorted(cross.items())],
        "definition_status":"unverified","actual_transfer_rate":None,"csv_sha256":hashlib.sha256(raw).hexdigest(),
        "source_url":"https://www.data.go.kr/data/15106191/fileData.do","checked_at":"2026-11-18",
        "message":"공식 공개 설명에서 환승 유무 컬럼의 판정 정의를 확인하지 못했습니다. N을 실제 비환승으로 확정하거나 실제 환승률 0%로 해석하지 않습니다.",
        "cross_tab_basis":"2025-12 이용 이력 × 2026-05 위치 마스터 × 현재 BRT 앵커. 근접성 대조이며 실제 환승 검증 아님."}
def pattern_case(city,start,end):
    rows=[r for r in real_data.profiles(city,start,end) if r.get("has_hourly") and r["rental_count"]>=100]
    rows.sort(key=lambda r:r["rental_count"]);best=None
    for i,a in enumerate(rows):
        va=np.array(a["hourly"],dtype=float)
        for b in rows[i+1:i+25]:
            if b["rental_count"]>a["rental_count"]*1.05:break
            vb=np.array(b["hourly"],dtype=float)
            cosine=float(np.dot(va,vb)/(np.linalg.norm(va)*np.linalg.norm(vb)))
            if best is None or cosine<best[0]:best=(cosine,a,b)
    if best is None:return None
    return {"cosine":best[0],"neighbor_search_limit":25,"selection_rule":"대여량 순 인접 25개 이내·5% 수요 차이 조건의 비교 중 최저 Cosine 사례","max_demand_difference_ratio":.05,"stations":[
        {"station_id":r["station_id"],"rental_count":r["rental_count"],"peak_hour":int(np.argmax(r["hourly"])),"hourly":r["hourly"]}
        for r in best[1:]],"decision":"총대여량이 유사해도 집중 시간이 다르면 현장 관찰·재배치 검토 시간대를 달리합니다. 실제 부족·이동 필요 수량은 추정하지 않습니다."}
def build():
    inputs=json.loads((OUT/"decision-inputs.json").read_text());routes=json.loads((OUT/"route-audit.json").read_text())
    if inputs["revision"]!=precomputed.revision():raise RuntimeError("Extract current prepared decision inputs first")
    if routes.get("input_signature")!=input_signature(inputs):raise RuntimeError("Route candidate coordinates or anchors changed; rerun route audit")
    profiles={}
    for city,x in inputs["cities"].items():
        ids={r["site_id"] for r in x["new_top3"]}
        union=next(s for s in x["selection_states"] if set(s["selected_ids"])==ids)
        rows=[]
        for r in x["new_top3"]:
            rows.append({**r,"nearest_anchor_distance_m":min(metres((r["latitude"],r["longitude"]),(a["lat"],a["lon"])) for a in x["anchors"]),"selection_reason":f"앵커 접근 공백 비율 {r['gap_ratio']:.2f}, 주변 1km 관측 대여 {r['nearby_rentals_1000m']:,}건, 500m 시설 {r['facilities_within_500m']}개",
             "observed_demand_label":"주변 기존 대여소 관측량(후보 간 중복 가능); 신규 수요 예측 아님",
             "feasibility_unchecked":["부지 소유·사용 허가","보도 유효 폭·출입구","안전·하천·철도 횡단","설치 비용·운영 용량","과거와 현재 위치 동일성"]})
        hub=(x["research"].get("types",{}).get("low_usage_high_connectivity") or [None])[0]
        if hub:hub={**hub,"decision":"대여량만 보면 낮은 우선순위이나 PageRank가 높아 연결 유지 검토 사례로 추가합니다. 설치 우선순위 가산점이나 실제 환승 근거로 사용하지 않습니다."}
        profiles[city]={"city":city,"period_start":x["period_start"],"period_end":x["period_end"],
          "top3":rows,"top3_union":union,"route_audit":[r for r in routes["rows"] if r["city"]==city],
          "route_source":routes["source"],"route_limitations":routes["limitations"],
          "sensitivity":x["sensitivity"],"hidden_hub":hub,
          "pattern_case":pattern_case(city,x["period_start"],x["period_end"]),
          "cluster_quality":x["cluster_quality"],"cluster_decision":"낮은 Silhouette로 군집 역할 해석 보류. 최종 입지 점수에 군집명을 강제로 반영하지 않습니다.",
          "planning_scope":"공간 모델상 검토 후보이며 실제 설치 후 이용량·환승 증가 예측 아님",
          "population_basis":x["population_basis"]}
    evaluation=json.loads((OUT/"solar-paired-evaluation.json").read_text()) if (OUT/"solar-paired-evaluation.json").exists() else {"status":"not_run"}
    for case in evaluation.get("cases",[]):
        source=inputs["cities"][case["city"]];top=source["ranking"][0]
        truth={"candidate_count":source["candidate_count"],"top_station_id":top["station_id"],"top_rentals":top["rental_count"],"top_anchor_distance_m":top["nearest_stop_distance_m"],"linked_trip_share":source["goal_metrics"]["linked_trip_share"]}
        if (case["period_start"],case["period_end"])!=(source["period_start"],source["period_end"]) or any(c["expected"]!=truth.get(c["field"]) for c in case["tool_assisted"]["evaluation"]["checks"]):
            raise RuntimeError("Paired evaluation truth changed; rerun the explicitly requested Solar study")
    attempts=[]
    for name in ("solar-paired-technical-failure.json","solar-paired-format-failure.json"):
        path=OUT/name
        if path.exists():
            old=json.loads(path.read_text())
            attempts.append({"artifact":name,"reason":"준비 중 집계 조회 불가" if "technical" in name else "최종 응답 JSON 형식 실패",
                "calls":len(old.get("calls",[])),"reported_tokens":sum((c.get("usage") or {}).get("total_tokens",0) for c in old.get("calls",[]))})
    evaluation["technical_pilots"]=attempts
    t=transfer(inputs["cities"]["sejong"]["stations"])
    for city,p in profiles.items():
        p["transfer_audit"]=t if city=="sejong" else {"actual_transfer_rate":None,"message":"실제 환승 여부 미확인. 앵커 근접 이동은 환승 가능성 지표입니다."}
    result={"revision":precomputed.revision(),"profiles":profiles,"transfer_audit":t,"agent_evaluation":evaluation}
    (OUT/"decision-evidence.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({"revision":result["revision"],"transfer":result["transfer_audit"]["raw_codes"],"profiles":{k:{"union_added_m2":v["top3_union"]["added_area_m2"],"overlap_m2":v["top3_union"]["overlap_area_m2"],"pattern":v["pattern_case"]["cosine"] if v["pattern_case"] else None} for k,v in profiles.items()}},ensure_ascii=False))
if __name__=="__main__":build()
