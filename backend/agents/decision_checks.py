"""Narrow checks for new decision-study claims; never a full prose truth guarantee."""
import re,math
def check(answer,evidence):
    claims=[]
    for e in evidence:
        if e.get("tool")!="get_decision_evidence" or not e.get("result",{}).get("available"):continue
        result=e["result"];routes={r["candidate_id"]:r for r in result.get("route_audit",[])}
        known={r["site_id"] for r in result.get("top3",[])}|set(routes)
        mentions=list(re.finditer(r"grid-\d+-\d+",answer))
        for i,m in enumerate(mentions):
            sid=m.group()
            if sid not in known:claims.append({"reason":"근거에 없는 격자 후보","candidate_id":sid})
            chunk=answer[m.end():mentions[i+1].start() if i+1<len(mentions) else len(answer)]
            for mode,dist in re.findall(r"(도보|보행|자전거)\s*([\d,]+(?:\.\d+)?)\s*m",chunk):
                route=routes.get(sid,{}).get("routes",{}).get("bike" if mode=="자전거" else "foot",{})
                if not route or not math.isclose(float(dist.replace(",","")),route["distance_m"],abs_tol=1):
                    claims.append({"reason":"후보와 경로 거리의 연결 불일치 또는 미검증","candidate_id":sid})
        if result.get("city")=="sejong":
            # A denial such as '대체하지 않았음' is allowed.
            invalid=re.search(r"(?:인구밀도|행정구)[^.\n]{0,70}(?:밀도로\s*대체(?:했|하였)|밀도(?:를|만)?\s*사용(?:했|하였))",answer)
            if invalid:claims.append({"reason":"세종 인구밀도 제외 조건과 불일치"})
    return {"passed":not claims,"unsupported_claims":claims,"method":"격자 ID·후보별 도로 거리·세종 인구 제외 조건만 검사. 전체 자유 서술 검증 아님."}
