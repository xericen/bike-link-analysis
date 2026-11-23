"""Offline candidate validation. No production state or held-out-demand fallback."""
import copy
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree
from scipy.stats import rankdata
from shapely.geometry import Point, box
from shapely.ops import unary_union
from sklearn.neighbors import BallTree

from backend.analysis.planning import PROJECT, UNPROJECT
from backend.analysis.transit import EARTH_M

ROOT = Path(__file__).resolve().parents[2]
START, END = "2025-12-01", "2025-12-31"
CITIES = ("seoul", "daejeon", "sejong")
FILE = ROOT / "data/reference/method_validation_202512.json"
MATCH_RADIUS = 300
TOP_K = 10
MASK_N = 10
SEEDS = (42, 43, 44)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dependencies():
    return {
        "experiment_code": sha(__file__),
        "transit_demand": sha(ROOT / "data/reference/transit_demand_202512.json"),
        "planning_code": sha(ROOT / "backend/analysis/planning.py"),
    }


def rank_candidates(rows, policy="equal", use_population=True):
    """Same midrank percentiles as grid_sites; no rounding before decisions."""
    rows = copy.deepcopy(rows)
    keys = (["population_density_km2"] if use_population else []) + [
        "facilities_within_500m", "nearby_rentals_1000m", "gap_ratio"]
    weights = {k: 1 / len(keys) for k in keys}
    special = {"demand": "nearby_rentals_1000m", "gap": "gap_ratio"}.get(policy)
    if special:
        weights = {k: (0.5 if k == special else 0.5 / (len(keys) - 1)) for k in keys}
    if rows:
        for key in keys:
            values = np.array([r[key] for r in rows], dtype=float)
            percentiles = (rankdata(values, method="average") - 0.5) / len(rows)
            for r, value in zip(rows, percentiles):
                r.setdefault("score_components", {})[key] = float(value)
        for r in rows:
            r["score"] = sum(weights[k] * r["score_components"][k] for k in keys)
        rows.sort(key=lambda r: (-r["score"], r["site_id"]))
        for index, r in enumerate(rows, 1):
            r["rank"] = index
    return rows, weights


