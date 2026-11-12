"""Unified view of active cities; no invented inter-city journeys."""
from collections import Counter
from pathlib import Path
from backend.services import real_data as data
from backend.services.result_cache import data_cached
from backend.analysis.network import centrality

REGIONS = ("seoul", "daejeon", "sejong")
NAMES = {"seoul": "서울", "daejeon": "대전", "sejong": "세종"}

def scope(date_start=None, date_end=None):
    ranges = [data.observed_dates(rid) for rid in REGIONS]
    ranges = [days for days in ranges if days]
    if not ranges:
        return None, None
    start, end = max(x[0] for x in ranges), min(x[-1] for x in ranges)
    start, end = max(start, date_start or start), min(end, date_end or end)
    return (start, end) if start <= end else (None, None)

def get(action, date_start=None, date_end=None):
    return projection(action, Path(__file__).stat().st_mtime_ns, date_start, date_end)

def meta():
    sources = [s for rid in REGIONS for s in data.source_meta(rid)["sources"]]
    return {"sources": sources, "source_names": sorted({s["dataset_name"] for s in sources}),
            "verification_status": "VERIFIED", "region_id": "all", "region_name": "전체",
            "last_updated": max((s["collected_at"] for s in sources if s.get("collected_at")), default=None)}

def station_rows(date_start=None, date_end=None):
    start, end = scope(date_start, date_end)
    if not start: return []
    return [{**row, "station_key": rid + "::" + row["station_id"],
             "region_id": rid, "region_name": NAMES[rid]}
            for rid in REGIONS for row in data.region_stations(rid, start, end)]

def graph_data(date_start=None, date_end=None):
    start, end = scope(date_start, date_end)
    stations, records = [], []
    if not start: return stations, records
    for rid in REGIONS:
        od = data.aggregated_od(rid, start, end)
        ids = {sid for row in od for sid in (row["origin_station_id"], row["destination_station_id"])}
        inventory = [s for s in data.snapshot()["stations"] if s["region_id"] == rid and s["station_id"] in ids
                     and (rid != "seoul" or (s["latitude"] is not None and s["longitude"] is not None))]
        valid = {s["station_id"] for s in inventory}
        stations.extend({**s, "original_station_id": s["station_id"], "station_id": rid + "::" + s["station_id"],
                         "station_name": NAMES[rid] + " · " + (s.get("station_name") or s["station_id"])}
                        for s in inventory)
        records.extend({**r, "origin_station_id": rid + "::" + r["origin_station_id"],
                        "destination_station_id": rid + "::" + r["destination_station_id"]}
                       for r in od if r["origin_station_id"] in valid and r["destination_station_id"] in valid)
    return stations, records

