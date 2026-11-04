"""Normalize verified public files. Run: python -m scripts.preprocess.normalize."""
import csv
import json
import logging
import math
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from scripts.collect.common import RAW, ROOT
from scripts.collect.sources import SEOUL, DAEJEON, SEJONG
from backend.models.normalized import DataSource, Station, StationUsage

OUT = ROOT / "data" / "processed"
LOG = logging.getLogger("bike.normalize")


def encoding(path: Path):
    with path.open("rb") as stream:
        sample = stream.read(65536)
    return detect_encoding(sample)


def detect_encoding(sample: bytes):
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for candidate in ("utf-8", "cp949", "euc-kr"):
        try:
            sample.decode(candidate)
            return candidate
        except UnicodeDecodeError:
            pass
    raise ValueError("인코딩 확인 실패")


def write_csv(name, fields, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def station_inventory(path, stations, issues):
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        for row in book.active.iter_rows(min_row=6, values_only=True):
            number, name = row[0], row[1]
            if number is None or name is None:
                continue
            try:
                lat, lon = float(row[4]), float(row[5])
                if not 33 <= lat <= 39 or not 124 <= lon <= 132:
                    raise ValueError()
            except (TypeError, ValueError):
                lat = lon = None
                issues["invalid_coordinates"] += 1
            capacity = sum(int(value) for value in (row[7], row[8]) if isinstance(value, (int, float)))
            key = "N-" + str(int(number)) if isinstance(number, (int, float)) else "N-" + str(number).strip()
            if ("seoul", key) in stations:
                issues["duplicate_stations"] += 1
            stations[("seoul", key)] = Station(region_id="seoul", station_id=key, station_name=str(name).strip(),
                                                latitude=lat, longitude=lon, capacity=capacity or None).model_dump()
    finally:
        book.close()


def daejeon_inventory(path, stations, issues):
    enc = encoding(path)
    with path.open(encoding=enc, newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"번호", "대여소명", "주소"} <= set(reader.fieldnames or []):
            raise ValueError("대전 대여소 컬럼이 예상과 다릅니다.")
        for row in reader:
            key = (row.get("번호") or "").strip()
            if not key:
                issues["missing_station_id"] += 1
                continue
            if ("daejeon", key) in stations:
                issues["duplicate_stations"] += 1
                continue
            stations[("daejeon", key)] = Station(region_id="daejeon", station_id=key,
                station_name=(row.get("대여소명") or "").strip() or None).model_dump()
    return enc


def sejong_yearly(path, issues):
    result = []
    with path.open(encoding=encoding(path), newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"구분", "어울링 이용건수"} <= set(reader.fieldnames or []):
            raise ValueError("세종 연도별 컬럼이 예상과 다릅니다.")
        for row in reader:
            if not (row.get("구분") or "").strip():
                continue
            try:
                period = row["구분"].strip()
                year, count = int(period[:4]), int(row["어울링 이용건수"])
                if count < 0 or year < 2000 or year > 2100:
                    raise ValueError()
            except ValueError:
                issues["invalid_yearly_count"] += 1
                continue
            complete = len(period) == 4
            result.append({"region_id": "sejong", "year": year, "period_end": f"{year}-12-31" if complete else period,
                           "complete_year": complete, "rental_count": count})
    return result


def daejeon_trips(path, stations, usage, od, issues):
    """Stream the October member and retain only days shared with Seoul."""
    selected_days = {"2026-10-25", "2026-10-29"}
    trip_count = 0
    fields = ["region_id", "origin_station_id", "destination_station_id",
              "started_at", "ended_at", "duration_minutes"]
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "trips.csv").open("w", encoding="utf-8", newline="") as target, zipfile.ZipFile(path) as archive:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        names = [name for name in archive.namelist() if "26년10월" in name and name.endswith(".csv")]
        if len(names) != 1:
            raise ValueError("대전 ZIP에서 2026년 10월 CSV를 찾지 못했습니다.")
        with archive.open(names[0]) as probe:
            enc = detect_encoding(probe.read(65536))
        with archive.open(names[0]) as stream:
            for chunk in pd.read_csv(stream, encoding=enc, dtype=str, chunksize=50000):
                required = {"대여일시", "대여_대여소ID", "대여_대여소명", "대여_X좌표", "대여_Y좌표",
                            "반납일시", "반납_대여소ID", "반납_대여소명", "반납_X좌표", "반납_Y좌표", "이용시간(분)"}
                if not required <= set(chunk.columns):
                    raise ValueError("대전 Trip 컬럼이 예상과 다릅니다.")
                chosen = chunk[chunk["대여일시"].str.slice(0, 10).isin(selected_days)]
                for row in chosen.itertuples(index=False, name=None):
                    values = dict(zip(chunk.columns, row))
                    try:
                        started = datetime.fromisoformat(str(values["대여일시"]))
                        ended = datetime.fromisoformat(str(values["반납일시"])) if pd.notna(values["반납일시"]) else None
                        duration = float(values["이용시간(분)"]) if pd.notna(values["이용시간(분)"]) else None
                        if duration is not None and duration < 0:
                            issues["daejeon_negative_duration"] += 1
                            continue
                        if ended and ended < started:
                            issues["daejeon_invalid_trip_time"] += 1
                            continue
                    except (ValueError, TypeError):
                        issues["daejeon_invalid_trip_time"] += 1
                        continue
                    origin, dest = str(values["대여_대여소ID"]).strip(), str(values["반납_대여소ID"]).strip()
                    if not origin or not dest or origin.lower() == "nan" or dest.lower() == "nan":
                        issues["daejeon_missing_station_id"] += 1
                        continue
                    labels = (str(values["대여_대여소명"]), str(values["반납_대여소명"]))
                    if any("타슈관제센터" in label for label in labels):
                        issues["daejeon_admin_return_excluded"] += 1
                        continue
                    for sid, label, x, y in (
                        (origin, labels[0], values["대여_X좌표"], values["대여_Y좌표"]),
                        (dest, labels[1], values["반납_X좌표"], values["반납_Y좌표"])):
                        key = ("daejeon", sid)
                        if key not in stations:
                            issues["daejeon_ids_missing_in_inventory"] += 1
                            stations[key] = Station(region_id="daejeon", station_id=sid,
                                station_name=label if label != "nan" else None).model_dump()
                        try:
                            lat, lon = float(x), float(y)
                            if not (33 <= lat <= 39 and 124 <= lon <= 132):
                                raise ValueError()
                            if stations[key]["latitude"] is None:
                                stations[key]["latitude"], stations[key]["longitude"] = lat, lon
                        except (TypeError, ValueError):
                            issues["daejeon_invalid_coordinates"] += 1
                    day, hour = started.date().isoformat(), started.hour
                    usage[("daejeon", day, hour, origin)][0] += 1
                    if ended:
                        usage[("daejeon", ended.date().isoformat(), ended.hour, dest)][1] += 1
                    od[("daejeon", day, origin, dest)] += 1
                    writer.writerow({"region_id": "daejeon", "origin_station_id": origin,
                        "destination_station_id": dest, "started_at": started.isoformat(),
                        "ended_at": ended.isoformat() if ended else None, "duration_minutes": duration})
                    trip_count += 1
    return trip_count