def grid_candidates(boundary, baseline, stations, facilities, districts, step=500,
                    policy="equal", use_population=True):
    """Equivalent candidate rules to production, with fast independent percentile ranking."""
    located = [r for r in stations if r.get("coordinate_valid")]
    if not located:
        return [], {}
    tree = BallTree(np.radians([[r["latitude"], r["longitude"]] for r in located]),
                    metric="haversine")
    projected_facilities = [PROJECT(r["lon"], r["lat"]) for r in facilities]
    facility_tree = cKDTree(projected_facilities) if projected_facilities else None
    x0, y0, x1, y1 = boundary.bounds
    rows = []
    for x in range(int(x0 // step) * step, int(x1) + step, step):
        for y in range(int(y0 // step) * step, int(y1) + step, step):
            cell = box(x, y, x + step, y + step).intersection(boundary)
            if cell.is_empty or cell.area < step * step * 0.25:
                continue
            centre = cell.representative_point()
            lon, lat = UNPROJECT(centre.x, centre.y)
            distance, _ = tree.query(np.radians([[lat, lon]]), k=1)
            nearest = float(distance[0, 0] * EARTH_M)
            if nearest <= 300:
                continue
            nearby = tree.query_radius(np.radians([[lat, lon]]), r=1000 / EARTH_M)[0]
            demand = sum(located[int(i)].get("rental_count") or 0 for i in nearby)
            count = len(facility_tree.query_ball_point([centre.x, centre.y], 500)) if facility_tree else 0
            if not demand and not count:
                continue
            district = next((d for d in districts if d["geometry"].covers(centre)), None)
            density = district.get("population_density_km2") if district else None
            if district is None or (use_population and density is None):
                continue
            rows.append({
                "site_id": f"grid-{x}-{y}", "station_id": f"grid-{x}-{y}",
                "latitude": lat, "longitude": lon, "district": district["name"],
                "population_density_km2": density if use_population else None,
                "facilities_within_500m": count, "nearby_rentals_1000m": int(demand),
                "nearest_station_distance_m": nearest,
                "gap_ratio": cell.difference(baseline).area / cell.area,
                "potential_added_area_m2": centre.buffer(300, quad_segs=16).intersection(boundary).difference(baseline).area,
            })
    return rank_candidates(rows, policy, use_population)


def geographic_matches(targets, candidates, radius=MATCH_RADIUS):
    """Maximum cardinality one-to-one matches, then minimum distance."""
    if not targets or not candidates:
        return {"hits": 0, "pairs": [], "recall": 0.0 if targets else None}
    a = np.array([PROJECT(r["longitude"], r["latitude"]) for r in targets])
    b = np.array([PROJECT(r["longitude"], r["latitude"]) for r in candidates])
    distances = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    # Penalty dominates the sum of all valid distances; do not greedily double count.
    penalty = (max(len(a), len(b)) + 1) * (radius + 1)
    cost = np.where(distances <= radius, distances, penalty)
    ri, ci = linear_sum_assignment(cost)
    pairs = [{"station_id": targets[i]["station_id"],
              "site_id": candidates[j]["site_id"], "distance_m": float(distances[i, j])}
             for i, j in zip(ri, ci) if distances[i, j] <= radius]
    return {"hits": len(pairs), "pairs": pairs, "recall": len(pairs) / len(targets)}


def retain_training(stations, od_rows, hidden_ids):
    """Both ends of hidden-station trips are removed from every demand feature."""
    hidden = set(hidden_ids)
    rentals, returns = Counter(), Counter()
    source_total, kept_total = 0, 0
    for r in od_rows:
        count = int(r["trip_count"])
        source_total += count
        o, d = r["origin_station_id"], r["destination_station_id"]
        if o in hidden or d in hidden:
            continue
        rentals[o] += count
        returns[d] += count
        kept_total += count
    kept = []
    for s in stations:
        if s["station_id"] in hidden:
            continue
        kept.append({**s, "rental_count": rentals[s["station_id"]],
                     "return_count": returns[s["station_id"]]})
    return kept, {"source_od_trips": source_total, "retained_od_trips": kept_total,
                  "removed_od_trips": source_total - kept_total,
                  "hidden_ids": sorted(hidden),
                  "hidden_station_count_in_training": sum(r["station_id"] in hidden for r in kept)}


def baseline_geometry(anchors, boundary, radius):
    points = {(float(a["lat"]), float(a["lon"])) for a in anchors}
    return unary_union([Point(*PROJECT(lon, lat)).buffer(radius, quad_segs=16)
                        for lat, lon in points]).intersection(boundary)


def top_area(rows, baseline, boundary, buffer_m=300):
    buffers = [Point(*PROJECT(r["longitude"], r["latitude"])).buffer(buffer_m, quad_segs=16)
               .intersection(boundary).difference(baseline) for r in rows[:TOP_K]]
    return unary_union(buffers).area if buffers else 0.0


def sensitivity(boundary, stations, facilities, districts, anchors, city):
    configs = [
        (500, 500, "equal", 300), (300, 500, "equal", 300),
        (800, 500, "equal", 300), (500, 250, "equal", 300),
        (500, 750, "equal", 300), (500, 500, "demand", 300),
        (500, 500, "gap", 300), (500, 500, "equal", 500),
    ]
    pool_cache, baselines = {}, {}
    result = []
    base_top = None
    for anchor_m, grid_m, policy, buffer_m in configs:
        if anchor_m not in baselines:
            baselines[anchor_m] = baseline_geometry(anchors, boundary, anchor_m)
        baseline = baselines[anchor_m]
        key = (anchor_m, grid_m)
        if key not in pool_cache:
            pool_cache[key] = grid_candidates(boundary, baseline, stations, facilities, districts,
                                               step=grid_m, use_population=city != "sejong")[0]
        ranked, weights = rank_candidates(pool_cache[key], policy, city != "sejong")
        top = ranked[:TOP_K]
        if base_top is None:
            base_top = top
        ids = {r["site_id"] for r in top}
        original = {r["site_id"] for r in base_top}
        shared, union = ids & original, ids | original
        matching = geographic_matches([{**r, "station_id": r["site_id"]} for r in base_top], top)
        row = {"anchor_radius_m": anchor_m, "grid_step_m": grid_m, "policy": policy,
               "candidate_buffer_m": buffer_m, "weights": weights, "candidate_count": len(ranked),
               "top": top, "top_k": TOP_K,
               "exact_jaccard": len(shared) / len(union) if union else None,
               "geographic_top10_overlap": matching["recall"],
               "mean_common_rank_shift": float(np.mean([abs(next(i for i,r in enumerate(base_top) if r["site_id"] == sid) -
                                                           next(i for i,r in enumerate(top) if r["site_id"] == sid))
                                                          for sid in shared])) if shared else None,
               "union_added_area_m2": top_area(top, baseline, boundary, buffer_m),
               "ranking_affected": buffer_m == 300,
               "note": "후보 버퍼는 점수 입력이 아니므로 순위가 같아도 강건성 증거로 세지 않습니다." if buffer_m != 300 else ""}
        result.append(row)
    return result


def mask_folds(stations, boundary):
    active = [r for r in stations if r.get("coordinate_valid") and r.get("rental_count", 0) > 0
              and boundary.covers(Point(*PROJECT(r["longitude"], r["latitude"])))]
    active.sort(key=lambda r: (-r["rental_count"], r["station_id"]))
    if not active:
        return []
    n = min(MASK_N, len(active))
    folds = [("high_usage", 0, active[:n])]
    ascending = sorted(active, key=lambda r: (r["rental_count"], r["station_id"]))
    strata = np.array_split(np.arange(len(ascending)), 3)
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        selected = []
        for i, stratum in enumerate(strata):
            k = min(len(stratum), n // 3 + (i < n % 3))
            selected.extend(ascending[int(j)] for j in rng.choice(stratum, k, replace=False))
        folds.append(("stratified", seed, selected))
    blocks = {}
    for r in active:
        x, y = PROJECT(r["longitude"], r["latitude"])
        blocks.setdefault((int(x // 1000), int(y // 1000)), []).append(r)
    for i, (_, group) in enumerate(sorted(blocks.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:2]):
        folds.append(("spatial_1km_block", i, group))
    return folds


def backtest(boundary, stations, facilities, districts, anchors, od_rows, city):
    baseline = baseline_geometry(anchors, boundary, 500)
    results = []
    for kind, seed, heldout in mask_folds(stations, boundary):
        hidden = [r["station_id"] for r in heldout]
        training, audit = retain_training(stations, od_rows, hidden)
        ranked, _ = grid_candidates(boundary, baseline, training, facilities, districts,
                                    use_population=city != "sejong")
        only_demand = sorted(ranked, key=lambda r: (-r["nearby_rentals_1000m"], r["site_id"]))
        non_demand, _ = rank_candidates(ranked, "equal", city != "sejong")
        # Facilities (+population for Seoul/Daejeon) baseline has no demand or gap score.
        keys = ["facilities_within_500m"] + (["population_density_km2"] if city != "sejong" else [])
        facility_scores = {r["site_id"]: sum(r["score_components"][k] for k in keys) / len(keys)
                           for r in non_demand}
        only_facilities = sorted(ranked, key=lambda r: (-facility_scores[r["site_id"]], r["site_id"]))
        methods = {}
        for name, proposals in (("full", ranked), ("demand_only", only_demand),
                                 ("facilities_population_only", only_facilities)):
            methods[name] = geographic_matches(heldout, proposals[:TOP_K])
        rng = np.random.default_rng(1000 + seed)
        random_recalls = [geographic_matches(heldout, [ranked[int(j)] for j in
                          rng.choice(len(ranked), min(TOP_K, len(ranked)), replace=False)])["recall"]
                          for _ in range(30)] if ranked else [0.0] * 30
        opportunities = []
        for target in heldout:
            if geographic_matches([target], ranked)["hits"]:
                opportunities.append(target["station_id"])
        full = methods["full"]
        full["eligible_recall"] = full["hits"] / len(opportunities) if opportunities else None
        results.append({"fold": kind, "seed": seed, "target_count": len(heldout),
                        "targets": [{k: r.get(k) for k in ("station_id", "station_name", "rental_count",
                                                         "latitude", "longitude")} for r in heldout],
                        "feasible_within_match_radius_count": len(opportunities),
                        "infeasible_targets": [sid for sid in hidden if sid not in opportunities],
                        "candidate_count": len(ranked), "top_k": TOP_K, "match_radius_m": MATCH_RADIUS,
                        "maximum_possible_recall_at_k": min(TOP_K, len(heldout)) / len(heldout),
                        "spatial_block_all_stations_hidden": kind == "spatial_1km_block",
                        "training_audit": audit, "methods": methods,
                        "random_recall_mean": float(np.mean(random_recalls)),
                        "random_recall_std": float(np.std(random_recalls)),
                        "random_repetitions": 30})
    return results


def demand_matrix(data, radius=500):
    if not data.get("available"):
        return {"available": False, "message": data.get("message", "동일 기간 승하차 자료 미확보")}
    source = data.get("stations", [])
    usable = [r for r in source if r.get("transit_total") is not None and r["transit_total"] > 0 and
              r.get(f"bike_activity_{radius}m") is not None]
    excluded = [{"station_name": r.get("station_name"), "transit_total": r.get("transit_total"),
                 "reason": "승하차 합계 0·결측은 실제 무수요로 단정하지 않고 분류 보류"}
                for r in source if r not in usable]
    if not usable:
        return {"available": False, "message": "연결된 역별 수요 자료가 없습니다."}
    t = float(np.median([r["transit_total"] for r in usable]))
    b = float(np.median([r[f"bike_activity_{radius}m"] for r in usable]))
    rows = []
    labels = {"high_high": "두 이용이 함께 집중", "high_low": "자전거 연계 여건 점검",
              "low_high": "지역 자전거 역할 점검", "low_low": "관측 활동 낮음"}
    for r in usable:
        key = ("high" if r["transit_total"] > 0 and r["transit_total"] >= t else "low") + "_" + (
            "high" if r[f"bike_activity_{radius}m"] > 0 and r[f"bike_activity_{radius}m"] >= b else "low")
        count = r[f"bike_station_count_{radius}m"]
        rows.append({**r, "quadrant": key, "interpretation": labels[key],
                     "bike_per_station": r[f"bike_activity_{radius}m"] / count if count else None,
                     "transit_at_threshold": r["transit_total"] == t,
                     "bike_at_threshold": r[f"bike_activity_{radius}m"] == b})
    return {"available": True, "radius_m": radius, "threshold_rule": "도시 내 중앙값 이상=높음(0은 낮음); 동률은 별도 표시",
            "transit_median": t, "bike_median": b,
            "counts": {k: sum(r["quadrant"] == k for r in rows) for k in labels},
            "matched_count": len(rows), "source_station_names": data.get("rail_unique_station_names"),
            "linked_station_count": len(source), "excluded_rows": excluded,
            "rows": rows, "limitations": data.get("limitations", []) + [
                "역 주변 활동의 공존이며 실제 환승·잠재 수요의 예측이 아닙니다.",
                "인접 역은 같은 대여소를 중복 포함할 수 있으므로 역별 자전거 활동을 합산하지 않습니다.",
                "승하차 자료가 포함된 운영기관·연결된 역에 한정되며 도시 전체 철도를 대표하지 않습니다."]}


def load_city(city):
    from backend.services import precomputed, planning, city_anchors, real_data
    data = precomputed.read("transit_linkage", city, START, END)
    boundary, districts = planning.boundaries(city)
    facilities = real_data.read_json(f"planning_facilities_{city}.json", [])
    anchors = [r for r in city_anchors.stops() if r["city"] == city]
    return boundary, data["stations"], facilities, districts, anchors, real_data.aggregated_od(city, START, END)