@data_cached
def projection(action, source_revision, date_start=None, date_end=None):
    start, end = scope(date_start, date_end)
    common = [data.overview(rid, start, end) for rid in REGIONS] if start else []
    base = {**meta(), "period_start": start, "period_end": end}
    if action == "overview":
        measured = [x for x in common if x["total_rentals"] is not None]
        daily = Counter()
        for item in measured:
            for row in item["daily"]: daily[row["date"]] += row["rental_count"]
        maps = []
        for item in common:
            inventory = item["map_stations"]
            stride = max(1, len(inventory) // 60)
            maps.extend([{**r, "region_name": NAMES[item["region_id"]]} for r in inventory[::stride][:60]])
        return {**base, "total_rentals": sum(x["total_rentals"] for x in measured) if measured else None,
                "station_count": sum(x["station_count"] or 0 for x in measured) if measured else None,
                "observed_dates": sorted(daily), "daily": [{"date": d, "rental_count": n} for d, n in sorted(daily.items())],
                "hourly": [sum(x["hourly"][h] for x in measured if x["hourly"]) for h in range(24)] if measured else None,
                "map_stations": maps, "annual_latest": None,
                "annual_separate": [{**x["annual_latest"], "region_name": x["region_name"]} for x in
                    (common if common else [data.overview("sejong")]) if x["annual_latest"]],
                "city_count": len(REGIONS), "measured_city_count": len(measured),
                "coverage_note": "서울·대전 공통 관측 기간의 이용 기록을 합산합니다. 서울은 집계 OD, 대전은 개별 Trip입니다. 세종 연간 통계는 합계에서 제외하고 별도로 표시합니다."}
    if action == "centrality":
        stations, records = graph_data(start, end)
        result = centrality(stations, records)
        for row in result["rankings"]:
            rid, sid = row["station_id"].split("::", 1)
            row.update(region_id=rid, original_station_id=sid, region_name=NAMES[rid])
        return {**base, **result, "rankings": result["rankings"][:100],
                "message": "통합 그래프의 중심성입니다. 도시 간 이동 간선은 없고 도시별 연결 성분만 존재합니다."}
    if action == "network":
        stations, records = graph_data()
        ranking = get("centrality", start, end).get("rankings", [])
        selected = {r["station_id"] for r in ranking[:40]}
        edges = [r for r in records if r["origin_station_id"] in selected and r["destination_station_id"] in selected
                 and r["origin_station_id"] != r["destination_station_id"]]
        edges.sort(key=lambda r: r["trip_count"], reverse=True)
        edges = edges[:20]
        visible = {sid for r in edges for sid in (r["origin_station_id"],r["destination_station_id"])}
        return {**base, "available": bool(records), "nodes": [s for s in stations if s["station_id"] in visible],
                "edges": edges, "edge_count": len(records), "visible_edge_count": len(edges),
                "message": "공통 기간의 서울·대전 OD를 하나로 표시합니다. 도시 간 이동을 생성하지 않았습니다."}
    if action == "research":
        results = [data.role_candidates(rid, start, end) for rid in REGIONS] if start else []
        types, counts = {}, Counter()
        for rid, result in zip(REGIONS, results):
            for key, rows in result.get("types", {}).items():
                types.setdefault(key, []).extend({**r, "region_id": rid, "region_name": NAMES[rid]} for r in rows)
            counts.update(result.get("counts", {}))
        return {**base, "available": any(r.get("available") for r in results), "types": types, "counts": dict(counts),
                "message": "후보는 공통 기간에 도시별 경험 분포로 판정한 뒤 합친 목록입니다. 통합 임계값으로 재판정한 결과가 아닙니다."}
    if action == "dashboard_extra":
        points, k_total, station_total = [], 0, 0
        representatives = []
        for rid in REGIONS if start else []:
            result = data.clusters(rid, start, end)
            profiles = {p["station_id"]: p for p in data.profiles(rid, start, end)}
            grouped = {}
            for cluster in result.get("clusters", []):
                p = profiles.get(cluster["station_id"])
                if not p or not p["rental_count"] or not p["hourly"]: continue
                label = cluster["cluster_id"]
                grouped.setdefault(label, []).append({"station_id": p["station_id"], "region_id": rid,
                    "x": sum(p["hourly"][6:10])/p["rental_count"], "y": sum(p["hourly"][17:21])/p["rental_count"],
                    "cluster_id": k_total + label})
            for label, rows in grouped.items():
                points.extend(rows[::max(1,len(rows)//30)][:30])
                members = [profiles[x["station_id"]] for x in rows]
                total = sum(p["rental_count"] for p in members)
                representatives.append({"label":NAMES[rid] + " 군집 " + str(label+1),
                    "hourly":[sum(p["hourly"][h] for p in members)/max(1,total)*100 for h in range(24)]})
            k_total += result.get("selected_k") or 0
            station_total += len(result.get("clusters", []))
        by_day = {}
        if start and data.database_enabled():
            import sqlite3
            with sqlite3.connect(data.database_path()) as conn:
                rows = conn.execute("SELECT date,hour,SUM(rental_count) FROM station_usage WHERE region_id IN ('seoul','daejeon','sejong') AND date>=? AND date<=? AND hour IS NOT NULL GROUP BY date,hour", (start,end)).fetchall()
            for day, hour, count in rows:
                by_day.setdefault(day,[0]*24)[int(hour)] = int(count)
        elif start:
            for row in data.filtered(data.snapshot()["usage"], date_start=start, date_end=end):
                if row["region_id"] in REGIONS and row["hour"] is not None:
                    by_day.setdefault(row["date"],[0]*24)[row["hour"]] += row["rental_count"]
        return {**base, "cluster_points": points, "selected_k": k_total or None, "cluster_count": station_total,
                "cluster_representatives": representatives, "silhouette": None, "cluster_scope": "도시별 K-means 분포 통합 표시 · 통합 재학습 아님",
                "heatmap": [{"date": d, "hours": h} for d,h in sorted(by_day.items())]}
    raise ValueError("Unsupported unified projection")
