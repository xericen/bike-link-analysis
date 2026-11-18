"""Read-only, revision-checked decision studies. No routing or model calls on requests."""
import copy,json
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException
from backend.services import precomputed
ROOT=Path(__file__).resolve().parents[2]
FILE=ROOT/"data/processed/research/decision-evidence.json"
@lru_cache(maxsize=2)
def _read(path,stamp,size):return json.loads(Path(path).read_text())
def read(city,start=None,end=None):
    if city not in {"seoul","daejeon","sejong","all"}:raise HTTPException(404,"지원하지 않는 도시입니다.")
    if not FILE.exists():raise HTTPException(409,"최종 의사결정 근거 검증 패키지가 아직 준비되지 않았습니다.")
    data=_read(str(FILE),FILE.stat().st_mtime_ns,FILE.stat().st_size)
    if data.get("revision")!=precomputed.revision():raise HTTPException(409,"현재 자료에 맞는 의사결정 근거를 다시 검증해야 합니다.")
    if city=="all":
        return {"available":True,"city":"all","profiles":copy.deepcopy(list(data["profiles"].values())),
                "transfer_audit":data["transfer_audit"],"agent_evaluation":data.get("agent_evaluation"),
                "comparison_note":"서울·대전·세종 공통 2025-12 사례. 도시별 수요 규모와 자료·좌표 조건을 함께 확인합니다."}
    profile=copy.deepcopy(data["profiles"][city])
    profile["available"]=True
    profile["matches_selected_period"]=(start in (None,profile["period_start"]) and end in (None,profile["period_end"]))
    profile["selected_period"]={"start":start,"end":end}
    profile["transfer_audit"]=copy.deepcopy(data["transfer_audit"]) if city=="sejong" else {
        "definition_status":"unavailable","actual_transfer_rate":None,"message":"실제 환승 여부 미확인. 앵커 근접 이동은 환승 가능성 지표입니다."}
    profile["agent_evaluation"]=data.get("agent_evaluation")
    return profile
