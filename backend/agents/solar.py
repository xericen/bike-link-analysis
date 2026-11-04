"""Solar tool calling over verified, local analysis results."""
import json
import os
import re
import time
from datetime import date

from fastapi import HTTPException
from openai import AuthenticationError, OpenAI, RateLimitError, APITimeoutError, APIConnectionError, APIStatusError

from backend.services import real_data

REGION_ALIASES = {"서울": "seoul", "따릉이": "seoul", "대전": "daejeon", "타슈": "daejeon",
                  "세종": "sejong", "어울링": "sejong", "부산": "busan"}
REGIONS = {r["region_id"] for r in real_data.REGIONS}
METRICS = {"pagerank", "weighted_in_degree", "weighted_out_degree", "betweenness"}
TOOL_DEFINITIONS = {
    "get_region_overview": ("지역의 관측 기간, 이용량, 시간대별 이용과 출처", {"region_id": "string", "date_range": "object"}, ["region_id"]),
    "get_station_details": ("대여소 실제 이용량, 좌표, 군집 세부 정보", {"region_id": "string", "station_id": "string", "date_range": "object"}, ["region_id", "station_id"]),
    "get_station_clusters": ("실제 이용 기록의 K-means 군집과 유형", {"region_id": "string", "date_range": "object"}, ["region_id"]),
    "get_centrality_ranking": ("전체 OD 그래프에서 계산한 중심성 순위", {"region_id": "string", "metric": "string", "top_n": "integer", "date_range": "object"}, ["region_id", "metric"]),
    "get_network_analysis": ("실제 OD 이동 연결, 상위 PageRank 노드 시각화", {"region_id": "string", "filters": "object", "date_range": "object"}, ["region_id"]),
    "find_similar_stations": ("시간대 패턴 코사인 유사 대여소", {"region_id": "string", "station_id": "string", "top_n": "integer", "date_range": "object"}, ["region_id", "station_id"]),
    "compare_region_patterns": ("지역별 기간과 비교 가능 범위", {"region_ids": "array", "date_range": "object"}, ["region_ids"]),
    "get_data_availability": ("원천 자료의 확보 상태 및 분석 가능 범위", {"region_id": "string"}, ["region_id"]),
}
def _schema(name, description, fields, required):
    props = {}
    for key, kind in fields.items():
        if key == "date_range":
            props[key] = {"type": "object", "properties": {"date_start": {"type": "string"}, "date_end": {"type": "string"}}, "additionalProperties": False}
        elif key == "filters":
            props[key] = {"type": "object", "properties": {"node_limit": {"type": "integer"}}, "additionalProperties": False}
        elif key == "region_ids":
            props[key] = {"type": "array", "items": {"type": "string"}}
        else:
            props[key] = {"type": kind}
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required, "additionalProperties": False}}}
TOOLS = [_schema(name, *spec) for name, spec in TOOL_DEFINITIONS.items()]


def _region(value):
    rid = REGION_ALIASES.get(value, value)
    if isinstance(rid, str):
        rid = rid.lower()
    if rid not in REGIONS:
        raise ValueError("존재하지 않는 지역입니다.")
    return rid


def _dates(arguments):
    value = arguments.get("date_range") or {}
    if not isinstance(value, dict) or set(value) - {"date_start", "date_end"}:
        raise ValueError("분석 기간 형식이 올바르지 않습니다.")
    start, end = value.get("date_start"), value.get("date_end")
    for item in (start, end):
        if item is not None:
            date.fromisoformat(item)
    if start and end and start > end:
        raise ValueError("시작일이 종료일보다 늦습니다.")
    return start, end


def _top(value, default=5):
    n = default if value is None else value
    if type(n) is not int or not 1 <= n <= 20:
        raise ValueError("top_n은 1~20이어야 합니다.")
    return n


