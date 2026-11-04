"""Read normalized public data. Missing measures are null, never synthetic zero."""
import csv
import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from backend.analysis.clustering import cluster_stations
from backend.analysis.network import centrality
from backend.analysis.similarity import station_similarity

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
REGIONS = [
    {"region_id": "seoul", "region_name": "서울", "service_name": "따릉이", "operator": "서울특별시"},
    {"region_id": "daejeon", "region_name": "대전", "service_name": "타슈", "operator": "대전광역시"},
    {"region_id": "sejong", "region_name": "세종", "service_name": "어울링", "operator": "세종도시교통공사"},
    {"region_id": "busan", "region_name": "부산", "service_name": "지역별 대여소", "operator": "부산광역시·구군·시설관리기관"},
]


def read_csv(name):
    path = PROCESSED / name
    paths = ([path] if path.exists() else []) + sorted((PROCESSED / "uploads").glob("*-" + name))
    rows = []
    for current in paths:
        with current.open(encoding="utf-8", newline="") as stream:
            rows.extend(csv.DictReader(stream))
    return rows


def read_json(name, default):
    path = PROCESSED / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


@lru_cache(maxsize=1)
def snapshot():
    stations = read_csv("stations.csv")
    for s in stations:
        s["latitude"] = float(s["latitude"]) if s["latitude"] else None
        s["longitude"] = float(s["longitude"]) if s["longitude"] else None
        s["capacity"] = int(s["capacity"]) if s["capacity"] else None
    usage = read_csv("station_usage.csv")
    for row in usage:
        row["hour"] = int(row["hour"]) if row["hour"] else None
        row["rental_count"] = int(row["rental_count"])
        row["return_count"] = int(row["return_count"]) if row["return_count"] else None
    od = read_csv("od_daily.csv")
    for row in od:
        row["trip_count"] = int(row["trip_count"])
    yearly = read_csv("yearly.csv")
    for row in yearly:
        row["year"] = int(row["year"])
        row["rental_count"] = int(row["rental_count"])
        row["complete_year"] = row["complete_year"].lower() == "true"
    quality = read_json("quality.json", {})
    for region, uploaded in read_json("uploads/quality.json", {}).items():
        quality.setdefault(region, {})["uploads"] = uploaded
    return {"stations": stations, "usage": usage, "od": od, "yearly": yearly,
            "sources": read_json("sources.json", []) + read_json("uploads/sources.json", []),
            "quality": quality}


def filtered(rows, region_id=None, date_start=None, date_end=None):
    return [row for row in rows if (region_id is None or row["region_id"] == region_id)
            and (date_start is None or row["date"] >= date_start)
            and (date_end is None or row["date"] <= date_end)]


def source_meta(region_id):
    selected = [s for s in snapshot()["sources"] if s["region_id"] == region_id]
    verified = [s for s in selected if s["verification_status"] == "VERIFIED"]
    collected = [s["collected_at"] for s in verified if s.get("collected_at")]
    return {"sources": selected, "source_names": sorted({s["dataset_name"] for s in verified}),
            "last_updated": max(collected) if collected else None,
            "verification_status": "VERIFIED" if verified else ("METADATA_ONLY" if selected else "UNAVAILABLE")}


def region_stations(region_id, date_start=None, date_end=None):
    s = [row for row in snapshot()["stations"] if row["region_id"] == region_id]
    if region_id == "seoul" and any(x["source_id"] == "seoul-station-master-oa-21235" for x in snapshot()["sources"]):
        s = [row for row in s if row["station_id"].startswith("ST-")]
    profile = profiles(region_id, date_start, date_end)
    by_id = {p["station_id"]: p for p in profile}
    return [{**station, "rental_count": by_id.get(station["station_id"], {}).get("rental_count"),
             "return_count": by_id.get(station["station_id"], {}).get("return_count"),
             "hourly": by_id.get(station["station_id"], {}).get("hourly"),
             "weekend_share": by_id.get(station["station_id"], {}).get("weekend_share")}
            for station in s]


def observed_dates(region_id, date_start=None, date_end=None):
    return sorted({row["date"] for row in filtered(snapshot()["usage"], region_id, date_start, date_end)
                   if row["rental_count"] > 0})