def seoul_od(path, stations, usage, od, issues):
    seen_rows = set()
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError("서울 OD ZIP에 CSV 하나가 있어야 합니다.")
        with archive.open(names[0]) as probe:
            enc = detect_encoding(probe.read(65536))
        with archive.open(names[0]) as stream:
            for chunk in pd.read_csv(stream, encoding=enc, dtype=str, chunksize=50000):
                required = {"기준_날짜", "집계_기준", "기준_시간대", "시작_대여소_ID",
                            "시작_대여소명", "종료_대여소_ID", "종료_대여소명", "전체_건수"}
                if not required <= set(chunk.columns):
                    raise ValueError("서울 OD 컬럼이 예상과 다릅니다.")
                # The source includes departure-time and arrival-time views of the same trips.
                for row in chunk.itertuples(index=False, name=None):
                    values = dict(zip(chunk.columns, row))
                    if values["집계_기준"] != "출발시간":
                        continue
                    raw_key = tuple(values.get(key) for key in
                        ("기준_날짜", "집계_기준", "기준_시간대", "시작_대여소_ID", "종료_대여소_ID"))
                    if raw_key in seen_rows:
                        issues["duplicate_od_rows"] += 1
                    seen_rows.add(raw_key)
                    raw_date = str(values["기준_날짜"])
                    try:
                        day = datetime.strptime(raw_date, "%Y%m%d").date().isoformat()
                        hour = int(str(values["기준_시간대"])[:2])
                        count = int(values["전체_건수"])
                        if hour not in range(24):
                            raise ValueError()
                        if count < 0:
                            issues["negative_usage_rows"] += 1
                            continue
                    except (ValueError, TypeError):
                        issues["invalid_usage_rows"] += 1
                        continue
                    origin, dest = str(values["시작_대여소_ID"]).strip(), str(values["종료_대여소_ID"]).strip()
                    if not origin or not dest or origin.lower() == "nan" or dest.lower() == "nan":
                        issues["missing_station_id"] += 1
                        continue
                    for station_id, label in ((origin, values["시작_대여소명"]), (dest, values["종료_대여소명"])):
                        key = ("seoul", station_id)
                        if key not in stations:
                            stations[key] = Station(region_id="seoul", station_id=station_id,
                                station_name=str(label).strip() if pd.notna(label) else None).model_dump()
                    usage[("seoul", day, hour, origin)][0] += count
                    usage[("seoul", day, hour, dest)][1] += count
                    od[("seoul", day, origin, dest)] += count
    return names[0]


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    stations, usage, od = {}, defaultdict(lambda: [0, 0]), Counter()
    issues = Counter()
    daejeon_trip_count = 0
    files = {s["source_id"]: RAW / s["filename"] for s in SEOUL + DAEJEON + SEJONG}
    manifest_file = RAW / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
    sources = []
    for source in SEOUL + DAEJEON + SEJONG:
        path = files[source["source_id"]]
        if not path.exists():
            status, columns, collected = "METADATA_ONLY", [], None
        else:
            status = "VERIFIED"
            collected = manifest.get(path.name, {}).get("collected_at")
            if source["source_id"] == "seoul-stations-202606":
                station_inventory(path, stations, issues)
                columns = ["대여소 번호", "보관소(대여소)명", "소재지(위치)", "위도", "경도", "설치 시기", "LCD 거치대수", "QR 거치대수", "운영 방식"]
            elif source["source_id"].startswith("seoul-od-"):
                seoul_od(path, stations, usage, od, issues)
                columns = ["기준_날짜", "집계_기준", "기준_시간대", "시작_대여소_ID", "시작_대여소명", "종료_대여소_ID", "종료_대여소명", "전체_건수", "전체_이용_분", "전체_이용_거리"]
            elif source["source_id"] == "daejeon-trips-20261102":
                daejeon_trip_count = daejeon_trips(path, stations, usage, od, issues)
                columns = ["자전거번호", "대여일시", "대여_대여소ID", "대여_대여소명", "대여_X좌표", "대여_Y좌표", "대여_구", "대여_동", "대여_대여소주소", "반납일시", "반납_대여소ID", "반납_대여소명", "반납_X좌표", "반납_Y좌표", "반납_구", "반납_동", "반납_대여소주소", "이용시간(분)", "이용거리(km)"]
            elif source["region_id"] == "daejeon":
                daejeon_inventory(path, stations, issues)
                columns = ["번호", "대여소명", "소재지", "행정동", "주소"]
            else:
                columns = ["구분", "어울링 이용건수"]
        day = source["source_id"][-8:] if source["source_id"].startswith("seoul-od-") else None
        day = f"{day[:4]}-{day[4:6]}-{day[6:]}" if day else None
        if source["source_id"] == "daejeon-stations-20260624":
            day = "2026-06-24"
        if source["source_id"] == "daejeon-trips-20261102":
            day = None
        if source["source_id"] == "seoul-stations-202606":
            day = "2026-06-30"  # Month-end marker for the source's June 2026 snapshot.
        sources.append(DataSource(source_id=source["source_id"], region_id=source["region_id"],
            dataset_name=source["dataset_name"], source_url=source["source_url"],
            date_start=day, date_end=day, collected_at=collected,
            verification_status=status, available_columns=columns).model_dump(mode="json"))
        if source["source_id"] == "daejeon-trips-20261102" and status == "VERIFIED":
            sources[-1]["date_start"], sources[-1]["date_end"] = "2025-12-01", "2026-10-31"
    yearly = sejong_yearly(files["sejong-yearly-20260831"], issues) if files["sejong-yearly-20260831"].exists() else []
    # Attach genuine collection period to the yearly source without guessing partial-year coverage.
    for item in sources:
        if item["source_id"] == "sejong-yearly-20260831" and yearly:
            item["date_start"] = f"{min(x['year'] for x in yearly)}-01-01"
            item["date_end"] = max(x["period_end"] for x in yearly)
    sources.append(DataSource(source_id="busan-services", region_id="busan",
        dataset_name="부산 자전거 대여소 운영현황", source_url="https://www.busan.go.kr/depart/ahbicycle04",
        verification_status="METADATA_ONLY").model_dump(mode="json"))
    sources.append(DataSource(source_id="busan-usage", region_id="busan",
        dataset_name="부산 통합 이용·OD 원본", verification_status="UNAVAILABLE").model_dump(mode="json"))
    sources.append(DataSource(source_id="sejong-stations-metadata", region_id="sejong",
        dataset_name="세담터 어울링 수집 대여소정보",
        source_url="https://www2.sejong.go.kr/bigdata/main.do",
        verification_status="METADATA_ONLY").model_dump(mode="json"))
    for region, source_id, name, url in (
        ("daejeon", "daejeon-portal-api", "타슈 위치 현황 자동변환 OpenAPI",
         "https://www.data.go.kr/data/15062798/fileData.do"),
        ("sejong", "sejong-portal-api", "어울링 연도별 이용건수 자동변환 OpenAPI",
         "https://www.data.go.kr/data/15134188/fileData.do"),
    ):
        sources.append(DataSource(source_id=source_id, region_id=region, dataset_name=name,
            source_url=url, verification_status="ACCESS_REQUIRED").model_dump(mode="json"))
    station_rows = list(stations.values())
    usage_rows = [StationUsage(region_id=region, station_id=station, date=day, hour=hour,
        rental_count=counts[0], return_count=counts[1]).model_dump(mode="json")
        for (region, day, hour, station), counts in sorted(usage.items())]
    od_rows = [{"region_id": region, "date": day, "origin_station_id": origin,
                "destination_station_id": dest, "trip_count": count}
               for (region, day, origin, dest), count in sorted(od.items())]
    station_keys = set(stations)
    inventory_ids = {sid for (region, sid), value in stations.items() if region == "seoul" and value["latitude"] is not None}
    od_ids = {sid for row in od_rows if row["region_id"] == "seoul" for sid in (row["origin_station_id"], row["destination_station_id"])}
    unknown_usage_ids = sum((row["region_id"], row["station_id"]) not in station_keys for row in usage_rows)
    unknown_od_ids = sum((row["region_id"], row["origin_station_id"]) not in station_keys or
                         (row["region_id"], row["destination_station_id"]) not in station_keys for row in od_rows)
    write_csv("stations.csv", ["region_id", "station_id", "station_name", "latitude", "longitude", "capacity"], station_rows)
    write_csv("station_usage.csv", ["region_id", "station_id", "date", "hour", "rental_count", "return_count"], usage_rows)
    write_csv("od_daily.csv", ["region_id", "date", "origin_station_id", "destination_station_id", "trip_count"], od_rows)
    write_csv("yearly.csv", ["region_id", "year", "period_end", "complete_year", "rental_count"], yearly)
    (OUT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    days = sorted({row["date"] for row in usage_rows if row["region_id"] == "seoul"})
    daejeon_days = sorted({row["date"] for row in usage_rows if row["region_id"] == "daejeon" and row["rental_count"] > 0})
    quality = {
        "seoul": {"issues": {k:v for k,v in issues.items() if not k.startswith("daejeon_")},
                  "station_count": sum(x["region_id"] == "seoul" for x in station_rows),
                  "usage_rows": sum(x["region_id"] == "seoul" for x in usage_rows),
                  "od_rows": sum(x["region_id"] == "seoul" for x in od_rows),
                  "unknown_usage_station_ids": unknown_usage_ids, "unknown_od_station_ids": unknown_od_ids,
                  "od_ids_without_inventory_match": len(od_ids - inventory_ids),
                  "missing_coordinate_ratio": round(sum(x["region_id"] == "seoul" and x["latitude"] is None for x in station_rows) /
                        max(1, sum(x["region_id"] == "seoul" for x in station_rows)), 4),
                  "missing_station_name_ratio": round(sum(x["region_id"] == "seoul" and not x["station_name"] for x in station_rows) /
                        max(1, sum(x["region_id"] == "seoul" for x in station_rows)), 4),
                  "period_start": days[0] if days else None, "period_end": days[-1] if days else None,
                  "observed_dates": days, "coverage_note": "선택된 2일의 OD 집계만 포함. 연속 기간이 아님."},
        "daejeon": {"issues": {k:v for k,v in issues.items() if k.startswith("daejeon_")},
                    "station_count": sum(x["region_id"] == "daejeon" for x in station_rows),
                    "trip_rows": daejeon_trip_count,
                    "usage_rows": sum(x["region_id"] == "daejeon" for x in usage_rows),
                    "od_rows": sum(x["region_id"] == "daejeon" for x in od_rows),
                    "missing_coordinates": sum(x["region_id"] == "daejeon" and x["latitude"] is None for x in station_rows),
                    "missing_coordinate_ratio": round(sum(x["region_id"] == "daejeon" and x["latitude"] is None for x in station_rows) /
                        max(1, sum(x["region_id"] == "daejeon" for x in station_rows)), 4),
                    "missing_station_name_ratio": round(sum(x["region_id"] == "daejeon" and not x["station_name"] for x in station_rows) /
                        max(1, sum(x["region_id"] == "daejeon" for x in station_rows)), 4),
                    "period_start": daejeon_days[0] if daejeon_days else None,
                    "period_end": daejeon_days[-1] if daejeon_days else None,
                    "observed_dates": daejeon_days,
                    "coverage_note": "대전 ZIP의 2026년 10월 기록 중 서울과 공통인 2일만 처리."},
        "sejong": {"yearly_rows": len(yearly), "station_count": 0, "usage_rows": 0,
                    "period_start": f"{min(x['year'] for x in yearly)}-01-01" if yearly else None,
                    "period_end": max(x["period_end"] for x in yearly) if yearly else None},
        "busan": {"station_count": 0, "usage_rows": 0, "period_start": None, "period_end": None}
    }
    (OUT / "quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("stations=%s usage=%s od=%s trips=%s yearly=%s", len(station_rows), len(usage_rows), len(od_rows), daejeon_trip_count, len(yearly))
    return quality


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(json.dumps(run(), ensure_ascii=False, indent=2))
