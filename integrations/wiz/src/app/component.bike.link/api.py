"""WIZ adapter for the isolated Bike Link Analysis data and agent code."""
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException

ROOT = Path(wiz.project.path("bike-link-analysis"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import importlib
from backend.services import wiz_bridge
_bridge_revision = Path(wiz_bridge.__file__).stat().st_mtime_ns
if getattr(wiz_bridge, "_loaded_revision", None) != _bridge_revision:
    importlib.reload(wiz_bridge)
    wiz_bridge._loaded_revision = _bridge_revision
wiz_bridge.get_app()
from backend.services import real_data
from backend.services import periods
from backend.services import all_regions
_all_revision = Path(all_regions.__file__).stat().st_mtime_ns
if getattr(all_regions, "_loaded_revision", None) != _all_revision:
    importlib.reload(all_regions)
    all_regions._loaded_revision = _all_revision
from backend.agents.solar import chat


def handle():
    action = str(wiz.request.query("action", "overview"))
    region_id = str(wiz.request.query("region_id", "seoul"))
    station_id = str(wiz.request.query("station_id", ""))
    query = str(wiz.request.query("query", "")).strip()[:100]
    valid_regions = {item["region_id"] for item in real_data.REGIONS}
    if region_id not in valid_regions | {"all"}:
        return wiz.response.status(404, message="지역을 찾을 수 없습니다.")
    unified = region_id == "all"
    selected_region = "all" if action in ("compare", "compare_clusters") else region_id
    try:
        date_start, date_end = periods.resolve(selected_region,
            str(wiz.request.query("date_start", "")).strip() or None,
            str(wiz.request.query("date_end", "")).strip() or None) if action not in ("regions", "period_bounds") else (None, None)
    except ValueError as error:
        return wiz.response.status(422, message=str(error))
    context = {"region_ids": [r["region_id"] for r in real_data.REGIONS] if unified else [region_id],
               "date_start": date_start, "date_end": date_end}
    if unified and action in ("station", "station_history", "station_validation"):
        station_region = str(wiz.request.query("station_region_id", ""))
        if "::" in station_id:
            station_region, station_id = station_id.split("::", 1)
        if station_region not in valid_regions:
            return wiz.response.status(400, message="대여소의 실제 도시를 지정하세요.")
        region_id = station_region
    try:
        if action == "transit_vulnerability":
            from backend.services.vulnerability import analyze
            if unified:
                results = [analyze(rid, date_start, date_end) for rid in valid_regions]
                available = [r for r in results if r["available"]]
                result = {"available":bool(available),"cities":results,"candidates":[row for r in available for row in r["candidates"]],
                          "ranking":[row for r in available for row in r["ranking"]],
                          "candidate_count":sum(r["candidate_count"] for r in available),
                          "period_start":date_start,"period_end":date_end,
                          "message":"정류장 자료를 확보한 도시만 계산합니다. 미확보 도시 지표는 N/A입니다."}
            else:
                item = analyze(region_id,date_start,date_end)
                result = {**item,"cities":[item]}
        elif action == "period_bounds":
            result = {"regions": periods.all_bounds()}
        elif unified and action in ("overview", "network", "centrality", "research", "dashboard_extra"):
            result = all_regions.get(action, date_start, date_end)
        elif unified and action == "stations":
            items = all_regions.station_rows(date_start, date_end)
            if query:
                items = [item for item in items if query.lower() in (item["region_name"] + " " + item["station_id"] + " " + (item.get("station_name") or "")).lower()]
            items.sort(key=lambda item: item.get("rental_count") or 0, reverse=True)
            result = {"stations": items[:50], "total": len(items), "message": "공통 기간 통합 목록 · 실제 도시와 ID로 구분"}
        elif action == "regions":
            result = {"regions": [{**item, "availability": real_data.source_meta(item["region_id"])["verification_status"]}
                                  for item in real_data.REGIONS]}
        elif action == "overview":
            result = real_data.overview(region_id, date_start, date_end)
            # A bounded coordinate sample keeps the course page response small.
            map_stations = result.pop("map_stations", [])
            result["map_stations"] = [item for index, item in enumerate(map_stations)
                                      if index % max(1, len(map_stations) // 120) == 0][:120]
            result["map_sample_count"] = len(result["map_stations"])
        elif action == "dashboard_extra":
            from collections import defaultdict
            by_day = defaultdict(lambda: [0] * 24)
            if real_data.database_enabled():
                import sqlite3
                with sqlite3.connect(real_data.database_path()) as connection:
                    rows = connection.execute(
                        "SELECT date, hour, SUM(rental_count) FROM station_usage "
                        "WHERE region_id = ? AND date>=? AND date<=? AND hour IS NOT NULL GROUP BY date, hour",
                        (region_id, date_start or "0001-01-01", date_end or "9999-12-31")).fetchall()
                for day, hour, count in rows:
                    by_day[day][int(hour)] += int(count)
            else:
                for row in real_data.snapshot()["usage"]:
                    if row["region_id"] == region_id and row["hour"] is not None and (not date_start or row["date"] >= date_start) and (not date_end or row["date"] <= date_end):
                        by_day[row["date"]][row["hour"]] += row["rental_count"]
            heatmap = [{"date": day, "hours": hours} for day, hours in sorted(by_day.items())]
            result_clusters = real_data.clusters(region_id, date_start, date_end)
            profiles = {item["station_id"]: item for item in real_data.profiles(region_id, date_start, date_end)}
            grouped = defaultdict(list)
            for item in result_clusters["clusters"]:
                profile = profiles.get(item["station_id"])
                if not profile or not profile["hourly"] or not profile["rental_count"]:
                    continue
                total = profile["rental_count"]
                grouped[item["cluster_id"]].append({
                    "station_id": item["station_id"],
                    "x": round(sum(profile["hourly"][6:10]) / total, 4),
                    "y": round(sum(profile["hourly"][17:21]) / total, 4),
                    "cluster_id": item["cluster_id"], "role": item["role"]
                })
            representatives = []
            for label, members in grouped.items():
                selected = [profiles[x["station_id"]] for x in members]
                total = sum(p["rental_count"] for p in selected)
                representatives.append({"label":"군집 " + str(label+1),
                    "hourly":[sum(p["hourly"][h] for p in selected)/max(1,total)*100 for h in range(24)]})
            points = []
            for label, rows in grouped.items():
                stride = max(1, len(rows) // 30)
                points.extend(rows[::stride][:30])
            usage_rows = real_data.snapshot()["usage"]
            seoul_dates = {row["date"] for row in usage_rows if row["region_id"] == "seoul"
                           and row["rental_count"] > 0}
            daejeon_dates = {row["date"] for row in usage_rows if row["region_id"] == "daejeon"
                             and row["rental_count"] > 0}
            common_dates = sorted(seoul_dates & daejeon_dates)
            comparison = []
            for rid, name in (("seoul", "서울"), ("daejeon", "대전")):
                total = sum(row["rental_count"] for row in usage_rows
                            if row["region_id"] == rid and row["date"] in common_dates)
                comparison.append({"region_id": rid, "name": name,
                    "total_rentals": total if common_dates else None,
                    "observed_dates": common_dates})
            result = {"heatmap": heatmap, "cluster_points": points,
                      "cluster_count": len(result_clusters["clusters"]),
                      "selected_k": result_clusters.get("selected_k"),
                      "comparison": comparison, "comparison_dates": common_dates,
                      "silhouette": max((x["silhouette"] for x in result_clusters.get("diagnostics", [])), default=None),
                      "quality": result_clusters.get("quality"),
                      "cluster_representatives": representatives}
        elif action == "research":
            result = real_data.role_candidates(region_id, date_start, date_end)
        elif action == "compare_clusters":
            observed = [real_data.observed_dates(rid) for rid in ("seoul", "daejeon")]
            if all(observed):
                start, end = date_start, date_end
                result = {"regions": [
                    {"region_id": rid, "region_name": name,
                     "clusters": real_data.clusters(rid, start, end).get("cluster_summaries", []),
                     "period_start": start, "period_end": end}
                    for rid, name in (("seoul", "서울"), ("daejeon", "대전"))] if start <= end else []}
            else:
                result = {"regions": []}
        elif action == "cluster_stability":
            result = real_data.cluster_stability(region_id, date_end, date_start) if not unified else {
                "regions": [{**real_data.cluster_stability(rid, date_end, date_start), "region_id": rid, "region_name": name}
                            for rid,name in (("seoul","서울"),("daejeon","대전"))]}
        elif action == "station_validation":
            result = real_data.hidden_hub_validation(region_id, station_id, date_end, date_start)
        elif action == "station_history":
            result = real_data.station_role_history(region_id, station_id, date_end, date_start)
        elif action == "stations":
            items = real_data.region_stations(region_id, date_start, date_end)
            if query:
                items = [item for item in items if query.lower() in
                         (item["station_id"] + " " + (item.get("station_name") or "")).lower()]
            items.sort(key=lambda item: item.get("rental_count") or 0, reverse=True)
            result = {"stations": items[:50], "total": len(items),
                      "message": "상위 50개만 표시합니다. 검색하면 전체 대여소에서 찾습니다."}
        elif action == "station":
            item = next((item for item in real_data.region_stations(region_id, date_start, date_end)
                         if item["station_id"] == station_id), None)
            if item is None:
                return wiz.response.status(404, message="대여소를 찾을 수 없습니다.")
            cluster = next((row for row in real_data.clusters(region_id, date_start, date_end)["clusters"]
                            if row["station_id"] == station_id), None) if item.get("rental_count") else None
            item = {**item, "region_id": region_id, "region_name": next(r["region_name"] for r in real_data.REGIONS if r["region_id"] == region_id), "station_key": region_id + "::" + station_id}
            result = {"station": item, "cluster": cluster, "source": real_data.source_meta(region_id),
                      "similarity": real_data.similarity_result(region_id, station_id, date_start, date_end) if item.get("rental_count") else {"similar": []},
                      "profile": next((p for p in real_data.profiles(region_id, date_start, date_end) if p["station_id"] == station_id), None)}
            for row in result["similarity"].get("similar", []):
                row["region_id"] = region_id
                row["station_key"] = region_id + "::" + row["station_id"]
        elif action == "network":
            network = real_data.network(region_id, date_start, date_end)
            # The flow diagram shows trips between distinct stations.
            edges = [item for item in network["edges"]
                     if item["origin_station_id"] != item["destination_station_id"]][:20]
            node_ids = {value for edge in edges for value in
                        (edge["origin_station_id"], edge["destination_station_id"])}
            result = {**network, "edges": edges,
                      "display_note": "동일 대여소 출발·도착 기록은 연결 도식에서 제외했습니다.",
                      "nodes": [item for item in network["nodes"] if item["station_id"] in node_ids]}
        elif action == "centrality":
            result = real_data.centrality_result(region_id, date_start, date_end)
            result["rankings"] = result["rankings"][:15]
        elif action == "compare":
            items = []
            for region in real_data.REGIONS:
                overview = real_data.overview(region["region_id"], date_start, date_end)
                overview.pop("map_stations", None)
                items.append(overview)
            dated = [x for x in items if x.get("period_start")]
            start = date_start
            end = date_end
            common = [real_data.overview(x["region_id"], start, end) for x in dated] if start and end and start <= end else []
            for x in common: x.pop("map_stations", None)
            result = {"regions": items, "common": common,
                      "common_start": start if common else None, "common_end": end if common else None,
                      "annual": real_data.snapshot()["yearly"]}
        elif action == "chat":
            message = str(wiz.request.query("message", "")).strip()
            if not 1 <= len(message) <= 2000:
                return wiz.response.status(400, message="질문은 1~2000자로 입력하세요.")
            result = chat(message, context=context)
            result["evidence"] = result.get("evidence", [])[:10]
        else:
            return wiz.response.status(400, message="지원하지 않는 작업입니다.")
    except HTTPException as error:
        if isinstance(error.detail, dict):
            return wiz.response.status(error.status_code, error.detail, message=error.detail.get("message", "Solar 요청 실패"))
        return wiz.response.status(error.status_code, message=str(error.detail))
    except Exception as error:
        if type(error).__name__ == "ResponseException":
            raise
        return wiz.response.status(500, message=f"Bike Link 데이터 요청 실패: {type(error).__name__}")
    return wiz.response.status(200, result)
