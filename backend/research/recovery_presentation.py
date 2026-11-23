"""Read-only compact presentation of archived experiments, not an operational score."""
import copy
import json
from functools import lru_cache
from pathlib import Path
from backend.research import method_validation as m

DIRECTORY=m.ROOT/"docs/recovery-evaluation-20261123"

@lru_cache(maxsize=4)
def _summary(signature):
    root=DIRECTORY
    checksums=json.loads((root/"presentation-manifest.json").read_text())
    for name in ("results.json","audit.json","inputs.json"):
        if m.sha(root/name)!=checksums[name]:
            raise ValueError("저장된 실험 결과 지문 불일치")
    report=json.loads((root/"results.json").read_text())
    audit=json.loads((root/"audit.json").read_text())
    manifest=json.loads((root/"inputs.json").read_text())
    if not audit.get("passed") or not report.get("input_metadata_unchanged"):
        raise ValueError("별도 기간 검증 감사 미완료")
    for rel,stamp in manifest.items():
        path=m.ROOT/rel
        stat=path.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(stamp["size"],stamp["mtime_ns"]):
            raise ValueError("입력 자료 변경")
        # Databases are never rehashed or queried by the presentation request.
        if path.suffix!=".sqlite" and m.sha(path)!=stamp["sha256"]:
            raise ValueError("입력 지문 불일치")
    periods=report["protocol"]["periods"]
    result={"available":True,"checked_conditions":sum(len(f["configs"]) for c in report["cities"].values() for stage in ("development","evaluation") for f in c[stage]),
            "matching_checks":audit["matching_metric_checks"],"service_period_start":m.START,"service_period_end":m.END,
            "development_period_start":periods["development"][0],"development_period_end":periods["development"][1],
            "evaluation_period_start":periods["evaluation"][0],"evaluation_period_end":periods["evaluation"][1],
            "decision":"운영 추천 유지 · 정확도 향상 미입증",
            "scope_note":"6·7월은 별도 방법 실험입니다. 서비스 공통 기준인 2025년12월 결과를 대체하지 않습니다.",
            "cities":{}}
    for city,c in report["cities"].items():
        original=next(r for r in report["original_december_diagnostics"][city] if r["fold"]=="high_usage")
        selected=c["selected_summary"][0]
        baseline=c["baseline_summary"][0]
        final=c["evaluation"][0]
        result["cities"][city]={"city":city,"original":original,
            "comparison":{"target_definition":"교통 공백 조건에 맞는 이용 상위 대여소10곳",
                          "target_count":selected["n"],"baseline_hits":baseline["hits10"],
                          "selected_hits":selected["hits10"],
                          "generation_500m":final["configs"]["500:equal"]["generation_possible"],
                          "generation_250m":final["configs"]["250:equal"]["generation_possible"]},
            "other_evaluations":[{"name":"무작위 표본" if r["fold"]=="gap_random" else "1km 구역 전체",
                                  "hits":r["hits10"],"target_count":r["n"]} for r in c["selected_summary"][1:]],
            "decision":result["decision"]}
    return result

def read(city="all"):
    if city not in (*m.CITIES,"all"):
        return {"available":False,"message":"지원하지 않는 도시입니다."}
    try:
        manifest=json.loads((DIRECTORY/"inputs.json").read_text())
        paths=[DIRECTORY/name for name in ("results.json","audit.json","inputs.json","presentation-manifest.json")]
        paths += [m.ROOT/rel for rel in manifest]
        signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
        data=copy.deepcopy(_summary(signature))
        data["cities"]=[data["cities"][c] for c in (m.CITIES if city=="all" else (city,))]
        return data
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return {"available":False,"message":"추가 방법 실험 자료가 없거나 변경되어 재검증이 필요합니다. 기존12월 검증 결과는 유지합니다."}
