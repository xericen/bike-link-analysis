"""Presentation-only labels and audited footnotes. No KPI calculations or cache writes."""
import copy,json,re
from pathlib import Path
from functools import lru_cache
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[2]
ANCHOR_NAMES={"seoul":"지하철역","daejeon":"지하철역","sejong":"BRT 정류장"}
def anchor_name(city):return ANCHOR_NAMES.get(city,"도시별 지하철역/BRT 정류장")
def distance_label(city):return "최근접 "+anchor_name(city)+"(앵커) 거리"
def contextualize(result,city):
    result=copy.deepcopy(result)
    result["anchor_type"]=anchor_name(city);result["distance_label"]=distance_label(city)
    for row in result.get("ranking",[]):row["distance_label"]=distance_label(city)
    result["limitations"]=[anchor_text(x,city) for x in result.get("limitations",[])]
    return result
def anchor_text(text,city):
    text=re.sub(r"(?<!일반 버스 )(?<!버스 )(?<!버스)최근접 정류장(?:까지의)? 거리",distance_label(city),text)
    text=re.sub(r"(?<!일반 버스 )(?<!버스 )(?<!버스)정류장과의 직선거리",anchor_name(city)+"(앵커)까지의 직선거리",text)
    return text.replace("정류장과 대여소의 직선거리",anchor_name(city)+"(앵커)와 대여소의 직선거리")
def scope_answer(answer,evidence):
    cities={e.get("result",{}).get("city") for e in evidence if e.get("tool") in {"get_transit_vulnerability","get_improvement_ranking","get_transit_linkage"}}
    cities.discard(None)
    if not cities:return answer
    city=next(iter(cities)) if len(cities)==1 else "all"
    answer=anchor_text(answer,city)
    # Score ranking is not a maximum-demand ranking; only correct a named first-ranked row.
    for item in evidence:
        ranked=item.get("result",{}).get("ranking",[])
        if item.get("tool") not in {"get_transit_vulnerability","get_improvement_ranking"} or not ranked:continue
        first=ranked[0].get("station_id","")
        pattern=r"상위\s*5곳\s*중\s*최대\s*수요는\s*[^。\n]*?\("+re.escape(first)+r"\)"
        match=re.search(pattern,answer)
        if first and match:
            corrected=re.sub(r"최대\s*수요는","개선 검토 우선순위가 가장 높은 후보는",match.group(),count=1)
            answer=answer[:match.start()]+corrected+answer[match.end():]
    if anchor_name(city) not in answer:answer="분석 앵커: "+anchor_name(city)+".\n"+answer
    return answer
@lru_cache(maxsize=4)
def _read(path,mtime,size):return json.loads(Path(path).read_text())
def context(city,start,end):
    from backend.services import precomputed
    p=ROOT/"docs/anchor_presentation_context.json"
    if not p.exists():raise HTTPException(409,"표시용 DB 각주 검증 기록이 없습니다.")
    value=_read(str(p),p.stat().st_mtime_ns,p.stat().st_size)
    if value["revision"]!=precomputed.revision():raise HTTPException(409,"현재 자료에 맞는 표시용 각주 검증이 필요합니다.")
    key="|".join((city,start or "",end or ""))
    if key not in value["contexts"]:raise HTTPException(409,"선택 기간의 표시용 각주가 미준비 상태입니다.")
    return value["contexts"][key]
