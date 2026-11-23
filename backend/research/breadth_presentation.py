"""Optional, strictly read-only broad experiment evidence. Never changes operating scores."""
import copy,json
from functools import lru_cache
from backend.research import recovery_breadth as b, method_validation as m
from scripts.validate.audit_recovery_breadth import label

@lru_cache(maxsize=3)
def _load(signature):
    out=b.OUT
    audit=json.loads((out/"audit.json").read_text())
    if not audit.get("passed"):raise ValueError("Audit incomplete")
    for name,digest in audit["artifacts"].items():
        if m.sha(out/name)!=digest:raise ValueError("Artifact changed")
    manifest=json.loads((out/"inputs.json").read_text())
    for rel,value in manifest.items():
        path=m.ROOT/rel;stat=path.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(value["size"],value["mtime_ns"]):raise ValueError("Input changed")
        if path.suffix!=".sqlite" and m.sha(path)!=value["sha256"]:raise ValueError("Input hash changed")
    source=json.loads((out/"results.json").read_text())
    result={"available":True,"period_start":"2025-12-01","period_end":"2025-12-31",
            "combination_count":len(b.CONFIGS),"matching_checks":audit["matching_checks"],
            "exploratory":True,"operational_update":False,
            "notice":"12월은 이미 결과를 본 자료의 탐색 최고값입니다. 독립 검증 성공으로 해석하지 않습니다.",
            "diagnostic_notice":"50m진단은 기존 대여소와의 간격을 완화한 별도 실험이며 신규 설치 추천이 아닙니다.",
            "evaluation_start":source["protocol"]["evaluation"][0],
            "evaluation_end":source["protocol"]["evaluation"][1],"cities":{}}
    for city,c in source["cities"].items():
        f=c["exploration"][0]
        strict=max(b.STRICT,key=lambda k:f["methods"][k]["matches"]["10"]["hits"])
        diagnostic=max(b.DIAGNOSTIC,key=lambda k:f["methods"][k]["matches"]["10"]["hits"])
        def item(key):
            v=f["methods"][key]
            return {"method":key,"label":label(key),"hits":v["matches"]["10"]["hits"],
                    "possible":v["generation_possible"],"target_count":f["target_count"]}
        result["cities"][city]={"city":city,"baseline":item("legacy500:original"),
                               "strict":item(strict),"diagnostic":item(diagnostic),
                               "locked_strict_method":label(c["selection"]["strict"]),
                               "locked_diagnostic_method":label(c["selection"]["diagnostic"]),
                               "evaluation":[{"fold":row["name"],"target_count":row["target_count"],
                                              "baseline_hits":row["methods"]["legacy500:original"]["matches"]["10"]["hits"],
                                              "strict_hits":row["methods"][c["selection"]["strict"]]["matches"]["10"]["hits"],
                                              "diagnostic_hits":row["methods"][c["selection"]["diagnostic"]]["matches"]["10"]["hits"]}
                                             for row in c["evaluation"]]}
    return result

def read(city="all"):
    if city not in (*m.CITIES,"all"):return {"available":False,"message":"지원하지 않는 도시"}
    try:
        manifest=json.loads((b.OUT/"inputs.json").read_text())
        paths=[b.OUT/name for name in ("results.json","audit.json","inputs.json","protocol.json")]
        paths += [m.ROOT/rel for rel in manifest]
        signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
        result=copy.deepcopy(_load(signature))
        result["cities"]=[result["cities"][c] for c in (m.CITIES if city=="all" else (city,))]
        return result
    except (OSError,ValueError,KeyError,TypeError):
        return {"available":False,"message":"확장 실험 자료가 없거나 변경되어 재검증이 필요합니다. 기존 결과는 유지합니다."}
