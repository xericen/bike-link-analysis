import json
import os

from fastapi import HTTPException
from openai import OpenAI

from backend.services import real_data

TOOL_SPEC = [
    ("get_region_overview", "지역별 확보 현황, 실제 이용 건수와 관측 기간", ["region_id"]),
    ("get_station_clusters", "실제 이용 기록의 K-means 군집", ["region_id"]),
    ("get_network_analysis", "실제 OD 연결 관계 또는 미확보 사유", ["region_id"]),
    ("get_centrality_ranking", "OD 기반 PageRank와 가중 차수", ["region_id"]),
    ("find_similar_stations", "정규화된 이용 패턴 유사 대여소", ["region_id", "station_id"]),
    ("compare_region_patterns", "4개 지역의 데이터 기간 및 비교 한계", []),
    ("get_data_availability", "지역별 데이터셋·컬럼·확보 상태", ["region_id"]),
]
TOOLS = [{"type": "function", "function": {"name": name, "description": description,
    "parameters": {"type": "object", "properties": {key: {"type": "string"} for key in args},
                   "required": args, "additionalProperties": False}}} for name, description, args in TOOL_SPEC]


def run_tool(name, arguments):
    region_id = arguments.get("region_id")
    if region_id and region_id not in {r["region_id"] for r in real_data.REGIONS}:
        return {"error": "존재하지 않는 지역", "region_id": region_id}
    if name == "get_region_overview" and region_id:
        result = real_data.overview(region_id)
        result.pop("map_stations", None)
        return result
    if name == "get_station_clusters" and region_id:
        result = real_data.clusters(region_id)
        return {**result, "clusters": result["clusters"][:20], "total_clusters": len(result["clusters"])}
    if name == "get_network_analysis" and region_id:
        result = real_data.network(region_id)
        return {**result, "nodes": result["nodes"][:10], "edges": result["edges"][:20]}
    if name == "get_centrality_ranking" and region_id:
        result = real_data.centrality_result(region_id)
        return {**result, "rankings": result["rankings"][:20]}
    if name == "find_similar_stations" and region_id and arguments.get("station_id"):
        try:
            return real_data.similarity_result(region_id, arguments["station_id"])
        except ValueError as exc:
            return {"error": str(exc)}
    if name == "compare_region_patterns":
        return real_data.compare(None)
    if name == "get_data_availability" and region_id:
        overview = real_data.overview(region_id)
        return {"region_id": region_id, "sources": overview["sources"],
                "has_od": overview["has_od"], "total_rentals": overview["total_rentals"],
                "coverage_note": overview["coverage_note"]}
    return {"error": "허용되지 않았거나 필수 인자가 없는 도구"}


def chat(question):
    api_key = os.getenv("UPSTAGE_API_KEY")
    if not api_key:
        raise HTTPException(503, "UPSTAGE_API_KEY가 없습니다. .env에 설정하세요.")
    client = OpenAI(api_key=api_key, base_url="https://api.upstage.ai/v1", timeout=30.0)
    prompt = ("공공자전거 4개 지역 분석 도우미입니다. 먼저 도구를 호출하세요. "
              "도구가 반환한 실제 수치만 사용하고, 데이터가 없거나 비교 기간이 다르면 명확히 설명하세요. "
              "서울 OD는 개별 Trip이 아닌 집계입니다. 대전은 개별 Trip을 확보했으며, 세종은 연간 총량만, 부산은 통합 이용 자료가 없습니다. "
              "출처와 관측 기간을 답변에 포함하세요. 추측하거나 가상 수치를 만들지 마세요.")
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": question}]
    evidence = []
    try:
        for step in range(3):
            completion = client.chat.completions.create(
                model=os.getenv("UPSTAGE_MODEL", "solar-mini4"), messages=messages,
                tools=TOOLS, tool_choice="required" if step == 0 else "auto")
            reply = completion.choices[0].message
            if not reply.tool_calls:
                if evidence:
                    return {"answer": reply.content or "분석 결과를 요약할 수 없습니다.", "evidence": evidence}
                return {"answer": "조회된 분석 근거가 없어 답변할 수 없습니다.", "evidence": []}
            messages.append(reply.model_dump(exclude_none=True))
            for call in reply.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                    if not isinstance(args, dict):
                        args = {}
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(call.function.name, args)
                evidence.append({"tool": call.function.name, "arguments": args, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result, ensure_ascii=False)})
        completion = client.chat.completions.create(
            model=os.getenv("UPSTAGE_MODEL", "solar-mini4"), messages=messages, tool_choice="none")
        return {"answer": completion.choices[0].message.content or "분석 결과를 요약할 수 없습니다.",
                "evidence": evidence}
    except Exception as exc:
        raise HTTPException(502, f"Solar API 호출 실패: {type(exc).__name__}") from exc