def run_tool(name, arguments):
    """Return compact actual data. Invalid calls are explicit errors, never fabricated facts."""
    try:
        if name not in TOOL_DEFINITIONS or not isinstance(arguments, dict):
            raise ValueError("허용되지 않는 도구 또는 인자입니다.")
        allowed = set(TOOL_DEFINITIONS[name][1])
        if set(arguments) - allowed:
            raise ValueError("허용되지 않는 도구 인자가 있습니다.")
        if name == "compare_region_patterns":
            ids = arguments.get("region_ids")
            if not isinstance(ids, list) or not 1 <= len(ids) <= 4:
                raise ValueError("region_ids는 1~4개 지역 배열이어야 합니다.")
            ids = list(dict.fromkeys(_region(x) for x in ids))
            start, end = _dates(arguments)
            return real_data.compare(ids, start, end)
        region_id = _region(arguments.get("region_id"))
        start, end = _dates(arguments)
        if name == "get_region_overview":
            result = real_data.overview(region_id, start, end)
            result.pop("map_stations", None)
            return result
        if name == "get_station_details":
            station_id = arguments.get("station_id")
            if not isinstance(station_id, str) or not station_id:
                raise ValueError("station_id가 필요합니다.")
            item = next((s for s in real_data.region_stations(region_id, start, end) if s["station_id"] == station_id), None)
            if item is None:
                return {"available": False, "message": "대여소 ID가 확인되지 않았습니다.", "station_id": station_id}
            cluster = next((c for c in real_data.clusters(region_id, start, end)["clusters"] if c["station_id"] == station_id), None)
            return {**real_data.source_meta(region_id), "available": True, "station": item, "cluster": cluster,
                    "observed_dates": real_data.observed_dates(region_id, start, end)}
        if name == "get_station_clusters":
            result = real_data.clusters(region_id, start, end)
            return {**result, "clusters": result["clusters"][:20], "returned_count": min(20, len(result["clusters"]))}
        if name == "get_centrality_ranking":
            metric = str(arguments.get("metric", "")).lower().replace("page_rank", "pagerank").replace("weighted_degree", "weighted_in_degree")
            if metric not in METRICS:
                raise ValueError("metric은 pagerank, weighted_in_degree, weighted_out_degree, betweenness 중 하나여야 합니다.")
            result = real_data.centrality_result(region_id, start, end)
            rankings = sorted(result["rankings"], key=lambda x: x[metric], reverse=True)[:_top(arguments.get("top_n"))]
            usage = sorted((p for p in real_data.profiles(region_id, start, end) if p["rental_count"] is not None),
                           key=lambda p: p["rental_count"], reverse=True)
            usage_rank = {p["station_id"]: index for index, p in enumerate(usage, 1)}
            usage_count = {p["station_id"]: p["rental_count"] for p in usage}
            rankings = [{**row, "centrality_rank": index,
                         "rental_count": usage_count.get(row["station_id"]),
                         "usage_rank": usage_rank.get(row["station_id"])}
                        for index, row in enumerate(rankings, 1)]
            return {**result, "metric": metric, "rankings": rankings,
                    "period_start": (real_data.observed_dates(region_id, start, end) or [None])[0],
                    "period_end": (real_data.observed_dates(region_id, start, end) or [None])[-1]}
        if name == "get_network_analysis":
            filters = arguments.get("filters") or {}
            if not isinstance(filters, dict) or set(filters) - {"node_limit"}:
                raise ValueError("filters 형식이 올바르지 않습니다.")
            limit = filters.get("node_limit", 30)
            if limit not in (30, 40, 50):
                raise ValueError("node_limit은 30, 40, 50 중 하나여야 합니다.")
            result = real_data.network(region_id, start, end, limit)
            return {**result, "nodes": result["nodes"][:10], "edges": result["edges"][:20],
                    "returned_nodes": min(10, len(result["nodes"])), "returned_edges": min(20, len(result["edges"]))}
        if name == "find_similar_stations":
            station_id = arguments.get("station_id")
            if not isinstance(station_id, str) or not station_id:
                raise ValueError("station_id가 필요합니다.")
            result = real_data.similarity_result(region_id, station_id, start, end)
            return {**result, "similar": result["similar"][:_top(arguments.get("top_n"))]}
        if name == "get_data_availability":
            result = real_data.overview(region_id)
            return {k: result[k] for k in ("region_id", "region_name", "service_name", "sources",
                    "total_rentals", "annual_latest", "has_od", "coverage_note", "period_start", "period_end")}
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}
    return {"error": "허용되지 않는 도구입니다."}


