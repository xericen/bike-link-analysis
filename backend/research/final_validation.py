"""Present independent follow-up evidence without replacing operational ranking."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FILE=ROOT/"docs/final-validation-20261123/results.json"
def enrich(packets,scope):
    if not FILE.exists():return
    report=json.loads(FILE.read_text())
    for packet in packets:
        audit=report["cities"].get(packet["city"])
        if not audit or audit["source_revision"]!=packet["source_revision"]:continue
        temporal=audit["temporal"]
        baseline,graph=temporal["methods"]
        packet["additional_validation"]={"temporal":temporal,"full_journey":report["full_journey"]}
        packet["findings"].append("별도 시간 검증: 2025년1·4~6월로 후보를 선정하고 7~12월을 평가했습니다. 인구를 제외한 동일3개 기준의 상위3곳 중 평가기간 상위10위에 "+str(baseline["test_top10_hits"])+"곳이 포함됐습니다.")
        packet["findings"].append("훈련기간 PageRank10% 보조 실험에서 상위3곳 중 "+str(temporal["selection_overlap"])+"곳이 기존 공통기준과 같았습니다. 운영 순위를 변경하지 않으며, 신규 수요 예측·설치 효과 검증으로 해석하지 않습니다.")
        pattern_file=FILE.parent/"training-patterns.json"
        if pattern_file.exists():
            pattern=json.loads(pattern_file.read_text())[packet["city"]]
            pair=pattern["similar_demand_different_pattern"]
            packet["additional_validation"]["training_patterns"]=pattern
            packet["findings"].append("훈련 수요가 비슷한 "+pair[0]["station_id"]+"와 "+pair[1]["station_id"]+"의 이용 집중 시각은 각각 "+str(pair[0]["peak_hour"])+"시·"+str(pair[1]["peak_hour"])+"시였습니다. 운영 점검 시간대를 구분하는 근거이며 군집을 확정 역할로 해석하지 않습니다.")
        if scope!="individual":continue
        routes=audit["routes"]
        packet["additional_validation"]["routes"]={k:v for k,v in routes.items() if k!="candidates"}
        packet["additional_validation"]["routes"]["checks"]=[{"site_id":r["site_id"],"original_rank":r["original_rank"],"review_rank":r.get("validated_review_rank"),"status_label":{"positive_model":"모델 시간 유리","not_faster":"도보보다 느림","unconfirmed":"경로 미확인"}[r["review_status"]],"before_minutes":r["best_checked_route"]["before_minutes"] if r["best_checked_route"] else None,"after_minutes":r["best_checked_route"]["after_minutes"] if r["best_checked_route"] else None} for r in routes["candidates"]]
        packet["findings"].append("전체기간 후보 상위"+str(routes["candidate_count"])+"곳을 추가 점검했습니다. 별도 경로 검토 순서: "+(" → ".join("기존"+str(next(r["original_rank"] for r in routes["candidates"] if r["site_id"]==sid))+"순위" for sid in routes["review_order"]) or "시간 개선이 확인된 후보 없음")+". 원래 점수순과 구분합니다.")
        by_id={r["site_id"]:r for r in routes["candidates"]}
        for site in packet["candidates"]:
            checked=by_id.get(site["site_id"])
            if not checked:continue
            site["additional_validation"]={k:checked.get(k) for k in ("review_status","validated_review_rank","overhead_sensitivity")}
            gain=checked["overhead_sensitivity"][-1]["gain_minutes"]
            sensitivity="5분 가정에서는 "+(f"{gain:.1f}분 단축" if gain is not None and gain>0 else "시간 단축 미확인")
            status=checked["review_status"]
            label=("별도 경로 검토 "+str(checked["validated_review_rank"])+"순위" if status=="positive_model" else "도보보다 느려 우선도 재검토" if status=="not_faster" else "경로 미확인으로 판단 보류")
            best=checked.get("best_checked_route")
            if best:
                site["unchecked"].append(f"추가 대안 경로: {best['anchor_name']} / 반납 {best['dock_station_id']}, 도보 {best['before_minutes']:.1f}분 → 자전거 연계 {best['after_minutes']:.1f}분(대여·반납2분 가정). 아래 기본 경로와 별도입니다.")
            site["action"]=label+" · "+sensitivity+" · 실제 설치·환승 효과 미검증"

def supplement_goals(goals):
    spark_file=FILE.parent/"spark.json"
    if spark_file.exists():
        spark=json.loads(spark_file.read_text())
        if spark.get("all_match"):
            count=sum(r["daily_od_rows"] for r in spark["results"])
            goals["items"][2]["evidence"]+=" 현재3도시 전체기간 daily OD "+format(count,",")+"행의 Spark 월 집계와 SQLite 결과도 일치했습니다. 원본 정제 전체의 Spark 이관은 아닙니다."
    solar_file=FILE.parent/"solar.json"
    if solar_file.exists():
        rows=json.loads(solar_file.read_text())["scenarios"]
        passed=sum(all(r.get("checks",{}).get(k,False) for k in ("http_200","autonomous_tool_selected","conclusion_tool_selected","individual_scope","candidate_id_cited","period_cited")) for r in rows)
        held=sum(r.get("response",{}).get("answer_basis")=="tool_summary" for r in rows)
        goals["items"][4]["evidence"]+=" 추가 실제 질문의 도구 선택·기간·후보ID 검사 "+str(passed)+"/"+str(len(rows))+"건. 이 중 "+str(held)+"건은 자유 서술을 보류하고 서버의 도구 요약으로 표시했습니다."
