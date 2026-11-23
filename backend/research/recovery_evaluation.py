"""Offline June development / July locked evaluation; never alters production scores."""
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point
from backend.research import method_validation as m
from backend.research.validation_followup import eligible_targets
from backend.analysis.transit import match_stations

PERIODS = {"development": ("2025-06-01", "2025-06-30"),
           "evaluation": ("2025-07-01", "2025-07-31")}
STEPS = (500, 250)
POLICIES = ("equal", "demand", "gap", "facilities_only")
SEEDS = {"development": 137, "evaluation": 233}
OUTPUT = m.ROOT / "docs/recovery-evaluation-20261123"

def load(city, start, end):
    """Read-only SQLite and fixed spatial references; no global service path mutation."""
    from backend.services import planning, real_data
    folder = m.ROOT / "data/individual" / city
    with (folder / "stations.csv").open() as stream:
        stations = list(csv.DictReader(stream))
    for s in stations:
        for k in ("latitude", "longitude"):
            s[k] = float(s[k]) if s[k] else None
    with (folder / "transit_anchors.csv").open() as stream:
        anchors = [r for r in csv.DictReader(stream) if r["city"] == city]
    stations = match_stations(stations, anchors)
    for s in stations:
        s["nearest_anchor_distance_m"] = s["nearest_stop_distance_m"]
    with sqlite3.connect("file:" + str(folder / "analysis.sqlite") + "?mode=ro", uri=True) as connection:
        counts = connection.execute(
            "SELECT date,SUM(trip_count) FROM od_daily WHERE region_id=? AND date BETWEEN ? AND ? GROUP BY date",
            (city, start, end)).fetchall()
        rows = connection.execute(
            "SELECT origin_station_id,destination_station_id,SUM(trip_count) FROM od_daily "
            "WHERE region_id=? AND date BETWEEN ? AND ? GROUP BY origin_station_id,destination_station_id",
            (city, start, end)).fetchall()
    od = [{"origin_station_id": o, "destination_station_id": d, "trip_count": int(n)} for o,d,n in rows]
    stations, audit = m.retain_training(stations, od, [])
    boundary, districts = planning.boundaries(city)
    facilities = real_data.read_json("planning_facilities_" + city + ".json", [])
    known = {s["station_id"] for s in stations if s["coordinate_valid"]}
    summary = {"city": city, "start": start, "end": end, "observed_days": len(counts),
               "trips": sum(int(n) for _, n in counts), "daily_trips": dict(counts),
               "located_stations": len(known),
               "trips_with_unknown_endpoint": sum(r["trip_count"] for r in od if r["origin_station_id"] not in known or r["destination_station_id"] not in known),
               "historical_coordinates_verified": False}
    return boundary, stations, facilities, districts, anchors, od, summary