def _report(question, answer, evidence):
    """Cards and charts are copied only from tool results, never from model prose."""
    findings, charts, sources, periods, algorithms, limitations, roles, recommendations = [], [], [], set(), set(), [], [], []
    for call in evidence:
        result = call["result"]
        if result.get("error"):
            continue
        for source in result.get("sources", []):
            if source.get("dataset_name"):
                entry = {"dataset_name": source["dataset_name"], "source_url": source.get("source_url"),
                         "verification_status": source.get("verification_status")}
                if entry not in sources:
                    sources.append(entry)
        for field in ("period_start", "period_end"):
            if result.get(field):
                periods.add(result[field])
        if result.get("coverage_note"):
            limitations.append(result["coverage_note"])
        if result.get("message") and result.get("available") is False:
            limitations.append(result["message"])
        if call["tool"] == "get_region_overview":
            if result.get("total_rentals") is not None:
                findings.append({"label": result["region_name"] + " 이용 건수", "value": result["total_rentals"],
                                 "unit": "건", "region_id": result["region_id"]})
            elif result.get("annual_latest"):
                annual = result["annual_latest"]
                findings.append({"label": result["region_name"] + " 연간 이용량", "value": annual["rental_count"],
                                 "unit": "건", "region_id": result["region_id"], "period": str(annual["year"])})
            if result.get("daily"):
                charts.append({"title": result["region_name"] + " 관측일 이용량", "kind": "daily", "points": result["daily"]})
        elif call["tool"] == "get_centrality_ranking" and result.get("available"):
            metric = result["metric"]
            algorithms.add(metric)
            if result["rankings"]:
                top = result["rankings"][0]
                findings.append({"label": top["station_id"] + " " + metric, "value": top[metric],
                                 "unit": "지표", "region_id": call["arguments"].get("region_id", "")})
                recommendations.append({"feature": metric + " 상위 연결 대여소",
                    "evidence": top["station_id"] + " / " + metric + " " + str(top[metric]),
                    "action": "해당 대여소의 운영 현황을 우선 모니터링하세요.",
                    "value": "연결 구조상 중요한 지점을 검토할 수 있습니다.",
                    "validation": "실제 재고와 장기간 이용 기록으로 운영 효과를 추가 검증해야 합니다."})
            charts.append({"title": result["rankings"][0]["station_id"] + " 등 " + metric + " 순위" if result["rankings"] else metric,
                           "kind": "ranking", "metric": metric,
                           "points": [{"station_id": row["station_id"], "station_name": row["station_name"], "value": row[metric]}
                                      for row in result["rankings"]]})
        elif call["tool"] == "get_station_clusters" and result.get("available"):
            algorithms.add("K-means")
            roles.extend({"station_id": c["station_id"], "role": c["role"], "cluster_id": c["cluster_id"]}
                         for c in result.get("clusters", [])[:5] if c.get("role"))
        elif call["tool"] == "find_similar_stations" and result.get("available"):
            algorithms.add("cosine similarity")
        elif call["tool"] == "get_station_details" and result.get("available"):
            cluster = result.get("cluster")
            if cluster and cluster.get("role"):
                roles.append({"station_id": result["station"]["station_id"], "role": cluster["role"],
                              "cluster_id": cluster["cluster_id"]})
        elif call["tool"] == "get_network_analysis" and result.get("available"):
            algorithms.add("directed OD graph")
        elif call["tool"] == "get_data_availability":
            if result.get("annual_latest"):
                annual = result["annual_latest"]
                findings.append({"label": result["region_name"] + " 연간 이용량", "value": annual["rental_count"],
                                 "unit": "건", "region_id": result["region_id"], "period": str(annual["year"])})
        elif call["tool"] == "compare_region_patterns":
            limitations.extend(result.get("limitations", []))
            for row in result.get("regions", []):
                for source in row.get("sources", []):
                    entry = {"dataset_name": source.get("dataset_name"), "source_url": source.get("source_url"),
                             "verification_status": source.get("verification_status")}
                    if entry["dataset_name"] and entry not in sources:
                        sources.append(entry)
                for field in ("period_start", "period_end"):
                    if row.get(field):
                        periods.add(row[field])
                if row.get("total_rentals") is not None:
                    findings.append({"label": row["region_name"] + " 이용 건수", "value": row["total_rentals"],
                                     "unit": "건", "region_id": row["region_id"]})
    if any(c["tool"] == "get_centrality_ranking" for c in evidence):
        limitations.append("중심성은 이용량과 다른 지표입니다. 서울은 집계 OD, 대전은 개별 Trip을 사용합니다.")
    if not evidence:
        limitations.append("분석 도구 결과가 없어 사실 기반 보고서를 만들 수 없습니다.")
    comparisons = []
    for call in evidence:
        if call["tool"] != "get_station_details" or not call["result"].get("available"):
            continue
        station = call["result"]["station"]
        for rank_call in evidence:
            if rank_call["tool"] != "get_centrality_ranking" or not rank_call["result"].get("available"):
                continue
            match = next((x for x in rank_call["result"]["rankings"] if x["station_id"] == station["station_id"]), None)
            if match:
                comparisons.append({"station_id": station["station_id"], "station_name": station.get("station_name"),
                                    "rental_count": station.get("rental_count"),
                                    "metric": rank_call["result"]["metric"],
                                    "centrality": match[rank_call["result"]["metric"]],
                                    "centrality_rank": match.get("centrality_rank"),
                                    "usage_rank": match.get("usage_rank"),
                                    "rank_gap": (match["usage_rank"] - match["centrality_rank"])
                                                if match.get("usage_rank") is not None else None})
                break
    comparisons = list({x["station_id"]: x for x in comparisons}.values())
    if len(comparisons) >= 2 and any(x.get("rank_gap") is not None for x in comparisons):
        charts.append({"title": "이용량 순위 − 중심성 순위", "kind": "ranking", "metric": "rank_gap",
                       "points": [{"station_id": x["station_id"], "value": x["rank_gap"]}
                                  for x in comparisons if x["rank_gap"] is not None]})
    findings = list({(x["label"], x["value"], x["unit"]): x for x in findings}.values())
    charts = list({(x["kind"], x["title"]): x for x in charts}.values())
    roles = list({x["station_id"]: x for x in roles}.values())
    recommendations = list({x["evidence"]: x for x in recommendations}.values())
    return {"question_summary": question, "key_findings": findings, "evidence": evidence,
            "algorithms": sorted(algorithms), "station_roles": roles,
            "recommendations": recommendations, "limitations": list(dict.fromkeys(limitations)),
            "sources": sources, "periods": sorted(periods), "charts": charts, "station_comparison": comparisons,
            "interpretation": answer}


