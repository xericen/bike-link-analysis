"""Prepared whole-period/whole-city recovery. No fallback to common December data."""
import copy,json
from functools import lru_cache
from backend.research import method_validation as m

OUT=m.ROOT/"docs/recovery-individual-20261123"
@lru_cache(maxsize=3)
def _read(signature):
    audit=json.loads((OUT/"audit.json").read_text())
    if not audit.get("passed"):raise ValueError("Audit missing")
    for name,digest in audit["artifacts"].items():
        if m.sha(OUT/name)!=digest:raise ValueError("Result changed")
    inputs=json.loads((OUT/"inputs.json").read_text())
    for rel,value in inputs.items():
        p=m.ROOT/rel;s=p.stat()
        if (s.st_size,s.st_mtime_ns)!=(value["size"],value["mtime_ns"]):raise ValueError("Input changed")
        if p.suffix!=".sqlite" and m.sha(p)!=value["sha256"]:raise ValueError("Source hash changed")
    return json.loads((OUT/"summary.json").read_text())

def read(city,start=None,end=None):
    if city not in m.CITIES:return {"available":False,"scope":"individual_full","message":"개별 도시를 선택하세요."}
    try:
        inputs=json.loads((OUT/"inputs.json").read_text())
        paths=[OUT/n for n in ("summary.json","audit.json","inputs.json","protocol.json")]
        paths += [m.ROOT/rel for rel in inputs]
        signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
        summary=copy.deepcopy(_read(signature)["cities"][city])
        if start not in (None,summary["period_start"]) or end not in (None,summary["period_end"]):
            return {"available":False,"scope":"individual_full","message":"개별 도시 검증은 보유 전체 기간만 준비되어 있습니다."}
        return {"available":True,"scope":"individual_full","city":city,
                "period_start":summary["period_start"],"period_end":summary["period_end"],
                "scope_note":summary["scope_note"],"combination_count":46,"summary":summary,
                "exploratory":True,"operational_update":False,"matching_checks":json.loads((OUT/"audit.json").read_text())["matching_checks"]}
    except (OSError,ValueError,KeyError,TypeError):
        return {"available":False,"scope":"individual_full","message":"도시 전체 기간의 검증 결과를 준비 중입니다. 공통12월 결과로 대체하지 않습니다."}
