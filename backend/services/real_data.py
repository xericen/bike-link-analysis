"""Read normalized public data. Missing measures are null, never synthetic zero."""
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from backend.analysis.clustering import adjusted_rand, cluster_stations
from backend.analysis.network import centrality
from backend.analysis.similarity import station_similarity

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
REGIONS = [
    {"region_id": "seoul", "region_name": "서울", "service_name": "따릉이", "operator": "서울특별시"},
    {"region_id": "daejeon", "region_name": "대전", "service_name": "타슈", "operator": "대전광역시"},
    {"region_id": "sejong", "region_name": "세종", "service_name": "어울링", "operator": "세종도시교통공사"},
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


def database_path():
    return PROCESSED / "analysis.sqlite"


def database_enabled():
    return database_path().exists()


def _where(region_id, date_start=None, date_end=None):
    clauses, values = ["region_id = ?"], [region_id]
    if date_start:
        clauses.append("date >= ?"); values.append(date_start)
    if date_end:
        clauses.append("date <= ?"); values.append(date_end)
    return " AND ".join(clauses), values


def has_observations(table, region_id, date_start=None, date_end=None):
    if not database_enabled():
        name = "station_usage.csv" if table == "station_usage" else "od_daily.csv"
        return bool(filtered(read_csv(name), region_id, date_start, date_end))
    where, values = _where(region_id, date_start, date_end)
    with sqlite3.connect(database_path()) as connection:
        return connection.execute(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", values).fetchone() is not None


def aggregated_od(region_id, date_start=None, date_end=None):
    if not database_enabled():
        merged = Counter()
        for row in filtered(snapshot()["od"], region_id, date_start, date_end):
            merged[(row["origin_station_id"], row["destination_station_id"])] += row["trip_count"]
        return [{"region_id": region_id, "origin_station_id": origin, "destination_station_id": destination,
                 "trip_count": count} for (origin, destination), count in merged.items()]
    where, values = _where(region_id, date_start, date_end)
    with sqlite3.connect(database_path()) as connection:
        rows = connection.execute(f"""SELECT origin_station_id, destination_station_id, SUM(trip_count)
            FROM od_daily WHERE {where} GROUP BY origin_station_id, destination_station_id""", values)
        return [{"region_id": region_id, "origin_station_id": origin, "destination_station_id": destination,
                 "trip_count": int(count)} for origin, destination, count in rows]


@lru_cache(maxsize=1)
def snapshot():
    stations = read_csv("stations.csv")
    for s in stations:
        s["latitude"] = float(s["latitude"]) if s["latitude"] else None
        s["longitude"] = float(s["longitude"]) if s["longitude"] else None
        s["capacity"] = int(s["capacity"]) if s["capacity"] else None
    usage = [] if database_enabled() else read_csv("station_usage.csv")
    for row in usage:
        row["hour"] = int(row["hour"]) if row["hour"] else None
        row["rental_count"] = int(row["rental_count"])
        row["return_count"] = int(row["return_count"]) if row["return_count"] else None
    od = [] if database_enabled() else read_csv("od_daily.csv")
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


def percentile(values, fraction):
    """Linear empirical percentile without adding a heavy dataframe dependency."""
    ordered = sorted(float(value) for value in values if value is not None)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


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
    flows = {row["station_id"]: row for row in imbalance_result(region_id, date_start, date_end)["stations"]}
    return [{**station, "rental_count": by_id.get(station["station_id"], {}).get("rental_count"),
             "return_count": by_id.get(station["station_id"], {}).get("return_count"),
             "hourly": by_id.get(station["station_id"], {}).get("hourly"),
             "weekend_share": by_id.get(station["station_id"], {}).get("weekend_share"),
             **{key: flows.get(station["station_id"], {}).get(key) for key in
                ("net_outflow", "imbalance_ratio", "hourly_net_outflow", "persistent_direction", "persistence_ratio")}}
            for station in s]


def observed_dates(region_id, date_start=None, date_end=None):
    if database_enabled():
        where, values = _where(region_id, date_start, date_end)
        with sqlite3.connect(database_path()) as connection:
            return [row[0] for row in connection.execute(
                f"SELECT DISTINCT date FROM station_usage WHERE {where} AND rental_count > 0 ORDER BY date", values)]
    return sorted({row["date"] for row in filtered(snapshot()["usage"], region_id, date_start, date_end)
                   if row["rental_count"] > 0})


def profiles(region_id, date_start=None, date_end=None):
    if database_enabled():
        where, values = _where(region_id, date_start, date_end)
        stations = {s["station_id"]: s for s in snapshot()["stations"] if s["region_id"] == region_id}
        with sqlite3.connect(database_path()) as connection:
            grouped = connection.execute(f"""SELECT station_id, hour, SUM(rental_count),
                SUM(return_count), COUNT(return_count),
                SUM(CASE WHEN CAST(strftime('%w', date) AS INTEGER) IN (0,6) THEN rental_count ELSE 0 END)
                FROM station_usage WHERE {where} GROUP BY station_id, hour""", values).fetchall()
            day_types = connection.execute(f"""SELECT
                COUNT(DISTINCT CASE WHEN CAST(strftime('%w', date) AS INTEGER) IN (0,6) THEN date END),
                COUNT(DISTINCT CASE WHEN CAST(strftime('%w', date) AS INTEGER) NOT IN (0,6) THEN date END)
                FROM station_usage WHERE {where}""", values).fetchone()
        by_id = {}
        for sid, hour, rentals, returns, return_rows, weekend in grouped:
            item = by_id.setdefault(sid, {"station_id": sid, "station_name": stations.get(sid, {}).get("station_name"),
                "region_id": region_id, "hourly": [0] * 24, "return_hourly": [0] * 24, "rental_count": 0,
                "return_count": 0, "has_return": False, "weekend_count": 0, "has_hourly": True})
            item["rental_count"] += int(rentals or 0)
            item["return_count"] += int(returns or 0)
            item["has_return"] = item["has_return"] or bool(return_rows)
            item["weekend_count"] += int(weekend or 0)
            if hour is None:
                item["has_hourly"] = False
            else:
                item["hourly"][int(hour)] += int(rentals or 0)
                item["return_hourly"][int(hour)] += int(returns or 0)
        mixed_days = bool(day_types and day_types[0] and day_types[1])
        for item in by_id.values():
            item["weekend_share"] = item["weekend_count"] / item["rental_count"] if mixed_days and item["rental_count"] else None
            if not item["has_hourly"]: item["hourly"] = None
            if not item["has_return"]: item["return_count"] = None
        return list(by_id.values())
    rows = filtered(snapshot()["usage"], region_id, date_start, date_end)
    stations = {s["station_id"]: s for s in snapshot()["stations"] if s["region_id"] == region_id}
    by_id = {}
    for row in rows:
        sid = row["station_id"]
        item = by_id.setdefault(sid, {"station_id": sid, "station_name": stations.get(sid, {}).get("station_name"),
            "region_id": region_id, "hourly": [0] * 24, "return_hourly": [0] * 24, "rental_count": 0,
            "return_count": 0, "has_return": False, "weekend_count": 0, "has_hourly": True})
        count = row["rental_count"]
        item["rental_count"] += count
        item["return_count"] += row["return_count"] or 0
        item["has_return"] = item["has_return"] or row["return_count"] is not None
        if row["hour"] is None:
            item["has_hourly"] = False
        else:
            item["hourly"][row["hour"]] += count
            item["return_hourly"][row["hour"]] += row["return_count"] or 0
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
    if database_enabled():
        where, values = _where(region_id, date_start, date_end)
        with sqlite3.connect(database_path()) as connection:
            daily_rows = connection.execute(f"SELECT date, SUM(rental_count) FROM station_usage WHERE {where} GROUP BY date HAVING SUM(rental_count) > 0 ORDER BY date", values).fetchall()
            hourly_rows = connection.execute(f"SELECT hour, SUM(rental_count) FROM station_usage WHERE {where} GROUP BY hour", values).fetchall()
            station_count = connection.execute(f"SELECT COUNT(DISTINCT station_id) FROM station_usage WHERE {where} AND rental_count > 0", values).fetchone()[0]
        daily = [{"date": day, "rental_count": int(count)} for day, count in daily_rows if count > 0]
        days = [row["date"] for row in daily]
        rows = [{"date": day, "hour": None, "rental_count": count} for day, count in daily_rows]
        hourly = [0] * 24 if hourly_rows and all(hour is not None for hour, _ in hourly_rows) else None
        if hourly is not None:
            for hour, count in hourly_rows: hourly[int(hour)] = int(count)
    else:
        rows = filtered(snapshot()["usage"], region_id, date_start, date_end)
        days = sorted({r["date"] for r in rows if r["rental_count"] > 0})
        daily = [{"date": day, "rental_count": sum(r["rental_count"] for r in rows if r["date"] == day)} for day in days]
        hourly = [sum(r["rental_count"] for r in rows if r["hour"] == h) for h in range(24)] if rows and all(r["hour"] is not None for r in rows) else None
        station_count = len({r["station_id"] for r in rows if r["rental_count"] > 0})
    monthly_counts = Counter()
    weekday_counts = Counter()
    for row in rows:
        monthly_counts[row["date"][:7]] += row["rental_count"]
        weekday_counts[__import__("datetime").date.fromisoformat(row["date"]).weekday()] += row["rental_count"]
    monthly = [{"month": month, "rental_count": count} for month, count in sorted(monthly_counts.items())]
    weekday = [{"weekday": index, "rental_count": weekday_counts.get(index, 0)} for index in range(7)] if rows else None
    total = sum(r["rental_count"] for r in rows) if rows else None
    inventory = [s for s in snapshot()["stations"] if s["region_id"] == region_id and s["latitude"] is not None
                 and (region_id != "seoul" or s["station_id"].startswith("ST-"))]
    # Sejong's annual totals are a separate population and period; never mix them with station usage.
    annual = [r for r in snapshot()["yearly"] if r["region_id"] == region_id and r["complete_year"]]
    annual_latest = max(annual, key=lambda r: r["year"]) if annual else None
    weekend = sum(r["rental_count"] for r in rows if __import__("datetime").date.fromisoformat(r["date"]).weekday() >= 5)
    weekdays = {r["date"] for r in rows if __import__("datetime").date.fromisoformat(r["date"]).weekday() < 5}
    weekends = {r["date"] for r in rows if __import__("datetime").date.fromisoformat(r["date"]).weekday() >= 5}
    weekend_share = round(weekend / total, 4) if total and weekdays and weekends else None
    return {**region, **meta, "total_rentals": total, "station_count": station_count if rows else
            (len([s for s in snapshot()["stations"] if s["region_id"] == region_id]) or None),
            "inventory_station_count": len(inventory) or None,
            "average_per_station": round(total / station_count, 2) if total is not None and station_count else None,
            "hourly": hourly, "period_start": days[0] if days else None, "period_end": days[-1] if days else None,
            "observed_dates": days, "daily": daily, "monthly": monthly, "weekday": weekday,
            "weekend_share": weekend_share,
            "weekday_share": round(1 - weekend_share, 4) if weekend_share is not None else None,
            "map_stations": inventory, "annual_latest": annual_latest,
            "has_od": has_observations("od_daily", region_id, date_start, date_end),
            "coverage_note": "서울은 2026년 10월 집계 OD입니다. 공식 대여소 마스터의 ST ID와 유효 좌표를 확인한 항목만 지도에 연결합니다." if region_id == "seoul" else
            ("대전 월별 Trip 원본 전체 유효 기간을 분석하며 관리 목적 반납과 검증 실패 행은 제외했습니다." if region_id == "daejeon" and rows else
             "대여소 위치 목록만 확보해 이용량·좌표가 없습니다." if region_id == "daejeon" else
             "연도별 총 이용량만 확보해 대여소·시간대 자료가 없습니다.")}


@lru_cache(maxsize=32)
def clusters(region_id, date_start=None, date_end=None):
    result = cluster_stations(profiles(region_id, date_start, date_end))
    days = observed_dates(region_id, date_start, date_end)
    warning = None if len(days) >= 7 else "관측일이 7일 미만이므로 군집 안정성 해석에 주의하세요."
    if warning and result.get("available"):
        result["message"] += " " + warning
    return {**source_meta(region_id), **result, "period_start": days[0] if days else date_start,
            "period_end": days[-1] if days else date_end, "observed_day_count": len(days),
            "confidence_warning": warning}


@lru_cache(maxsize=16)
def cluster_stability(region_id, date_end=None):
    dates = observed_dates(region_id, None, date_end)
    if not dates:
        return {**source_meta(region_id), "available": False, "windows": [], "comparisons": [],
                "message": "군집 안정성을 계산할 이용 기록이 없습니다."}
    end = date.fromisoformat(dates[-1])
    windows = []
    for size in (7, 14, 30):
        start = (end - timedelta(days=size - 1)).isoformat()
        result = clusters(region_id, start, end.isoformat())
        best_silhouette = max((x["silhouette"] for x in result.get("diagnostics", [])), default=None)
        warnings = []
        if result["observed_day_count"] < size:
            warnings.append(f"요청한 {size}일 중 {result['observed_day_count']}일만 관측되었습니다.")
        if best_silhouette is not None and best_silhouette < 0.1:
            warnings.append("최고 Silhouette가 0.1 미만이라 군집 분리가 약합니다.")
        windows.append({"days": size, "date_start": start, "date_end": end.isoformat(),
            "observed_day_count": result["observed_day_count"], "available": result["available"],
            "selected_k": result.get("selected_k"), "diagnostics": result.get("diagnostics", []),
            "feature_comparisons": result.get("feature_comparisons", []),
            "quality": result.get("quality"), "interpretation_allowed": result.get("interpretation_allowed"),
            "cluster_summaries": result.get("cluster_summaries", []), "clusters": result.get("clusters", []),
            "confidence_warning": " ".join(warnings) or None})
    comparisons = []
    for left, right in zip(windows, windows[1:]):
        score = adjusted_rand(left["clusters"], right["clusters"])
        comparisons.append({"left_days": left["days"], "right_days": right["days"], **score})
    compact = [{k: v for k, v in window.items() if k != "clusters"} for window in windows]
    return {**source_meta(region_id), "available": any(x["available"] for x in windows),
            "period_end": end.isoformat(), "windows": compact, "comparisons": comparisons,
            "message": "ARI는 두 기간에 모두 존재하는 대여소만 비교하며 1에 가까울수록 군집 배정이 안정적입니다."}


def _daily_station_flows(region_id, date_start=None, date_end=None):
    if database_enabled():
        where, values = _where(region_id, date_start, date_end)
        with sqlite3.connect(database_path()) as connection:
            rows = connection.execute(f"""SELECT station_id, date, SUM(rental_count), SUM(return_count)
                FROM station_usage WHERE {where} GROUP BY station_id, date""", values)
            return [(sid, day, int(rentals or 0), int(returns or 0)) for sid, day, rentals, returns in rows]
    merged = defaultdict(lambda: [0, 0])
    for row in filtered(snapshot()["usage"], region_id, date_start, date_end):
        merged[(row["station_id"], row["date"])][0] += row["rental_count"]
        merged[(row["station_id"], row["date"])][1] += row["return_count"] or 0
    return [(sid, day, values[0], values[1]) for (sid, day), values in merged.items()]


@lru_cache(maxsize=32)
def imbalance_result(region_id, date_start=None, date_end=None):
    station_names = {s["station_id"]: s.get("station_name") for s in snapshot()["stations"] if s["region_id"] == region_id}
    daily = defaultdict(list)
    for sid, day, rentals, returns in _daily_station_flows(region_id, date_start, date_end):
        daily[sid].append({"date": day, "rental_count": rentals, "return_count": returns,
                           "net_outflow": rentals - returns})
    results = []
    for profile in profiles(region_id, date_start, date_end):
        rentals, returns = profile["rental_count"], profile["return_count"]
        if returns is None:
            continue
        net = rentals - returns
        total = rentals + returns
        daily_rows = sorted(daily.get(profile["station_id"], []), key=lambda row: row["date"])
        values = [row["net_outflow"] for row in daily_rows]
        positive = sum(value > 0 for value in values)
        negative = sum(value < 0 for value in values)
        dominant = max(positive, negative)
        weekday_rows = [row for row in daily_rows if date.fromisoformat(row["date"]).weekday() < 5]
        weekend_rows = [row for row in daily_rows if date.fromisoformat(row["date"]).weekday() >= 5]
        def day_type(rows):
            day_rentals = sum(row["rental_count"] for row in rows)
            day_returns = sum(row["return_count"] for row in rows)
            denominator = day_rentals + day_returns
            return {"observed_days": len(rows), "rental_count": day_rentals, "return_count": day_returns,
                    "net_outflow": day_rentals - day_returns,
                    "imbalance_ratio": round((day_rentals - day_returns) / denominator, 4) if denominator else None}
        results.append({"station_id": profile["station_id"], "station_name": station_names.get(profile["station_id"]),
            "rental_count": rentals, "return_count": returns, "net_outflow": net,
            "imbalance_ratio": round(net / total, 4) if total else None,
            "hourly_net_outflow": [r - v for r, v in zip(profile["hourly"] or [0] * 24, profile["return_hourly"] or [0] * 24)],
            "daily_net_outflow": daily_rows, "weekday": day_type(weekday_rows), "weekend": day_type(weekend_rows),
            "nonzero_imbalance_days": positive + negative,
            "persistent_direction": "net_outflow" if positive > negative else ("net_inflow" if negative > positive else "mixed"),
            "persistence_ratio": round(dominant / len(values), 4) if values else None})
    named = [row for row in results if row.get("station_name")]
    volume_floor = percentile((row["rental_count"] + row["return_count"] for row in named), 0.25)
    eligible = [row for row in named if row["rental_count"] + row["return_count"] >= (volume_floor or 0)]
    ratio_threshold = percentile((abs(row["imbalance_ratio"] or 0) for row in eligible), 0.9)
    persistence_threshold = percentile((row["persistence_ratio"] for row in eligible), 0.75)
    for row in results:
        row["low_volume_warning"] = row["rental_count"] + row["return_count"] < (volume_floor or 0)
        row["imbalance_candidate"] = bool(row.get("station_name") and row["rental_count"] + row["return_count"] >= (volume_floor or 0)
            and abs(row["imbalance_ratio"] or 0) >= (ratio_threshold or 0)
            and (row["persistence_ratio"] or 0) >= (persistence_threshold or 0))
    results.sort(key=lambda row: (abs(row["net_outflow"]), abs(row["imbalance_ratio"] or 0)), reverse=True)
    return {**source_meta(region_id), "available": bool(results), "stations": results,
            "period_start": date_start or (observed_dates(region_id, date_start, date_end) or [None])[0],
            "period_end": date_end or (observed_dates(region_id, date_start, date_end) or [None])[-1],
            "selection_rule": {"minimum_total_volume": round(volume_floor or 0, 2),
                "absolute_ratio_min": round(ratio_threshold or 0, 4),
                "persistence_min": round(persistence_threshold or 0, 4),
                "basis": "총량 하위 25% 제외 후 절대 불균형 비율 상위 10%와 지속성 상위 25% 동시 충족"},
            "definition": "순유출 = 대여 - 반납. 양수는 순유출, 음수는 순유입입니다.",
            "message": "후보 임계값은 선택 기간의 실제 분포에서 계산합니다. 지속성은 0을 포함한 관측일 중 우세 방향의 비율입니다. 실제 재고가 없어 자전거 부족·재배치 필요를 확정하지 않습니다."}


@lru_cache(maxsize=32)
def hidden_hubs(region_id, date_start=None, date_end=None, include_betweenness=True):
    records = aggregated_od(region_id, date_start, date_end)
    ids = {sid for row in records for sid in (row["origin_station_id"], row["destination_station_id"])}
    stations = [s for s in snapshot()["stations"] if s["region_id"] == region_id and s["station_id"] in ids
                and (region_id != "seoul" or (s["latitude"] is not None and s["longitude"] is not None))]
    full = centrality(stations, records, include_betweenness=include_betweenness)
    if not full.get("available"):
        return {**source_meta(region_id), **full, "candidates": []}
    usage = sorted(profiles(region_id, date_start, date_end), key=lambda row: row["rental_count"], reverse=True)
    usage_rank = {row["station_id"]: index for index, row in enumerate(usage, 1)}
    usage_count = {row["station_id"]: row["rental_count"] for row in usage}
    pagerank_rank = {row["station_id"]: index for index, row in enumerate(full["rankings"], 1)}
    betweenness_sorted = sorted(full["rankings"], key=lambda row: row["betweenness"], reverse=True)
    betweenness_rank = {row["station_id"]: index for index, row in enumerate(betweenness_sorted, 1)}
    connections = defaultdict(list)
    for row in records:
        if row["origin_station_id"] == row["destination_station_id"]:
            continue
        connections[row["origin_station_id"]].append((row["destination_station_id"], row["trip_count"], "out"))
        connections[row["destination_station_id"]].append((row["origin_station_id"], row["trip_count"], "in"))
    candidates = []
    for row in full["rankings"]:
        sid = row["station_id"]
        if sid not in usage_rank:
            continue
        rank_gap = usage_rank[sid] - pagerank_rank[sid]
        candidates.append({**row, "rental_count": usage_count[sid], "usage_rank": usage_rank[sid],
            "pagerank_rank": pagerank_rank[sid], "betweenness_rank": betweenness_rank[sid], "rank_gap": rank_gap,
            "top_connections": [{"station_id": peer,
                "station_name": next((s.get("station_name") for s in stations if s["station_id"] == peer), None),
                "trip_count": int(weight), "direction": direction}
                for peer, weight, direction in sorted(connections[sid], key=lambda item: item[1], reverse=True)[:10]]})
    low_usage_threshold = percentile((row["rental_count"] for row in candidates), 0.5)
    positive_gaps = [row["rank_gap"] for row in candidates if row["rank_gap"] > 0]
    rank_gap_threshold = percentile(positive_gaps, 0.9)
    pagerank_threshold = percentile((row["pagerank"] for row in candidates), 0.5)
    for row in candidates:
        count = len(candidates)
        row["usage_percentile"] = round(1 - (row["usage_rank"] - 1) / max(1, count - 1), 4)
        row["pagerank_percentile"] = round(1 - (row["pagerank_rank"] - 1) / max(1, count - 1), 4)
        row["candidate"] = bool(low_usage_threshold is not None and rank_gap_threshold is not None and
            row["rental_count"] <= low_usage_threshold and row["rank_gap"] >= rank_gap_threshold and
            row["pagerank"] >= (pagerank_threshold or 0))
    candidates.sort(key=lambda row: (row["candidate"], row["rank_gap"], row["pagerank"]), reverse=True)
    pagerank_top = sorted(candidates, key=lambda row: row["pagerank"], reverse=True)[:5]
    return {**source_meta(region_id), "available": True, "candidates": candidates,
            "candidate_count": sum(row["candidate"] for row in candidates), "pagerank_top": pagerank_top,
            "period_start": date_start or (observed_dates(region_id, date_start, date_end) or [None])[0],
            "period_end": date_end or (observed_dates(region_id, date_start, date_end) or [None])[-1],
            "components": full.get("components"), "betweenness_sample_nodes": full.get("betweenness_sample_nodes"),
            "selection_rule": {"low_usage_max": round(low_usage_threshold or 0, 2),
                "rank_gap_min": round(rank_gap_threshold or 0, 2),
                "pagerank_min": round(pagerank_threshold or 0, 8),
                "basis": "이용량 중앙값 이하이면서 양의 순위 차이 상위 10%, PageRank 중앙값 이상"},
            "message": "후보 임계값은 선택 기간의 실제 분포에서 계산합니다. 매개 중심성은 표본 근사이며 환승·관광 기능을 뜻하지 않습니다."}


@lru_cache(maxsize=32)
def hidden_hub_validation(region_id, station_id, date_end=None):
    dates = observed_dates(region_id, None, date_end)
    station = next((s for s in snapshot()["stations"] if s["region_id"] == region_id
                    and s["station_id"] == station_id), None)
    if station is None or not dates:
        return {**source_meta(region_id), "available": False, "station_id": station_id, "windows": [],
                "message": "대여소 또는 관측 기간을 확인할 수 없습니다."}
    end = date.fromisoformat(dates[-1])
    windows = []
    for size in (7, 14, 30):
        start = (end - timedelta(days=size - 1)).isoformat()
        result = hidden_hubs(region_id, start, end.isoformat(), include_betweenness=False)
        row = next((item for item in result.get("candidates", []) if item["station_id"] == station_id), None)
        profile = next((item for item in profiles(region_id, start, end.isoformat()) if item["station_id"] == station_id), None)
        windows.append({"days": size, "date_start": start, "date_end": end.isoformat(),
            "observed_day_count": len(observed_dates(region_id, start, end.isoformat())),
            "rental_count": profile.get("rental_count") if profile else None,
            "return_count": profile.get("return_count") if profile else None,
            **({key: row.get(key) for key in ("pagerank", "pagerank_rank", "pagerank_percentile", "usage_rank",
                "usage_percentile", "betweenness", "betweenness_rank", "rank_gap", "candidate")} if row else {}),
            "minimum_observation_pass": bool(profile and len(observed_dates(region_id, start, end.isoformat())) >= size
                and profile["rental_count"] + (profile.get("return_count") or 0) >= 100)})
    full = hidden_hubs(region_id, None, date_end) if date_end else hidden_hubs(region_id)
    detail = next((item for item in full.get("candidates", []) if item["station_id"] == station_id), None)
    if detail is None:
        return {**source_meta(region_id), "available": False, "station_id": station_id, "windows": windows,
                "message": "선택 대여소가 유효한 OD 그래프에 포함되지 않았습니다."}
    candidate_windows = sum(bool(item.get("candidate")) for item in windows)
    rank_span = max(item["pagerank_rank"] for item in windows if item.get("pagerank_rank")) - min(
        item["pagerank_rank"] for item in windows if item.get("pagerank_rank"))
    role = "기간 반복 검토 후보" if candidate_windows >= 2 else "연결 중요도 추가 검토 후보"
    return {**source_meta(region_id), "available": True, "station": station, "metrics": detail,
        "period_start": dates[0], "period_end": dates[-1], "windows": windows,
        "sensitivity": {"candidate_windows": candidate_windows, "total_windows": 3,
            "pagerank_rank_span": rank_span, "all_minimum_observation_pass": all(x["minimum_observation_pass"] for x in windows)},
        "role": role,
        "why_not_usage_top": f"전체 대여량 {detail['usage_rank']}위로 단순 이용량 TOP 10 밖이지만 PageRank는 {detail['pagerank_rank']}위입니다.",
        "limitations": ["31일 서울 집계 OD 한 달만 검증해 계절 안정성을 판단할 수 없습니다.",
            f"매개 중심성은 {full.get('betweenness_sample_nodes')}개 노드 표본 근사입니다.",
            "PageRank·순위 차이만으로 환승 거점이나 운영 효과를 확정할 수 없습니다."],
        "message": "7·14·30일 동일 종료일 창과 최소 100건·요청 일수 충족 여부를 함께 제시합니다."}


@lru_cache(maxsize=64)
def station_role_history(region_id, station_id, date_end=None):
    dates = observed_dates(region_id, None, date_end)
    if not dates:
        return {**source_meta(region_id), "available": False, "station_id": station_id, "windows": [],
                "message": "기간별 역할을 계산할 이용 기록이 없습니다."}
    end = date.fromisoformat(dates[-1])
    windows = []
    for size in (7, 14, 30):
        start = (end - timedelta(days=size - 1)).isoformat()
        end_text = end.isoformat()
        profile = next((row for row in profiles(region_id, start, end_text) if row["station_id"] == station_id), None)
        cluster = next((row for row in clusters(region_id, start, end_text).get("clusters", [])
                        if row["station_id"] == station_id), None)
        edges = aggregated_od(region_id, start, end_text)
        degrees = Counter()
        for edge in edges:
            degrees[edge["origin_station_id"]] += edge["trip_count"]
            degrees[edge["destination_station_id"]] += edge["trip_count"]
        ranked = [sid for sid, _ in degrees.most_common()]
        degree_rank = ranked.index(station_id) + 1 if station_id in degrees else None
        hourly = profile.get("hourly") if profile else None
        total = sum(hourly or [])
        windows.append({"days": size, "date_start": start, "date_end": end_text,
            "observed_day_count": len(observed_dates(region_id, start, end_text)),
            "rental_count": profile.get("rental_count") if profile else None,
            "return_count": profile.get("return_count") if profile else None,
            "peak_hour": max(range(24), key=lambda hour: hourly[hour]) if total else None,
            "peak_hour_share": round(max(hourly) / total, 4) if total else None,
            "cluster_id": cluster.get("cluster_id") if cluster else None,
            "cluster_role": cluster.get("role") if cluster else None,
            "weighted_degree": degrees.get(station_id) if station_id in degrees else None,
            "weighted_degree_rank": degree_rank,
            "network_station_count": len(ranked) or None})
    recent, baseline = windows[0], windows[-1]
    return {**source_meta(region_id), "available": any(row["rental_count"] is not None for row in windows),
            "station_id": station_id, "period_end": end.isoformat(), "windows": windows,
            "role_change": {"cluster_changed": recent["cluster_id"] is not None and baseline["cluster_id"] is not None
                and recent["cluster_id"] != baseline["cluster_id"],
                "weighted_degree_rank_change": (baseline["weighted_degree_rank"] - recent["weighted_degree_rank"])
                if baseline["weighted_degree_rank"] is not None and recent["weighted_degree_rank"] is not None else None,
                "peak_hour_changed": recent["peak_hour"] is not None and baseline["peak_hour"] is not None
                and recent["peak_hour"] != baseline["peak_hour"]},
            "message": "7·14·30일 창을 같은 종료일로 비교합니다. 가중 연결 순위는 입·출 OD 건수 합이며 역할 변화의 확정적 원인을 뜻하지 않습니다."}


def _weighted_degree_ranks(region_id, start, end):
    degrees = Counter()
    for edge in aggregated_od(region_id, start, end):
        degrees[edge["origin_station_id"]] += edge["trip_count"]
        degrees[edge["destination_station_id"]] += edge["trip_count"]
    ranked = [sid for sid, _ in degrees.most_common()]
    return degrees, {sid: index for index, sid in enumerate(ranked, 1)}, len(ranked)


@lru_cache(maxsize=32)
def role_candidates(region_id, date_start=None, date_end=None):
    dates = observed_dates(region_id, date_start, date_end)
    if not dates:
        return {**source_meta(region_id), "available": False, "types": {}, "rules": {},
                "message": "숨은 역할을 계산할 대여소별 이용 기록이 없습니다."}
    hidden = hidden_hubs(region_id, date_start, date_end)
    imbalance = imbalance_result(region_id, date_start, date_end)
    names = {s["station_id"]: s.get("station_name") for s in snapshot()["stations"] if s["region_id"] == region_id}
    selected_profiles = [row for row in profiles(region_id, date_start, date_end) if row.get("hourly") and names.get(row["station_id"])]
    volume_floor = percentile((row["rental_count"] for row in selected_profiles), 0.25)
    concentration_rows = []
    for row in selected_profiles:
        total = sum(row["hourly"] or [])
        share = max(row["hourly"]) / total if total else 0
        concentration_rows.append({"station_id": row["station_id"], "station_name": names.get(row["station_id"]),
            "rental_count": row["rental_count"], "peak_hour": max(range(24), key=lambda h: row["hourly"][h]),
            "peak_hour_share": round(share, 4)})
    eligible_concentration = [row for row in concentration_rows if row["rental_count"] >= (volume_floor or 0)]
    concentration_threshold = percentile((row["peak_hour_share"] for row in eligible_concentration), 0.9)
    concentrated_all = sorted((row for row in eligible_concentration if row["peak_hour_share"] >= (concentration_threshold or 1)),
                              key=lambda row: row["peak_hour_share"], reverse=True)

    end = date.fromisoformat(dates[-1])
    recent_start, baseline_start = (end - timedelta(days=6)).isoformat(), (end - timedelta(days=29)).isoformat()
    recent_profiles = {row["station_id"]: row for row in profiles(region_id, recent_start, end.isoformat())}
    baseline_profiles = {row["station_id"]: row for row in profiles(region_id, baseline_start, end.isoformat())}
    recent_clusters = {row["station_id"]: row for row in clusters(region_id, recent_start, end.isoformat()).get("clusters", [])}
    baseline_clusters = {row["station_id"]: row for row in clusters(region_id, baseline_start, end.isoformat()).get("clusters", [])}
    _, recent_ranks, recent_count = _weighted_degree_ranks(region_id, recent_start, end.isoformat())
    _, baseline_ranks, baseline_count = _weighted_degree_ranks(region_id, baseline_start, end.isoformat())
    changes = []
    for sid in set(recent_profiles) & set(baseline_profiles):
        recent, baseline = recent_profiles[sid], baseline_profiles[sid]
        if not names.get(sid) or baseline["rental_count"] < (volume_floor or 0):
            continue
        recent_hour = max(range(24), key=lambda h: (recent.get("hourly") or [0] * 24)[h])
        baseline_hour = max(range(24), key=lambda h: (baseline.get("hourly") or [0] * 24)[h])
        hour_distance = min(abs(recent_hour - baseline_hour), 24 - abs(recent_hour - baseline_hour)) / 12
        recent_percentile = 1 - (recent_ranks.get(sid, recent_count) - 1) / max(1, recent_count - 1)
        baseline_percentile = 1 - (baseline_ranks.get(sid, baseline_count) - 1) / max(1, baseline_count - 1)
        cluster_changed = recent_clusters.get(sid, {}).get("role") != baseline_clusters.get(sid, {}).get("role")
        score = abs(recent_percentile - baseline_percentile) + hour_distance + (1 if cluster_changed else 0)
        changes.append({"station_id": sid, "station_name": names.get(sid), "change_score": round(score, 4),
            "weighted_degree_percentile_change": round(recent_percentile - baseline_percentile, 4),
            "peak_hour_recent": recent_hour, "peak_hour_baseline": baseline_hour,
            "cluster_role_recent": recent_clusters.get(sid, {}).get("role"),
            "cluster_role_baseline": baseline_clusters.get(sid, {}).get("role"), "cluster_changed": cluster_changed})
    change_threshold = percentile((row["change_score"] for row in changes), 0.9)
    changed_all = sorted((row for row in changes if row["change_score"] >= (change_threshold or 1)),
                         key=lambda row: row["change_score"], reverse=True)
    cluster_result = clusters(region_id, date_start, date_end)
    hidden_rows = [row for row in hidden.get("candidates", []) if row.get("candidate")]
    imbalance_rows = [row for row in imbalance.get("stations", []) if row.get("imbalance_candidate")]
    outflow_rows = [row for row in imbalance_rows if row.get("persistent_direction") == "net_outflow"]
    inflow_rows = [row for row in imbalance_rows if row.get("persistent_direction") == "net_inflow"]
    return {**source_meta(region_id), "available": True, "period_start": dates[0], "period_end": dates[-1],
        "types": {
            "low_usage_high_connectivity": hidden_rows[:20], "persistent_imbalance": imbalance_rows[:20],
            "persistent_outflow": outflow_rows[:20], "persistent_inflow": inflow_rows[:20],
            "time_concentrated": concentrated_all[:20], "role_changed": changed_all[:20]},
        "counts": {"low_usage_high_connectivity": hidden.get("candidate_count", len(hidden_rows)),
            "persistent_imbalance": len(imbalance_rows), "time_concentrated": len(concentrated_all),
            "persistent_outflow": len(outflow_rows), "persistent_inflow": len(inflow_rows),
            "role_changed": len(changed_all)}, "pagerank_top": hidden.get("pagerank_top", []),
        "rules": {"low_usage_high_connectivity": hidden.get("selection_rule"),
            "persistent_imbalance": imbalance.get("selection_rule"),
            "persistent_outflow": {**imbalance.get("selection_rule", {}), "direction": "net_outflow",
                "basis": "불균형 후보 규칙을 충족하고 관측일의 우세 방향이 순유출(대여-반납>0)"},
            "persistent_inflow": {**imbalance.get("selection_rule", {}), "direction": "net_inflow",
                "basis": "불균형 후보 규칙을 충족하고 관측일의 우세 방향이 순유입(대여-반납<0)"},
            "time_concentrated": {"minimum_rentals": round(volume_floor or 0, 2),
                "peak_hour_share_min": round(concentration_threshold or 0, 4),
                "basis": "이용량 하위 25% 제외 후 최대 시간대 비중 상위 10%"},
            "role_changed": {"change_score_min": round(change_threshold or 0, 4),
                "basis": "7일과 30일의 연결 순위 백분위 차이·집중 시간 이동·군집 역할 변경 합산 점수 상위 10%"}},
        "cluster_distribution": cluster_result.get("cluster_summaries", []),
        "message": "모든 임계값은 선택 데이터의 경험 분포에서 계산하며 후보는 운영상 검토 대상이지 실제 역할이나 효과의 확정이 아닙니다."}


@lru_cache(maxsize=64)
def network(region_id, date_start=None, date_end=None, node_limit=40):
    records = aggregated_od(region_id, date_start, date_end)
    if not records:
        return {**source_meta(region_id), "available": False, "nodes": [], "edges": [],
                "edge_count": 0, "visible_edge_count": 0, "message": "이동 경로 데이터 미확보"}
    merged = Counter()
    for row in records:
        merged[(row["origin_station_id"], row["destination_station_id"])] += row["trip_count"]
    station_inventory = [s for s in snapshot()["stations"] if s["region_id"] == region_id]
    ranking = centrality(station_inventory, records, include_betweenness=False)["rankings"]
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
            "period_start": (observed_dates(region_id, date_start, date_end) or [None])[0],
            "period_end": (observed_dates(region_id, date_start, date_end) or [None])[-1],
            "message": ("대전 개별 Trip에서 집계한 연결입니다." if region_id == "daejeon"
                        else "서울의 집계 OD 연결이며 개별 Trip 기록은 아닙니다.")}


@lru_cache(maxsize=32)
def centrality_result(region_id, date_start=None, date_end=None):
    records = aggregated_od(region_id, date_start, date_end)
    ids = {s for row in records for s in (row["origin_station_id"], row["destination_station_id"])}
    stations = [s for s in snapshot()["stations"] if s["region_id"] == region_id and s["station_id"] in ids
                and (region_id != "seoul" or (s["latitude"] is not None and s["longitude"] is not None))]
    result = centrality(stations, records)
    return {**source_meta(region_id), **result, "rankings": result["rankings"][:100]}


def similarity_result(region_id, station_id, date_start=None, date_end=None):
    result = station_similarity(profiles(region_id, date_start, date_end), station_id)
    return {**source_meta(region_id), "station_id": station_id, "similar": result,
            "available": bool(result), "message": "정규화한 시간대·주말 비중의 코사인 유사도. 절대 이용량은 별도 표시." if result else "비교할 이용 기록이 없습니다."}


def compare(region_ids, date_start=None, date_end=None, align_common=False):
    selected = region_ids or [r["region_id"] for r in REGIONS]
    common_period = None
    if align_common and not date_start and not date_end:
        ranges = []
        for rid in selected:
            dates = observed_dates(rid)
            if dates:
                ranges.append((dates[0], dates[-1]))
        if len(ranges) >= 2:
            start, end = max(row[0] for row in ranges), min(row[1] for row in ranges)
            if start <= end:
                date_start, date_end, common_period = start, end, {"date_start": start, "date_end": end}
    items = [overview(rid, date_start, date_end) for rid in selected]
    dates = [set(x["observed_dates"]) for x in items if x["total_rentals"] is not None]
    same_dates = len(dates) >= 2 and all(d == dates[0] for d in dates)
    rows = []
    for item in items:
        top = centrality_result(item["region_id"], date_start, date_end)["rankings"][:1] if item["has_od"] else []
        rows.append({**{k: value for k, value in item.items() if k != "map_stations"}, "centrality_top": top[0] if top else None})
    return {"regions": rows, "common_period": common_period,
            "same_observed_dates": same_dates,
            "limitations": ["모집단·수집 범위·운영방식이 다릅니다.", "OD 집계와 연간 총량을 직접 비교할 수 없습니다.",
                            "N/A는 결측 또는 비교 불가를 뜻합니다."]}