def chat(question):
    if not os.getenv("UPSTAGE_API_KEY"):
        raise HTTPException(503, "UPSTAGE_API_KEY가 없습니다. .env에 설정하세요.")
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise HTTPException(400, "질문은 1~2000자로 입력하세요.")
    client = OpenAI(api_key=os.environ["UPSTAGE_API_KEY"], base_url="https://api.upstage.ai/v1",
                    timeout=25.0, max_retries=0)
    prompt = ("서울·대전·세종·부산 공공자전거 분석가입니다. 질문에 맞는 실제 도구를 먼저 호출하세요. "
              "서울 OD는 집계이며 위치 ID는 공식 마스터 검증분만 사용합니다. 대전은 개별 Trip, "
              "세종은 연간 총량, 부산은 운영 메타데이터만 있습니다. 관측 날짜는 불연속일 수 있습니다. "
              "도구 수치와 대여소 ID를 그대로 인용하고 없는 값을 만들지 마세요. "
              "관측 사실·해석·운영 제안을 분리한 한국어 답변을 작성하세요. "
              "재고 자료가 없으므로 부족을 단정하지 말고 PageRank를 환승의 증거로 단정하지 마세요. "
              "도구 오류나 자료 부족이면 불가능한 분석을 명시하세요.")
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": question}]
    evidence, usage = [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    started = time.monotonic()
    try:
        completion = client.chat.completions.create(model=os.getenv("UPSTAGE_MODEL", "solar-mini4"),
            messages=messages, tools=TOOLS, tool_choice="required", max_tokens=550)
        if completion.usage:
            for key in usage: usage[key] += getattr(completion.usage, key, 0) or 0
        reply = completion.choices[0].message
        if not reply.tool_calls:
            raise HTTPException(502, "Solar가 분석 도구를 선택하지 않았습니다.")
        messages.append(reply.model_dump(exclude_none=True))
        for call in reply.tool_calls:
            try: args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError: args = {}
            result = run_tool(call.function.name, args) if len(evidence) < 5 else {"error": "도구 호출 횟수 제한"}
            if len(evidence) < 5:
                evidence.append({"tool": call.function.name, "arguments": args, "result": result, "initiator": "solar"})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
        ids = list(dict.fromkeys(REGION_ALIASES[word] for word in REGION_ALIASES if word in question))
        if not ids:
            ids = [e["arguments"].get("region_id") for e in evidence if e["arguments"].get("region_id") in REGIONS][:1]
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", question)
        date_range = {"date_start": dates[0], "date_end": dates[1]} if len(dates) > 1 else ({"date_start": dates[0], "date_end": dates[0]} if dates else {})
        def ensure(name, args):
            if len(evidence) >= 8 or any(e["tool"] == name and not e["result"].get("error")
                and REGION_ALIASES.get(e["arguments"].get("region_id"), e["arguments"].get("region_id")) == args.get("region_id")
                and (not date_range or e["arguments"].get("date_range", {}) == date_range)
                and (name != "get_station_details" or e["arguments"].get("station_id") == args.get("station_id"))
                and (name != "get_centrality_ranking" or e["result"].get("metric") == args.get("metric"))
                and (name != "compare_region_patterns" or e["arguments"].get("region_ids") == args.get("region_ids"))
                for e in evidence):
                return
            result = run_tool(name, args)
            evidence.append({"tool": name, "arguments": args, "result": result, "initiator": "metric_guard"})
            messages.append({"role": "system", "content": "필수 지표 검증 결과 " + name + ": " + json.dumps(result, ensure_ascii=False, default=str)})
        if len(ids) >= 2 and ("비교" in question or "차이" in question):
            ensure("compare_region_patterns", {"region_ids": ids[:4], "date_range": date_range})
        for rid in ids[:2]:
            if any(word in question for word in ("PageRank", "페이지랭크", "중심성", "연결 거점", "거점")):
                metric = "betweenness" if "매개" in question else "pagerank"
                ensure("get_centrality_ranking", {"region_id": rid, "metric": metric, "top_n": 5, "date_range": date_range})
            if "군집" in question:
                ensure("get_station_clusters", {"region_id": rid, "date_range": date_range})
            if any(word in question for word in ("운영", "이용량", "패턴")):
                ensure("get_region_overview", {"region_id": rid, "date_range": date_range})
            if rid in ("sejong", "busan"):
                ensure("get_data_availability", {"region_id": rid})
            if "이용량" in question and "중심성" in question and rid in ("seoul", "daejeon"):
                ranking = next((e["result"] for e in evidence if e["tool"] == "get_centrality_ranking"
                                and e["result"].get("available") and e["arguments"].get("region_id") in (rid, "서울" if rid == "seoul" else "대전")), None)
                if ranking:
                    for item in ranking["rankings"][:3]:
                        ensure("get_station_details", {"region_id": rid, "station_id": item["station_id"],
                                                       "date_range": date_range})
        messages.append({"role": "system", "content": "이제 도구를 더 호출하지 마세요. 한국어 일반 문장만 작성하고 내부 도구 문법을 출력하지 마세요. 제공된 수치와 ID만 인용하세요. 오류가 난 도구 결과는 분석에 사용하지 마세요."})
        if time.monotonic() - started > 70:
            raise HTTPException(504, "분석 시간 제한을 초과했습니다.")
        completion = client.chat.completions.create(model=os.getenv("UPSTAGE_MODEL", "solar-mini4"),
            messages=messages, tools=TOOLS, tool_choice="none", max_tokens=850)
        if completion.usage:
            for key in usage: usage[key] += getattr(completion.usage, key, 0) or 0
        answer = completion.choices[0].message.content or ""
        if "<|tool_call" in answer or "<|tool_arg" in answer or not answer.strip():
            report = _report(question, "", evidence)
            if report["charts"]:
                answer = "검증된 분석 결과: " + "; ".join(str(p.get("station_id", p.get("date", ""))) + " " + str(p.get("value", p.get("rental_count", ""))) for p in report["charts"][0]["points"][:5])
            elif report["key_findings"]:
                answer = "확인된 자료: " + "; ".join(x["label"] + " " + str(x["value"]) + x["unit"] for x in report["key_findings"][:4])
            else:
                answer = "요청한 분석을 뒷받침할 자료가 부족하거나 Solar의 답변 형식을 확인할 수 없습니다."
            if report["limitations"]: answer += " 한계: " + report["limitations"][0]
        return {"answer": answer, "evidence": evidence, "report": _report(question, answer, evidence),
                "usage": usage, "model": completion.model}
    except AuthenticationError as exc:
        raise HTTPException(502, "Solar 인증 오류: API 키를 확인하세요.") from exc
    except RateLimitError as exc:
        raise HTTPException(429, "Solar 요청 한도에 도달했습니다. 잠시 후 다시 시도하세요.") from exc
    except APITimeoutError as exc:
        raise HTTPException(504, "Solar 응답 시간이 초과되었습니다.") from exc
    except APIConnectionError as exc:
        raise HTTPException(502, "Solar 서버 연결에 실패했습니다.") from exc
    except APIStatusError as exc:
        raise HTTPException(502, f"Solar API 오류 (HTTP {exc.status_code})") from exc
