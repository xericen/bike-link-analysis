"""Use Seoul's official OA-21235 station master to verify OD station coordinates."""
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
DATA_VIEW = "https://data.seoul.go.kr/dataList/dataView.do"
SOURCE_URL = "https://data.seoul.go.kr/dataList/OA-21235/S/1/datasetView.do"
FIELDS = ("RNTLS_ID", "ADDR1", "ADDR2", "LAT", "LOT")


def parse_page(body):
    # The official sheet endpoint returns JavaScript object notation, not valid JSON.
    records = []
    for chunk in re.findall(r"\{([^{}]*RNTLS_ID:[^{}]*)\}", body):
        item = {}
        for key in FIELDS:
            match = re.search(r'(?:^|,)' + key + r':"((?:\\.|[^"\\])*)"', chunk)
            item[key] = match.group(1).replace('\\"', '"') if match else ""
        if item["RNTLS_ID"]:
            records.append(item)
    total = re.search(r"totalCount:\s*(\d+)", body)
    if not total:
        raise ValueError("공식 마스터 응답에서 전체 건수를 확인하지 못했습니다.")
    return records, int(total.group(1))


def fetch_master():
    rows = []
    with httpx.Client(timeout=25, follow_redirects=True) as client:
        for page in range(1, 100):
            response = client.get(DATA_VIEW, params={
                "onepagerow": 100, "srvType": "S", "infId": "OA-21235", "serviceKind": "0",
                "pageNo": page, "ssUserId": "SAMPLE_VIEW", "strWhere": "",
                "strOrderby": "RNTLS_ID DESC", "filterCol": "필터선택", "txtFilter": "",
            })
            response.raise_for_status()
            current, total = parse_page(response.text)
            rows.extend(current)
            if len(rows) >= total:
                break
            if not current:
                raise ValueError("공식 마스터의 페이지가 비어 있습니다.")
    if len(rows) != total:
        raise ValueError(f"마스터 행 수 불일치: {len(rows)} / {total}")
    return rows


def match_master(master, processed):
    od_path = processed / "od_daily.csv"
    station_path = processed / "stations.csv"
    with od_path.open(encoding="utf-8", newline="") as stream:
        od = list(csv.DictReader(stream))
    with station_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        columns, stations = reader.fieldnames, list(reader)
    ids = {row[key] for row in od if row["region_id"] == "seoul"
           for key in ("origin_station_id", "destination_station_id")}
    counts = Counter(row["RNTLS_ID"] for row in master)
    master_by_id = {row["RNTLS_ID"]: row for row in master if counts[row["RNTLS_ID"]] == 1}
    matched, invalid, name_missing = set(), [], []
    station_by_id = {row["station_id"]: row for row in stations if row["region_id"] == "seoul"}
    for sid in sorted(ids):
        row = master_by_id.get(sid)
        if not row:
            continue
        try:
            lat, lon = float(row["LAT"]), float(row["LOT"])
        except (ValueError, TypeError):
            invalid.append(sid)
            continue
        if not (37.0 <= lat <= 38.0 and 126.0 <= lon <= 128.0):
            invalid.append(sid)
            continue
        name = row["ADDR2"].strip() or row["ADDR1"].strip()
        if not name:
            name_missing.append(sid)
            continue
        item = station_by_id.get(sid)
        if item is None:
            item = {"region_id": "seoul", "station_id": sid, "station_name": "",
                    "latitude": "", "longitude": "", "capacity": ""}
            stations.append(item)
        item.update({"station_name": name, "latitude": str(lat), "longitude": str(lon)})
        matched.add(sid)
    with station_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(stations)
    result = {"source_url": SOURCE_URL, "sheet_endpoint": DATA_VIEW, "master_rows": len(master),
              "master_unique_ids": len(master_by_id), "master_duplicate_ids": sorted(k for k, v in counts.items() if v > 1),
              "od_station_ids": len(ids), "matched_with_valid_coordinates": len(matched),
              "match_rate": round(len(matched) / len(ids), 4) if ids else None,
              "unmatched_ids": sorted(ids - matched), "invalid_coordinate_ids": invalid,
              "missing_name_ids": name_missing, "checked_at": datetime.now(timezone.utc).isoformat()}
    (processed / "seoul_station_mapping.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    quality_path = processed / "quality.json"
    if quality_path.exists():
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        quality.setdefault("seoul", {}).update({
            "od_station_ids": len(ids),
            "station_id_matches": len(matched),
            "station_id_match_rate": result["match_rate"],
            "unmatched_station_ids": result["unmatched_ids"],
            "station_master_rows": len(master),
            "station_count": len(ids),
            "inventory_station_count": len(master_by_id),
            "od_ids_without_inventory_match": len(ids - matched),
            "missing_coordinate_ratio": round(len(ids - matched) / len(ids), 4) if ids else None,
        })
        quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    source_path = processed / "sources.json"
    sources = json.loads(source_path.read_text(encoding="utf-8"))
    existing = next((s for s in sources if s["source_id"] == "seoul-station-master-oa-21235"), None)
    if existing:
        existing.update({"collected_at": result["checked_at"],
                         "note": "OD ST ID와 직접 매칭한 유효 좌표만 반영. OA-21235는 2026-11-16 종료 예정"})
        source_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        sources.append({"source_id": "seoul-station-master-oa-21235", "region_id": "seoul",
                        "dataset_name": "서울시 따릉이대여소 마스터 정보", "source_url": SOURCE_URL,
                        "date_start": None, "date_end": None, "collected_at": result["checked_at"],
                        "verification_status": "VERIFIED", "available_columns": list(FIELDS),
                        "origin": "official_sheet", "note": "OD ST ID와 직접 매칭한 유효 좌표만 반영. OA-21235는 2026-11-16 종료 예정"})
        source_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    result = match_master(fetch_master(), ROOT / "data" / "processed")
    print(json.dumps({k: v for k, v in result.items() if k not in {"unmatched_ids", "invalid_coordinate_ids", "missing_name_ids", "master_duplicate_ids"}}, ensure_ascii=False))
