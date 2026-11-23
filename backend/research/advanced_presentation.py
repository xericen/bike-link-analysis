"""Read-only research bundle, exact scope matching and no calculation in requests."""
import copy,json
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException
from backend.presentation import individual
ROOT=Path(__file__).resolve().parents[2]
FILE=ROOT/"docs/advanced-research-20261123/results.json"
@lru_cache(maxsize=2)
def _load(stamp,size):
    value=json.loads(FILE.read_text())
    for rel,meta in value.get("inputs",{}).items():
        p=ROOT/rel
        if not p.exists() or (p.stat().st_size,p.stat().st_mtime_ns)!=(meta["size"],meta["mtime_ns"]):
            raise HTTPException(409,"고도화 실험의 입력이 변경되어 재검증이 필요합니다.")
    return value
def read(city="all",scope=None,start=None,end=None):
    if city not in {"all","seoul","daejeon","sejong"}:raise HTTPException(404,"지원하지 않는 도시입니다.")
    scope=scope or ("common" if city=="all" or (start,end)==("2025-12-01","2025-12-31") else "individual")
    if scope not in {"common","individual"} or (city=="all" and scope!="common"):raise HTTPException(422,"전체는 공통 기간만 비교합니다.")
    if not FILE.exists():raise HTTPException(409,"고도화 실험 준비 중입니다.")
    value=_load(FILE.stat().st_mtime_ns,FILE.stat().st_size)
    # Recheck cheap metadata on every request even when JSON itself is cached.
    for rel,meta in value.get("inputs",{}).items():
        p=ROOT/rel
        if not p.exists() or (p.stat().st_size,p.stat().st_mtime_ns)!=(meta["size"],meta["mtime_ns"]):
            raise HTTPException(409,"실험 입력이 변경되어 재검증이 필요합니다.")
    ids=["seoul","daejeon","sejong"] if city=="all" else [city]
    cities=copy.deepcopy([value["scopes"][scope][c] for c in ids])
    for row in cities:
        if (start is not None or end is not None) and (start,end)!=(row["period_start"],row["period_end"]):raise HTTPException(422,"요청과 실험의 관측기간이 다릅니다.")
        current=individual.scope(row["city"])["revision"] if scope=="individual" else None
        if current is not None and row["source_revision"]!=current:raise HTTPException(409,"개별 기간 분석 버전이 변경되었습니다.")
    return {"available":True,"scope":scope,"period_start":cities[0]["period_start"],"period_end":cities[0]["period_end"],
       "built_at":value["built_at"],"operational_update":False,"cities":cities,
       "headline_ci":value["common_all_ci"] if city=="all" else cities[0]["headline_ci"],
       "benchmark":value.get("benchmark",{"available":False,"reason":"실측 준비 중"}),
       "agent_evaluation":value.get("agent_evaluation",{"available":False,"reason":"평가 준비 중"}),
       "relocation":value["relocation"]}
def tool(city,start=None,end=None):
    result=read(city,start=start,end=end)
    sources=[]
    for row in result["cities"]:
        for key in ("code_hash","methods_hash","source_revision"):row.pop(key,None)
        if row["scope"]=="individual":
            meta=json.loads((ROOT/"data/individual"/row["city"]/"sources.json").read_text())
        else:
            from backend.services.precomputed import read as common_read
            meta=common_read("overview",row["city"],row["period_start"],row["period_end"]).get("sources",[])
        sources.extend(meta)
        for comparison in row["location"].get("comparisons",[]):
            comparison["solver"].pop("selected",None)
        row["location"].pop("candidate_sites",None)
        row["headline_ci"].pop("block_sensitivity",None)
    result["sources"]={r["source_id"]:r for r in sources}.values()
    result["sources"]=list(result["sources"])
    result["source_names"]=[r["dataset_name"] for r in result["sources"]]
    result.pop("benchmark",None)
    result.pop("agent_evaluation",None)
    return result