def block_id(s):
    x, y = m.PROJECT(s["longitude"], s["latitude"])
    return int(x // 1000), int(y // 1000)

def folds(stations, boundary, stage, excluded_ids=(), excluded_block=None):
    cohort, eligibility = eligible_targets(stations, boundary)
    cohort = [s for s in cohort if s["station_id"] not in set(excluded_ids)]
    n = min(10, len(cohort))
    result = []
    if n:
        result.append({"name": "gap_high_usage", "targets": cohort[:n],
                       "hidden_ids": [s["station_id"] for s in cohort[:n]]})
        ix = np.random.default_rng(SEEDS[stage]).choice(len(cohort), n, replace=False)
        targets = [cohort[int(i)] for i in ix]
        result.append({"name": "gap_random", "targets": targets,
                       "hidden_ids": [s["station_id"] for s in targets]})
    groups = {}
    for s in stations:
        if s.get("coordinate_valid") and boundary.covers(Point(*m.PROJECT(s["longitude"], s["latitude"]))):
            groups.setdefault(block_id(s), []).append(s)
    eligible_blocks = []
    for key, group in groups.items():
        active = [s for s in group if s["rental_count"] > 0]
        if not active or any(s["station_id"] in excluded_ids for s in active):
            continue
        if excluded_block and math.dist(key, excluded_block) < 2:
            continue
        eligible_blocks.append((key, group, active))
    if eligible_blocks:
        key, group, targets = sorted(eligible_blocks, key=lambda v: (-len(v[2]), v[0]))[0]
        result.append({"name": "spatial_block", "block": key, "targets": targets,
                       "hidden_ids": [s["station_id"] for s in group]})
    return result, eligibility

def ranked(rows, policy, city):
    if policy == "facilities_only":
        keys = ["facilities_within_500m"] + ([] if city == "sejong" else ["population_density_km2"])
        return sorted(rows, key=lambda r: (-sum(r["score_components"][k] for k in keys)/len(keys), r["site_id"]))
    if policy == "demand":
        return sorted(rows, key=lambda r: (-r["nearby_rentals_1000m"], r["site_id"]))
    return m.rank_candidates(rows, policy, city != "sejong")[0]

def diagnose(targets, candidates, training, radius=300):
    """Exact loss stage and nearest candidate distance; not a causal attribution."""
    if candidates:
        points = np.array([m.PROJECT(r["longitude"], r["latitude"]) for r in candidates])
        tree = cKDTree(points)
    else:
        tree = None
    located = [s for s in training if s.get("coordinate_valid")]
    station_tree = cKDTree([m.PROJECT(s["longitude"], s["latitude"]) for s in located]) if located else None
    result = []
    for s in targets:
        point = m.PROJECT(s["longitude"], s["latitude"])
        distance = float(tree.query(point)[0]) if tree else None
        near = tree.query_ball_point(point, radius) if tree else []
        best_rank = min((i + 1 for i in near), default=None)
        result.append({"station_id": s["station_id"], "station_name": s.get("station_name"),
                       "observed_rentals": s["rental_count"],
                       "nearest_candidate_m": distance, "best_individual_rank_within_300m": best_rank,
                       "nearest_remaining_station_projected_m": float(station_tree.query(point)[0]) if station_tree else None,
                       "stage": "no_candidate" if not near else "top10_nearby" if best_rank <= 10 else "rank_below_top10"})
    return result

def metrics(targets, proposals):
    results = {str(k): m.geographic_matches(targets, proposals[:k]) for k in (10, 20)}
    errors = [r["distance_m"] for r in results["10"]["pairs"]]
    return {"at_k": results, "mean_matched_distance_m": float(np.mean(errors)) if errors else None,
            "precision_at10": results["10"]["hits"] / min(10, len(proposals)) if proposals else None,
            "maximum_possible_recall_at10": min(10, len(targets)) / len(targets) if targets else None}

def evaluate_fold(city, inputs, fold):
    boundary, stations, facilities, districts, anchors, od, summary = inputs
    training, audit = m.retain_training(stations, od, fold["hidden_ids"])
    baseline = m.baseline_geometry(anchors, boundary, 500)
    result = {"name": fold["name"], "block": fold.get("block"), "target_count": len(fold["targets"]),
              "target_ids": [s["station_id"] for s in fold["targets"]], "training_audit": audit,
              "configs": {}}
    for step in STEPS:
        pool, _ = m.grid_candidates(boundary, baseline, training, facilities, districts,
                                    step=step, use_population=city != "sejong")
        random = []
        rng = np.random.default_rng(711)
        for _ in range(30):
            proposals = [pool[int(i)] for i in rng.choice(len(pool), min(10, len(pool)), replace=False)] if pool else []
            random.append(m.geographic_matches(fold["targets"], proposals)["recall"])
        for policy in POLICIES:
            proposals = ranked(pool, policy, city)
            diagnostic = diagnose(fold["targets"], proposals, training)
            counts = Counter(r["stage"] for r in diagnostic)
            possible = sum(r["stage"] != "no_candidate" for r in diagnostic)
            value = metrics(fold["targets"], proposals)
            value.update(candidate_count=len(pool), target_diagnostics=diagnostic, loss_counts=dict(counts),
                         generation_possible=possible, random_recall_mean=float(np.mean(random)),
                         random_recall_std=float(np.std(random)),
                         conditional_recall_at10=value["at_k"]["10"]["hits"] / possible if possible else None)
            result["configs"][f"{step}:{policy}"] = value
    return result

def select_config(fold_results):
    """Development only. Deterministic ties prefer baseline grid and equal policy."""
    keys = [f"{step}:{p}" for step in STEPS for p in POLICIES]
    scores = {k: float(np.mean([f["configs"][k]["at_k"]["10"]["recall"] for f in fold_results]))
              for k in keys} if fold_results else {}
    return max(keys, key=lambda k: scores.get(k, -1)), scores

def summary(fold_results, config):
    rows = []
    for f in fold_results:
        v = f["configs"][config]
        rows.append({"fold": f["name"], "n": f["target_count"], "candidate_count": v["candidate_count"],
                     "possible": v["generation_possible"], "hits10": v["at_k"]["10"]["hits"],
                     "recall10": v["at_k"]["10"]["recall"], "hits20": v["at_k"]["20"]["hits"],
                     "recall20": v["at_k"]["20"]["recall"], "random_recall": v["random_recall_mean"],
                     "loss_counts": v["loss_counts"], "matched_error_m": v["mean_matched_distance_m"]})
    return rows

def existing_diagnostics():
    original = json.loads(m.FILE.read_text())
    return {city: [{"fold": r["fold"], "seed": r["seed"], "n": r["target_count"],
                    "no_candidate": r["target_count"] - r["feasible_within_match_radius_count"],
                    "possible_not_matched_top10": r["feasible_within_match_radius_count"] - r["methods"]["full"]["hits"],
                    "hits10": r["methods"]["full"]["hits"]} for r in value["backtest"]]
            for city, value in original["cities"].items()}
