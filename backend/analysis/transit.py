"""Geographic proximity is a linkage opportunity, never proof of an actual transfer."""
import math
import numpy as np
from sklearn.neighbors import BallTree

EARTH_M = 6371008.8
def valid_point(lat, lon):
    try:
        return math.isfinite(float(lat)) and math.isfinite(float(lon)) and 33 <= float(lat) <= 39 and 124 <= float(lon) <= 132
    except (ValueError, TypeError):
        return False

def match_stations(stations, stops):
    trees = {}
    for kind in ["버스", "지하철"]:
        selected = [s for s in stops if s["type"] == kind and valid_point(s["lat"], s["lon"])]
        if selected:
            trees[kind] = (selected, BallTree(np.radians([[float(s["lat"]), float(s["lon"])] for s in selected]), metric="haversine"))
    matched = []
    for station in stations:
        row = dict(station)
        good = valid_point(row.get("latitude"), row.get("longitude"))
        distances = []
        for kind, prefix in [("버스", "bus"), ("지하철", "subway")]:
            for radius in [300, 500]:
                row[f"{prefix}_within_{radius}m"] = None
            row[f"nearest_{prefix}_distance_m"] = None
            if good and kind in trees:
                stops_k, tree = trees[kind]
                point = np.radians([[float(row["latitude"]), float(row["longitude"])]])
                distance, index = tree.query(point, k=1)
                value = float(distance[0][0] * EARTH_M)
                distances.append(value)
                row[f"nearest_{prefix}_distance_m"] = round(value, 3)
                row[f"nearest_{prefix}_stop_id"] = stops_k[int(index[0][0])]["stop_id"]
                for radius in [300, 500]:
                    row[f"{prefix}_within_{radius}m"] = int(tree.query_radius(point, r=radius / EARTH_M, count_only=True)[0])
        row["nearest_stop_distance_m"] = round(min(distances), 3) if distances else None
        row["coordinate_valid"] = good
        matched.append(row)
    return matched

def hourly_linkage(rows, near_subway_ids, known_ids):
    """Accept actual departure-hour OD records; OR rule counts each trip at most once."""
    totals = {}
    for row in rows:
        key = (row["date"], int(row["hour"]))
        entry = totals.setdefault(key, {"date": key[0], "hour": key[1], "total_count": 0, "linked_count": 0, "unknown_endpoint_count": 0})
        count = int(row["trip_count"])
        if count < 0 or not 0 <= key[1] <= 23:
            raise ValueError("잘못된 OD 수치/시간")
        origin, destination = row["origin_station_id"], row["destination_station_id"]
        entry["total_count"] += count
        if origin in near_subway_ids or destination in near_subway_ids:
            entry["linked_count"] += count
        if origin not in known_ids or destination not in known_ids:
            entry["unknown_endpoint_count"] += count
    return list(totals.values())
