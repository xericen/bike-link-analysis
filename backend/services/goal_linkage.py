"""Offline goal-aligned linkage metrics. No web-request analysis."""
from backend.services import transit,city_anchors

def valid_distance(value):
    from numbers import Real
    import math
    return isinstance(value,Real) and not isinstance(value,bool) and math.isfinite(float(value)) and value>=0

def summarize(result):
    rows=result.get("stations",[])
    coordinates=[s for s in rows if s.get("coordinate_valid")]
    located=[s for s in coordinates if valid_distance(s.get("nearest_stop_distance_m"))]
    anchors=[s for s in coordinates if valid_distance(s.get("nearest_anchor_distance_m"))]
    anchor_mode=bool(result.get("anchor_label")) or any("nearest_anchor_distance_m" in s for s in rows)
    # Legacy subway-only callers retain their own explicit, valid-distance population.
    subway=anchors if anchor_mode else [s for s in coordinates if valid_distance(s.get("nearest_subway_distance_m"))]
    axis=anchors if anchor_mode else located
    distance=lambda s:s["nearest_anchor_distance_m"] if anchor_mode else s["nearest_stop_distance_m"]
    hours=result.get("hourly_station_linkage") or []
    total=sum(h["total_count"] for h in hours)
    all_stops=[s for s in coordinates if valid_distance(s.get("nearest_all_stop_distance_m"))]
    result["goal_metrics"]={
        "anchor_label":result.get("anchor_label","도시별 앵커"),
        "anchor_300m_ratio":sum(s["nearest_anchor_distance_m"]<=300 for s in anchors)/len(anchors) if anchors else None,
        "anchor_300m_denominator_count":len(anchors),
        "anchor_distance_missing_or_invalid_count":len(coordinates)-len(anchors),
        "first_last_mile_count":sum(800<=distance(s)<=1500 and (s.get("rental_count") or 0)>0 for s in axis) if axis else None,
        "reference_all_stops_outside500":sum(s["nearest_all_stop_distance_m"]>500 and (s.get("rental_count") or 0)>0 for s in all_stops) if all_stops else None,
        "located_station_count":len(located),"subway_station_count":len(subway),
        "subway_300m_ratio":sum((s["nearest_anchor_distance_m"] if anchor_mode else s["nearest_subway_distance_m"])<=300 for s in subway)/len(subway) if subway else None,
        "outside_500m_active_count":sum(distance(s)>500 and (s.get("rental_count") or 0)>0 for s in axis) if axis else None,
        "linked_trip_share":sum(h["linked_count"] for h in hours)/total if total else None,
        "linked_trip_total":total or None}
    return result

def build(city,start,end):
    if city != "all":
        return summarize(city_anchors.linkage(city,start,end))
    cities = [summarize(city_anchors.linkage(c,start,end)) for c in ("seoul","daejeon","sejong")]
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
        "anchor_label":"도시별 앵커","map_display_note":"세 도시의 공통 2025-12 개별 대여이력과 도시별 지하철·BRT 앵커 기준.",
    })
