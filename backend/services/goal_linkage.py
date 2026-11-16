"""Offline goal-aligned linkage metrics. No web-request analysis."""
from backend.services import transit

def summarize(result):
    rows = result.get("stations", [])
    located = [s for s in rows if s.get("coordinate_valid") and s.get("nearest_stop_distance_m") is not None]
    subway = [s for s in located if s.get("nearest_subway_distance_m") is not None]
    hours = result.get("hourly_station_linkage") or []
    total = sum(h["total_count"] for h in hours)
    result["goal_metrics"] = {
        "located_station_count": len(located),
        "subway_station_count": len(subway),
        "subway_300m_ratio": sum(s["nearest_subway_distance_m"] <= 300 for s in subway) / len(subway) if subway else None,
        "outside_500m_active_count": sum(s["nearest_stop_distance_m"] > 500 and (s.get("rental_count") or 0) > 0 for s in located) if located else None,
        "linked_trip_share": sum(h["linked_count"] for h in hours) / total if total else None,
        "linked_trip_total": total or None,
    }
    return result

def build(city,start,end):
    if city != "all":
        return summarize(transit.linkage(city,start,end))
    cities = [summarize(transit.linkage(c,start,end)) for c in ("seoul","daejeon","sejong")]
    hours = {}
    for c in cities:
        for row in c.get("hourly_station_linkage") or []:
            h = hours.setdefault(row["hour"], {"hour":row["hour"],"total_count":0,"linked_count":0,"unknown_endpoint_count":0})
            for key in ("total_count","linked_count","unknown_endpoint_count"):
                h[key] += row[key]
    for h in hours.values():
        h["linkage_share"] = h["linked_count"]/h["total_count"] if h["total_count"] else None
    return summarize({
        "available":any(c["available"] for c in cities),"cities":cities,
        "stations":[s for c in cities for s in c["stations"]],
        "map_stops":[s for c in cities for s in c.get("map_stops",[])],
        "hourly_station_linkage":sorted(hours.values(),key=lambda r:r["hour"]) or None,
        "map_display_note":"정류장 음영은 도시별 최대600개 표본. 거리·면적·KPI는 전체 자료로 계산. 세종2025-10은 공통2026-10에 합산하지 않음.",
    })
