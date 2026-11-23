"""Strict read-only validation report. Never recomputes experiments on a request."""
import copy
import json
from functools import lru_cache
from fastapi import HTTPException
from backend.research import method_validation as experiments
from backend.services import precomputed

@lru_cache(maxsize=2)
def _read(path,stamp,size):
    with open(path) as f:
        return json.load(f)

def read(city="all"):
    if city not in set(experiments.CITIES)|{"all"}:
        raise HTTPException(404,"지원하지 않는 도시입니다.")
    path=experiments.FILE
    if not path.exists():
        raise HTTPException(409,"방법 검증 보고서가 미준비 상태입니다. 오프라인 검증 배치를 실행하세요.")
    report=_read(str(path),path.stat().st_mtime_ns,path.stat().st_size)
    if report["revision"] != precomputed.revision() or report["dependencies"] != experiments.dependencies():
        raise HTTPException(409,"방법 검증 보고서의 입력·코드가 변경되었습니다. 재검증이 필요합니다.")
    result={k:report[k] for k in ("available","revision","built_at","period_start","period_end","scope_note","limitations")}
    result["cities"]=[report["cities"][rid] for rid in (experiments.CITIES if city=="all" else (city,))]
    return copy.deepcopy(result)


def read_support(city="all"):
    from backend.research import validation_followup as followup
    result=read(city)
    # Source-aware optional reader even when the worker imported runtime before this feature.
    import importlib
    from pathlib import Path
    from backend.research import recovery_presentation as recovery
    stamp=Path(recovery.__file__).stat().st_mtime_ns
    if getattr(recovery,"_source_stamp",None)!=stamp:
        recovery=importlib.reload(recovery)
        recovery._source_stamp=stamp
    result["recovery_evaluation"]=recovery.read(city)
    from backend.research.breadth_presentation import read as breadth_read
    result["breadth_evaluation"]=breadth_read(city)
    path=followup.FILE
    result["followup_available"]=False
    result["evaluation_purpose"]="기존 상위 이용 재발견은 진단 실험입니다. 교통 공백 규칙의 평가에는 사전 공간 조건을 명시한 후속 코호트를 별도 사용하며, 원래 실패 결과를 대체하지 않습니다."
    if not path.exists():
        result["followup_message"]="후속 코호트·지도 근거가 미준비 상태입니다."
        return result
    data=_read(str(path),path.stat().st_mtime_ns,path.stat().st_size)
    if data["revision"]!=result["revision"] or data["dependencies"]!=followup.dependencies():
        result["followup_message"]="후속 검증 자료의 입력·코드가 달라 재검증이 필요합니다."
        return result
    result["followup_available"]=True
    for c in result["cities"]:
        c["followup"]=copy.deepcopy(data["cities"][c["city"]])
        high=next(r for r in c["backtest"] if r["fold"]=="high_usage")
        grids=[r for r in c["sensitivity"] if r["grid_step_m"]!=500]
        c["finding_summary"]=[
            "원래 상위 이용 가림: "+str(high["methods"]["full"]["hits"])+"/"+str(high["target_count"])+" 복구. 검증 성공으로 해석하지 않습니다.",
            "격자 크기 변경 시 위치 대응: "+", ".join(str(r["grid_step_m"])+"m "+str(round(100*r["geographic_top10_overlap"],1))+"%" for r in grids)+".",
            "반복 횟수는 같은 후보·근접 후보의 별도 교차 근거이며 기존 점수에 가산하지 않습니다."]
    return result

def anchor(city,name):
    value=read_support(city)
    if not value["followup_available"]:
        raise HTTPException(409,value["followup_message"])
    found=next((r for r in value["cities"][0]["followup"]["matrix_neighborhoods"] if r["anchor_name"]==name),None)
    if found is None:raise HTTPException(404,"선택 도시의 연계 여건 점검 역이 아닙니다.")
    return copy.deepcopy(found)

def individual_report(city):
    from backend.research.individual_recovery import read
    return read(city)


def tool_report(city,start=None,end=None,anchor_name=None,station_id=None,top_n=5):
    if start not in (None,experiments.START) or end not in (None,experiments.END):
        from backend.research.individual_recovery import read
        result=read(city,start,end)
        if result.get("available"):
            result["sources"]=json.loads((experiments.ROOT/"data/individual"/city/"sources.json").read_text())
            result["source_names"]=[s["dataset_name"] for s in result["sources"]]
            result["limitations"]=["전체 기간의 탐색 결과이며 독립 예측 성능·설치 효과가 아닙니다.","50m진단은신규설치추천이아닙니다."]
        return result
    value=read_support(city)
    c=value["cities"][0]
    matrix=c["demand_matrix"]
    output={k:value[k] for k in ("available","period_start","period_end","scope_note","revision","limitations","followup_available")}
    meta=precomputed.read("overview",city,experiments.START,experiments.END)
    output["sources"]=meta.get("sources",[])
    output["source_names"]=meta.get("source_names",[])
    output["method_document"]="docs/METHOD_VALIDATION.md"
    output["city"]=city
    output["findings"]=c.get("finding_summary",[])
    output["separate_method_experiment"]=copy.deepcopy(value.get("recovery_evaluation",{"available":False}))
    output["breadth_method_experiment"]=copy.deepcopy(value.get("breadth_evaluation",{"available":False}))
    output["breadth_experiment_note"]="12월 다방법 탐색 최고값과 잠금 후8월회고평가를 구분하세요.50m간격진단은 신규 설치 추천이 아니며 운영점수는 유지합니다."
    output["separate_experiment_note"]="기본 근거는 공통12월입니다. separate_method_experiment의6월개발·7월평가는 별도 연구 결과이며12월 개선률·운영 효과로 합산하거나 대체하지 마세요."
    output["original_recovery"]=[{"fold":r["fold"],"seed":r["seed"],"hits":r["methods"]["full"]["hits"],"target_count":r["target_count"],"feasible_count":r["feasible_within_match_radius_count"]} for r in c["backtest"]]
    output["matrix"]={k:matrix.get(k) for k in ("available","message","counts","matched_count","transit_median","bike_median","excluded_rows")}
    if value["followup_available"]:
        f=c["followup"]
        output["recurrence"]={**f["recurrence"],"items":f["recurrence"]["items"][:top_n]}
        output["gap_evaluation"]=f["gap_backtest"]
        selected=f["matrix_neighborhoods"]
        if anchor_name is not None:
            selected=[r for r in selected if r["anchor_name"]==anchor_name]
            if not selected:raise HTTPException(404,"실제 보고서에 없는 역 이름입니다.")
        if station_id is not None:
            selected=[r for r in selected if any(s["station_id"]==station_id for s in r["nearby_stations"])]
            if not selected:raise HTTPException(404,"이 점검 역 주변 목록에 없는 대여소입니다.")
        output["anchor_reviews"]=[{**r,"nearby_station_count":len(r["nearby_stations"]),
                                  "nearby_stations":[s for s in r["nearby_stations"] if station_id is None or s["station_id"]==station_id][:top_n]}
                                  for r in selected[:top_n]]
    return output
