"""Reconcile normalized public observations without manufacturing missing fields."""
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"


def rows(name):
    path = PROCESSED / name
    if not path.exists():
        return
    with path.open(encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream)


def validate():
    stations = {}
    inventory = set()
    for row in rows("stations.csv"):
        stations.setdefault(row["region_id"], set()).add(row["station_id"])
        if row["region_id"] == "seoul" and row["latitude"] and row["longitude"]:
            inventory.add(row["station_id"])
    usage = Counter()
    for row in rows("station_usage.csv"):
        usage[(row["region_id"], row["date"])] += int(row["rental_count"])
    od = Counter()
    od_ids = set()
    missing_od_ids = set()
    for row in rows("od_daily.csv"):
        region = row["region_id"]
        od[(region, row["date"])] += int(row["trip_count"])
        for key in ("origin_station_id", "destination_station_id"):
            sid = row[key]
            if region == "seoul":
                od_ids.add(sid)
            if sid not in stations.get(region, set()):
                missing_od_ids.add((region, sid))
    trip_count = Counter()
    bad_time = 0
    negative_duration = 0
    possible_duplicates = 0
    missing_trip_ids = set()
    seen = set()
    for row in rows("trips.csv"):
        region = row["region_id"]
        try:
            start = datetime.fromisoformat(row["started_at"])
            end = datetime.fromisoformat(row["ended_at"])
            if end < start:
                bad_time += 1
        except (ValueError, TypeError):
            bad_time += 1
        try:
            if float(row["duration_minutes"]) < 0:
                negative_duration += 1
        except (ValueError, TypeError):
            negative_duration += 1
        key = tuple(row.values())
        if key in seen:
            possible_duplicates += 1
        else:
            seen.add(key)
        for name in ("origin_station_id", "destination_station_id"):
            if row[name] not in stations.get(region, set()):
                missing_trip_ids.add((region, row[name]))
        trip_count[(region, row["started_at"][:10])] += 1
    dates = sorted({d for _, d in usage} | {d for _, d in od} | {d for _, d in trip_count})
    reconciled = []
    for region in ("seoul", "daejeon"):
        for day in dates:
            if (region, day) not in usage and (region, day) not in od:
                continue
            rental = usage.get((region, day))
            routes = od.get((region, day))
            if rental == 0 and routes is None:
                continue  # Return-only date outside the selected rental days.
            trips = trip_count.get((region, day)) if region == "daejeon" else None
            reconciled.append({"region_id": region, "date": day, "station_rentals": rental,
                               "od_flow": routes, "trip_rows": trips,
                               "rental_vs_od_match": rental == routes})
    result = {
        "seoul": {"od_station_ids": len(od_ids), "inventory_located_ids": len(inventory),
                  "id_matches": len(od_ids & inventory),
                  "id_match_rate": round(len(od_ids & inventory) / len(od_ids), 4) if od_ids else None,
                  "unmatched_id_count": len(od_ids - inventory),
                  "unmatched_ids": sorted(od_ids - inventory),
                  "unmatched_id_sample": sorted(od_ids - inventory)[:30],
                  "coordinate_link_status": "검증되지 않은 ID는 좌표에 연결하지 않음"},
        "daejeon": {"trip_rows": sum(trip_count.values()), "possible_duplicate_rows": possible_duplicates,
                    "invalid_or_reversed_times": bad_time, "negative_or_invalid_durations": negative_duration,
                    "trip_ids_missing_in_normalized_stations": sorted(sid for region, sid in missing_trip_ids if region == "daejeon")[:30],
                    "missing_trip_id_count": len({sid for region, sid in missing_trip_ids if region == "daejeon"})},
        "common": {"od_ids_missing_in_normalized_stations": len(missing_od_ids),
                   "by_date": reconciled, "all_rental_od_totals_match": all(x["rental_vs_od_match"] for x in reconciled)},
    }
    return result


if __name__ == "__main__":
    report = validate()
    target = PROCESSED / "validation_stage3.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
