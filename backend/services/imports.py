"""Validated local CSV import for datasets supplied by a user."""
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from backend.models.normalized import Station, StationUsage, Trip
from backend.services import real_data

UPLOADS = real_data.PROCESSED / "uploads"
FIELDS = {
    "stations": ["region_id", "station_id", "station_name", "latitude", "longitude", "capacity"],
    "station_usage": ["region_id", "station_id", "date", "hour", "rental_count", "return_count"],
    "od_daily": ["region_id", "date", "origin_station_id", "destination_station_id", "trip_count"],
    "trips": ["region_id", "origin_station_id", "destination_station_id", "started_at", "ended_at", "duration_minutes"],
}


async def import_csv(region_id: str, kind: str, file: UploadFile, dataset_name: str):
    if kind not in FIELDS:
        raise HTTPException(400, "kind는 stations, station_usage, od_daily, trips 중 하나여야 합니다.")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "CSV 파일만 업로드할 수 있습니다.")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    incoming = UPLOADS / f".{region_id}-{kind}.upload"
    total = 0
    try:
        with incoming.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > 200 * 1024 * 1024:
                    raise HTTPException(413, "파일은 200 MB 이하여야 합니다.")
                output.write(chunk)
        if not total:
            raise HTTPException(400, "빈 파일입니다.")
        encoding = None
        for candidate in ("utf-8-sig", "cp949"):
            try:
                with incoming.open(encoding=candidate) as source:
                    for _ in iter(lambda: source.read(1024 * 1024), ""):
                        pass
                encoding = candidate
                break
            except UnicodeDecodeError:
                continue
        if encoding is None:
            raise HTTPException(400, "UTF-8 또는 CP949 CSV만 지원합니다.")
        current_ids = {s["station_id"] for s in real_data.snapshot()["stations"] if s["region_id"] == region_id}
        if kind == "stations":
            current_ids = set()
        final = UPLOADS / f"{region_id}-{kind}.csv"
        output_tmp = UPLOADS / f".{region_id}-{kind}.normalized"
        seen_path = UPLOADS / f".{region_id}-{kind}.seen.sqlite"
        seen = sqlite3.connect(seen_path)
        seen.execute("CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY)")
        def check_duplicate(key):
            try:
                seen.execute("INSERT INTO seen(key) VALUES (?)", (repr(key),))
            except sqlite3.IntegrityError as exc:
                raise ValueError("중복 행 또는 대여소 ID") from exc
        count = 0
        period_start = period_end = None
        def track_date(day):
            nonlocal period_start, period_end
            period_start = min(period_start, day) if period_start else day
            period_end = max(period_end, day) if period_end else day
        missing_optional = 0
        usage = defaultdict(lambda: [0, 0])
        od = Counter()
        with incoming.open(encoding=encoding, newline="") as source, output_tmp.open("w", encoding="utf-8", newline="") as output:
            reader = csv.DictReader(source)
            if not set(FIELDS[kind]) <= set(reader.fieldnames or []):
                raise HTTPException(400, f"필수 컬럼: {', '.join(FIELDS[kind])}")
            writer = csv.DictWriter(output, fieldnames=FIELDS[kind])
            writer.writeheader()
            for number, row in enumerate(reader, start=2):
                try:
                    row = {key: (None if value == "" else value) for key, value in row.items()}
                    if kind == "stations":
                        item = Station(**row)
                        missing_optional += int(item.latitude is None) + int(item.longitude is None)
                        if item.latitude is not None and not (33 <= item.latitude <= 39):
                            raise ValueError("위도 범위 오류")
                        if item.longitude is not None and not (124 <= item.longitude <= 132):
                            raise ValueError("경도 범위 오류")
                        key = item.station_id
                        check_duplicate(key)
                    elif kind == "station_usage":
                        item = StationUsage(**row)
                        track_date(item.date.isoformat())
                        missing_optional += int(item.hour is None) + int(item.return_count is None)
                        key = (item.station_id, item.date, item.hour)
                        if item.station_id not in current_ids:
                            raise ValueError("존재하지 않는 대여소 ID")
                        check_duplicate(key)
                    elif kind == "trips":
                        item = Trip(**row)
                        if not item.started_at or not item.origin_station_id or not item.destination_station_id:
                            raise ValueError("Trip은 출발시각·출발/도착 ID가 필요합니다.")
                        if item.origin_station_id not in current_ids or item.destination_station_id not in current_ids:
                            raise ValueError("존재하지 않는 대여소 ID")
                        day, hour = item.started_at.date().isoformat(), item.started_at.hour
                        track_date(day)
                        missing_optional += int(item.ended_at is None) + int(item.duration_minutes is None)
                        usage[(day, hour, item.origin_station_id)][0] += 1
                        usage[(day, hour, item.destination_station_id)][1] += 1
                        od[(day, item.origin_station_id, item.destination_station_id)] += 1
                    else:
                        from datetime import date
                        day = date.fromisoformat(row["date"]).isoformat()
                        track_date(day)
                        count_value = int(row["trip_count"])
                        if count_value < 0:
                            raise ValueError("음수 이동량")
                        if row["origin_station_id"] not in current_ids or row["destination_station_id"] not in current_ids:
                            raise ValueError("존재하지 않는 대여소 ID")
                        if row["region_id"] != region_id:
                            raise ValueError("지역 ID 불일치")
                        key = (day, row["origin_station_id"], row["destination_station_id"])
                        check_duplicate(key)
                        row["date"], row["trip_count"] = day, str(count_value)
                        item = None
                    if kind != "od_daily" and item.region_id != region_id:
                        raise ValueError("지역 ID 불일치")
                    writer.writerow(item.model_dump(mode="json") if kind != "od_daily" else {k: row[k] for k in FIELDS[kind]})
                    count += 1
                except (ValidationError, ValueError, TypeError) as exc:
                    raise HTTPException(400, f"{number}행: {exc}") from exc
        if count == 0:
            raise HTTPException(400, "데이터 행이 없습니다.")
        seen.close()
        output_tmp.replace(final)
        if kind == "trips":
            def write_derived(filename, fields, rows):
                with (UPLOADS / f"{region_id}-{filename}.csv").open("w", encoding="utf-8", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            write_derived("station_usage", FIELDS["station_usage"], (
                {"region_id": region_id, "station_id": sid, "date": day, "hour": hour,
                 "rental_count": values[0], "return_count": values[1]}
                for (day, hour, sid), values in usage.items()))
            write_derived("od_daily", FIELDS["od_daily"], (
                {"region_id": region_id, "date": day, "origin_station_id": origin,
                 "destination_station_id": dest, "trip_count": value}
                for (day, origin, dest), value in od.items()))
        manifest_path = UPLOADS / "sources.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
        source_id = f"upload-{region_id}-{kind}"
        manifest = [s for s in manifest if s["source_id"] != source_id]
        manifest.append({"source_id": source_id, "region_id": region_id, "dataset_name": dataset_name,
                         "source_url": None, "date_start": period_start,
                         "date_end": period_end,
                         "collected_at": datetime.now(timezone.utc).isoformat(), "verification_status": "VERIFIED",
                         "available_columns": FIELDS[kind], "origin": "user_upload",
                         "note": "스키마만 검증했습니다. 공식 출처·라이선스는 제출자가 확인해야 합니다."})
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        quality_path = UPLOADS / "quality.json"
        quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
        quality.setdefault(region_id, {})[kind] = {"rows": count, "invalid_rows": 0,
            "duplicate_rows": 0, "unknown_station_ids": 0,
            "missing_optional_values": missing_optional,
            "period_start": period_start, "period_end": period_end}
        quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
        real_data.snapshot.cache_clear()
        real_data.clusters.cache_clear()
        real_data.network.cache_clear()
        real_data.centrality_result.cache_clear()
        return {"region_id": region_id, "kind": kind, "rows": count, "source_id": source_id,
                "message": "로컬 CSV를 가져왔습니다. 출처와 라이선스는 별도 확인이 필요합니다."}
    finally:
        if "seen" in locals():
            seen.close()
        if "seen_path" in locals():
            seen_path.unlink(missing_ok=True)
        incoming.unlink(missing_ok=True)
        (UPLOADS / f".{region_id}-{kind}.normalized").unlink(missing_ok=True)
