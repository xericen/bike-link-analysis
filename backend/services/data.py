import json
from functools import lru_cache
from pathlib import Path

from backend.analysis.clustering import cluster_stations
from backend.analysis.network import centrality
from backend.analysis.similarity import station_similarity

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "samples" / "demo.json"

@lru_cache
def load_data():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

def metadata():
    return load_data()["metadata"]

def regions():
    return load_data()["regions"]

def stations(region_id=None):
    items = load_data()["stations"]
    if region_id:
        items = [s for s in items if s["region_id"] == region_id]
    timestamp = metadata()["period_end"] + "T23:00:00+09:00"
    return [{**s, "rental_count": sum(s["hourly"]), "timestamp": timestamp} for s in items]

def station(station_id):
    return next((s for s in stations() if s["station_id"] == station_id), None)

def clusters(region_id=None):
    return cluster_stations(stations(region_id))

def overview(region_id=None):
    items = stations(region_id)
    hourly = [sum(s["hourly"][i] for s in items) for i in range(24)]
    return {"metadata": metadata(), "region_id": region_id or "all", "total_rentals": sum(hourly), "station_count": len(items), "hourly": hourly, "stations": items}

def od(region_id=None):
    if not metadata()["has_od"]:
        return []
    ids = {s["station_id"] for s in stations(region_id)}
    return [edge for edge in load_data().get("od", []) if edge["origin_station_id"] in ids and edge["destination_station_id"] in ids]

def network(region_id=None):
    edges = od(region_id)
    return {"metadata": metadata(), "available": bool(edges), "nodes": stations(region_id), "edges": edges, "message": "합성 데모 OD 기록" if edges else "이 지역의 OD 기록이 없어 이동 네트워크를 계산할 수 없습니다."}

def centrality_result(region_id=None):
    edges = od(region_id)
    return {"metadata": metadata(), "available": bool(edges), "rankings": centrality(stations(region_id), edges), "message": "합성 데모 OD 기록 기반" if edges else "이 지역의 OD 기록이 없어 중심성을 계산할 수 없습니다."}

def compare_regions():
    return [{"region_id": r["region_id"], "name": r["name"], "total_rentals": overview(r["region_id"])["total_rentals"], "station_count": overview(r["region_id"])["station_count"]} for r in regions()]