def profiles(region_id, date_start=None, date_end=None):
    rows = filtered(snapshot()["usage"], region_id, date_start, date_end)
    stations = {s["station_id"]: s for s in snapshot()["stations"] if s["region_id"] == region_id}
    by_id = {}
    for row in rows:
        sid = row["station_id"]
        item = by_id.setdefault(sid, {"station_id": sid, "station_name": stations.get(sid, {}).get("station_name"),
            "region_id": region_id, "hourly": [0] * 24, "rental_count": 0,
            "return_count": 0, "has_return": False, "weekend_count": 0, "has_hourly": True})
        count = row["rental_count"]
        item["rental_count"] += count
        item["return_count"] += row["return_count"] or 0
        item["has_return"] = item["has_return"] or row["return_count"] is not None
        if row["hour"] is None:
            item["has_hourly"] = False
        else:
            item["hourly"][row["hour"]] += count
        if __import__("datetime").date.fromisoformat(row["date"]).weekday() >= 5:
            item["weekend_count"] += count
    observed = {row["date"] for row in rows}
    mixed_days = any(__import__("datetime").date.fromisoformat(d).weekday() >= 5 for d in observed) and any(__import__("datetime").date.fromisoformat(d).weekday() < 5 for d in observed)
    for item in by_id.values():
        item["weekend_share"] = item["weekend_count"] / item["rental_count"] if mixed_days and item["rental_count"] else None
        if not item["has_hourly"]:
            item["hourly"] = None
        if not item["has_return"]:
            item["return_count"] = None
    return list(by_id.values())


def overview(region_id, date_start=None, date_end=None):
    region = next(r for r in REGIONS if r["region_id"] == region_id)
    meta = source_meta(region_id)
    rows = filtered(snapshot()["usage"], region_id, date_start, date_end)
    days = sorted({r["date"] for r in rows if r["rental_count"] > 0})
    daily = [{"date": day, "rental_count": sum(r["rental_count"] for r in rows if r["date"] == day)}
             for day in days]
    hourly = [sum(r["rental_count"] for r in rows if r["hour"] == h) for h in range(24)] if rows and all(r["hour"] is not None for r in rows) else None
    total = sum(r["rental_count"] for r in rows) if rows else None
    station_ids = {r["station_id"] for r in rows if r["rental_count"] > 0}
    inventory = [s for s in snapshot()["stations"] if s["region_id"] == region_id and s["latitude"] is not None
                 and (region_id != "seoul" or s["station_id"].startswith("ST-"))]
    # Sejong's annual totals are a separate population and period; never mix them with station usage.
    annual = [r for r in snapshot()["yearly"] if r["region_id"] == region_id and r["complete_year"]]
    annual_latest = max(annual, key=lambda r: r["year"]) if annual else None
    weekend = sum(r["rental_count"] for r in rows if __import__("datetime").date.fromisoformat(r["date"]).weekday() >= 5)
    weekdays = {r["date"] for r in rows if __import__("datetime").date.fromisoformat(r["date"]).weekday() < 5}
    weekends = {r["date"] for r in rows if __import__("datetime").date.fromisoformat(r["date"]).weekday() >= 5}
    weekend_share = round(weekend / total, 4) if total and weekdays and weekends else None
    return {**region, **meta, "total_rentals": total, "station_count": len(station_ids) if rows else
            (len([s for s in snapshot()["stations"] if s["region_id"] == region_id]) or None),
            "inventory_station_count": len(inventory) or None,
            "average_per_station": round(total / len(station_ids), 2) if total is not None and station_ids else None,
            "hourly": hourly, "period_start": days[0] if days else None, "period_end": days[-1] if days else None,
            "observed_dates": days, "daily": daily, "weekend_share": weekend_share,
            "weekday_share": round(1 - weekend_share, 4) if weekend_share is not None else None,
            "map_stations": inventory, "annual_latest": annual_latest,
            "has_od": bool(filtered(snapshot()["od"], region_id, date_start, date_end)),
            "coverage_note": "서울은 불연속 2일의 집계 OD입니다. 공식 대여소 마스터의 ST ID와 유효 좌표를 확인한 항목만 지도에 연결했으며 X는 미매칭입니다." if region_id == "seoul" else
            ("대전 Trip 원본에서 서울과 공통인 2일만 분석합니다. 관리 반납 기록은 제외했습니다." if region_id == "daejeon" and rows else
             "대여소 위치 목록만 확보해 이용량·좌표가 없습니다." if region_id == "daejeon" else
             "운영기관별 자료 범위가 달라 통합 지표가 없습니다." if region_id == "busan" else
             "연도별 총 이용량만 확보해 대여소·시간대 자료가 없습니다.")}


