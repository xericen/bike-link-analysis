"""Audit denominator sets and unchanged prepared KPIs; write presentation metadata only."""
import csv,json,hashlib,sqlite3
from collections import Counter
from pathlib import Path
from backend.services import precomputed,real_data
from scripts.preprocess.precompute_city_kpis import combinations
from backend.presentation.anchors import anchor_name
ROOT=Path(__file__).resolve().parents[2]
def audit():
    contexts={};baseline={}
    anchors=list(csv.DictReader((real_data.PROCESSED/"transit_anchors.csv").open()))
    sources=real_data.read_json("transit_anchors_sources.json",[])
    counts=Counter(r["city"] for r in anchors)
    with sqlite3.connect(real_data.database_path().resolve().as_uri()+"?mode=ro",uri=True) as c:
        def city_context(city,start,end):
            link=precomputed.read("transit_linkage",city,start,end)
            overview=precomputed.read("overview",city,start,end)
            located={r["station_id"] for r in link["stations"] if r.get("coordinate_valid") and r.get("nearest_anchor_distance_m") is not None}
            rows={r[0]:{"rows":r[1],"rentals":r[2] or 0,"returns":r[3] or 0} for r in c.execute(
              "SELECT station_id,COUNT(*),SUM(rental_count),SUM(return_count) FROM station_usage WHERE region_id=? AND date BETWEEN ? AND ? GROUP BY station_id",(city,start,end))}
            active={sid for sid,r in rows.items() if r["rentals"]>0}
            denominator_only=sorted(located-active);analysis_only=sorted(active-located)
            return_only=[sid for sid in denominator_only if rows.get(sid,{}).get("returns",0)>0]
            no_records=[sid for sid in denominator_only if sid not in rows]
            assert overview["station_count"]==len(active)
            reason=[]
            if return_only:reason.append(str(len(return_only))+"개는 반납 기록만 있고 대여 0건")
            if no_records:reason.append(str(len(no_records))+"개는 선택 기간 이용 기록 미연결")
            other=len(denominator_only)-len(return_only)-len(no_records)
            if other:reason.append(str(other)+"개는 해당 기간 대여 0건")
            if analysis_only:reason.append("분석 대여소 중 "+str(len(analysis_only))+"개는 위치 미연결로 분모 제외")
            note=f"분모는 앵커 거리를 확인한 위치 마스터 {len(located):,}개 기준이며, 대여 기록이 연결된 분석 대여소는 {len(active):,}개입니다"
            note+="("+("; ".join(reason) if reason else "두 집합 동일")+")."
            source=next(s for s in sources if ("BRT" in s["dataset_name"] if city=="sejong" else "도시철도" in s["dataset_name"]))
            source_note=f"{anchor_name(city)} 앵커: {counts[city]:,}개 기준(출처: {source['dataset_name']})"
            if city!="sejong":source_note+=" · 운영기관·노선별 행 기준"
            return {"city":city,"period_start":start,"period_end":end,"denominator_count":len(located),"analysis_station_count":len(active),
              "master_total":len(link["stations"]),"unlocated_master_count":len(link["stations"])-len(located),
              "denominator_only":{sid:rows.get(sid,{"rows":0,"rentals":0,"returns":0}) for sid in denominator_only},
              "analysis_only":{sid:rows[sid] for sid in analysis_only},"denominator_note":note,
              "anchor_name":anchor_name(city),"distance_label":"최근접 "+anchor_name(city)+"(앵커) 거리",
              "anchor_count":counts[city],"source_name":source["dataset_name"],"source_url":source["source_url"],"source_note":source_note,
              "station_map_note":f"대여소 전체 {len(located):,}개 표시(위치 마스터 {len(link['stations']):,}개 중 좌표 미확보 {len(link['stations'])-len(located)}개 제외) + 취약 후보 전체" if city=="sejong" else "대여소 최대 300개 표본 + 취약 후보 전체",
              "brt_line_geometry_available":False,"brt_scope":"BRT 정류장 좌표·순번 CSV, 실제 노선 선형 자료 미확보"}
        for city,start,end in combinations():
            key="|".join((city,start,end))
            if city=="all":
                children=[city_context(rid,start,end) for rid in ("seoul","daejeon","sejong")]
                value={"city":"all","cities":children,"denominator_note":" / ".join(x["denominator_note"] for x in children),
                     "source_note":" / ".join(x["source_note"] for x in children)}
            else:value=city_context(city,start,end)
            contexts[key]=value
            link=precomputed.read("transit_linkage",city,start,end);v=precomputed.read("vulnerability",city,start,end)
            baseline[key]={"goal_metrics":link.get("goal_metrics"),"candidate_count":v.get("candidate_count"),"scenario":v.get("scenario"),
              "city_scenarios":[{"city":r["city"],"scenario":r.get("scenario")} for r in v.get("cities",[])]}
    return {"revision":precomputed.revision(),"cache_sha256":hashlib.sha256(precomputed.path().read_bytes()).hexdigest(),"contexts":contexts,"kpi_baseline":baseline,
        "line_geometry_inspection":{"data/raw/sejong-brt-20250717.csv":"노선명·정류장 순번·정류장 좌표만, LineString 또는 도로 선형 없음","repo_brt_geometry_files":[]}}
if __name__=="__main__":
    data=audit();(ROOT/"docs/anchor_presentation_context.json").write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in data["contexts"].items() if k in ["seoul|2025-12-01|2025-12-31","daejeon|2025-12-01|2025-12-31","sejong|2025-12-01|2025-12-31"]},ensure_ascii=False))
