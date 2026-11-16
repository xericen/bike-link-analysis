"""Offline-only WIZ-compatible projections. Never imported by cache lookup."""
from backend.services import real_data, all_regions

def dashboard_extra(region_id,date_start,date_end):
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
    return {"heatmap": heatmap, "cluster_points": points,
              "cluster_count": len(result_clusters["clusters"]),
              "selected_k": result_clusters.get("selected_k"),
              "comparison": comparison, "comparison_dates": common_dates,
              "silhouette": max((x["silhouette"] for x in result_clusters.get("diagnostics", [])), default=None),
              "quality": result_clusters.get("quality"),
              "cluster_representatives": representatives}

def build(action,region_id,start,end):
    if action == "planning":
        from backend.services.planning import build as planning_build
        return planning_build(region_id,start,end)
    if action == "transit_linkage":
        from backend.services.goal_linkage import build as linkage_build
        return linkage_build(region_id,start,end)
    if action == "vulnerability":
        from backend.services.vulnerability import analyze,build_all
        return build_all(start,end) if region_id=="all" else analyze(region_id,start,end,top_n=20)
    if region_id == "all":
        return all_regions.get(action,start,end)
    if action == "research":
        return real_data.role_candidates(region_id,start,end)
    if action == "overview":
        result=real_data.overview(region_id,start,end)
        rows=result.pop("map_stations",[])
        result["map_stations"]=rows[::max(1,len(rows)//120)][:120]
        result["map_sample_count"]=len(result["map_stations"])
        return result
    if action == "network":
        network=real_data.network(region_id,start,end)
        edges=[r for r in network["edges"] if r["origin_station_id"]!=r["destination_station_id"]][:20]
        ids={sid for r in edges for sid in (r["origin_station_id"],r["destination_station_id"])}
        return {**network,"edges":edges,"nodes":[r for r in network["nodes"] if r["station_id"] in ids],
                "display_note":"동일 대여소 출발·도착 기록은 연결 도식에서 제외했습니다."}
    if action == "centrality":
        result=real_data.centrality_result(region_id,start,end)
        result["rankings"]=result["rankings"][:15]
        return result
    if action == "dashboard_extra":
        return dashboard_extra(region_id,start,end)
    raise ValueError("Unsupported offline projection")