@lru_cache(maxsize=32)
def clusters(region_id, date_start=None, date_end=None):
    result = cluster_stations(profiles(region_id, date_start, date_end))
    return {**source_meta(region_id), **result, "period_start": date_start, "period_end": date_end}


@lru_cache(maxsize=64)
def network(region_id, date_start=None, date_end=None, node_limit=40):
    records = filtered(snapshot()["od"], region_id, date_start, date_end)
    if not records:
        return {**source_meta(region_id), "available": False, "nodes": [], "edges": [],
                "edge_count": 0, "visible_edge_count": 0, "message": "이동 경로 데이터 미확보"}
    merged = Counter()
    for row in records:
        merged[(row["origin_station_id"], row["destination_station_id"])] += row["trip_count"]
    ranking = centrality_result(region_id, date_start, date_end)["rankings"]
    top_ids = [item["station_id"] for item in ranking[:node_limit]]
    selected = set(top_ids)
    station_map = {s["station_id"]: s for s in snapshot()["stations"] if s["region_id"] == region_id}
    edges = [{"origin_station_id": origin, "destination_station_id": destination, "trip_count": count}
             for (origin, destination), count in merged.items()
             if origin in selected and destination in selected]
    edges.sort(key=lambda item: item["trip_count"], reverse=True)
    return {**source_meta(region_id), "available": True,
            "nodes": [station_map[sid] for sid in top_ids if sid in station_map],
            "edges": edges, "edge_count": len(merged), "visible_edge_count": len(edges),
            "node_selection_basis": "전체 OD 그래프의 PageRank 상위 대여소",
            "period_start": min(row["date"] for row in records),
            "period_end": max(row["date"] for row in records),
            "message": ("대전 개별 Trip에서 집계한 연결입니다." if region_id == "daejeon"
                        else "서울의 집계 OD 연결이며 개별 Trip 기록은 아닙니다.")}


@lru_cache(maxsize=32)
def centrality_result(region_id, date_start=None, date_end=None):
    records = filtered(snapshot()["od"], region_id, date_start, date_end)
    ids = {s for row in records for s in (row["origin_station_id"], row["destination_station_id"])}
    stations = [s for s in snapshot()["stations"] if s["region_id"] == region_id and s["station_id"] in ids
                and (region_id != "seoul" or (s["latitude"] is not None and s["longitude"] is not None))]
    result = centrality(stations, records)
    return {**source_meta(region_id), **result, "rankings": result["rankings"][:100]}


def similarity_result(region_id, station_id, date_start=None, date_end=None):
    result = station_similarity(profiles(region_id, date_start, date_end), station_id)
    return {**source_meta(region_id), "station_id": station_id, "similar": result,
            "available": bool(result), "message": "정규화한 시간대·주말 비중의 코사인 유사도. 절대 이용량은 별도 표시." if result else "비교할 이용 기록이 없습니다."}


def compare(region_ids, date_start=None, date_end=None):
    selected = region_ids or [r["region_id"] for r in REGIONS]
    items = [overview(rid, date_start, date_end) for rid in selected]
    dates = [set(x["observed_dates"]) for x in items if x["total_rentals"] is not None]
    same_dates = len(dates) >= 2 and all(d == dates[0] for d in dates)
    rows = []
    for item in items:
        top = centrality_result(item["region_id"], date_start, date_end)["rankings"][:1] if item["has_od"] else []
        rows.append({**{k: value for k, value in item.items() if k != "map_stations"}, "centrality_top": top[0] if top else None})
    return {"regions": rows,
            "same_observed_dates": same_dates,
            "limitations": ["모집단·수집 범위·운영방식이 다릅니다.", "OD 집계와 연간 총량을 직접 비교할 수 없습니다.",
                            "N/A는 결측 또는 비교 불가를 뜻합니다."]}
