"""WGS84 transit normalization, no implicit coordinate conversion or ID fabrication."""
import argparse
import csv
import io
import json
import math
from pathlib import Path
from scripts.collect.collect_transit_stops import ROOT

FIELDS = ["city", "stop_id", "name", "type", "lat", "lon"]
ALIASES = {
 "stop_id": ["stop_id", "NODE_ID", "nodeid", "고유역번호(외부역코드)", "정류소ID"],
 "name": ["name", "정류소명", "역명", "nodenm"],
 "lat": ["lat", "위도", "Y좌표", "gpslati"],
 "lon": ["lon", "경도", "X좌표", "gpslong"],
}
def read_rows(path):
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True, data_only=True)
        try:
            rows = iter(book.active.values)
            columns = next(rows)
            return [dict(zip(columns, row)) for row in rows]
        finally:
            book.close()
    data = path.read_bytes()
    for enc in ["utf-8-sig", "cp949", "euc-kr"]:
        try:
            return list(csv.DictReader(io.StringIO(data.decode(enc))))
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 인코딩을 확인할 수 없습니다.")

def normalize(rows, city, kind):
    if city not in {"seoul", "daejeon", "sejong"} or kind not in {"버스", "지하철"}:
        raise ValueError("지원하지 않는 도시/수단")
    result, stats, seen = [], {"raw": len(rows), "invalid": 0, "excluded_non_bus": 0, "duplicates": 0}, {}
    for row in rows:
        if kind == "버스" and row.get("정류소타입") == "한강선착장":
            stats["excluded_non_bus"] += 1
            continue
        values = {key: next((row[a] for a in aliases if row.get(a) not in [None, ""]), None)
                  for key, aliases in ALIASES.items()}
        try:
            lat, lon = float(values["lat"]), float(values["lon"])
            if not (math.isfinite(lat) and math.isfinite(lon) and 33 <= lat <= 39 and 124 <= lon <= 132):
                raise ValueError()
            if values["stop_id"] is None or not values["name"]:
                raise ValueError()
        except (TypeError, ValueError):
            stats["invalid"] += 1
            continue
        item = dict(city=city, stop_id=str(values["stop_id"]).strip(), name=str(values["name"]).strip(),
                    type=kind, lat=lat, lon=lon)
        key = (city, kind, item["stop_id"])
        if key in seen:
            if seen[key] != item:
                raise ValueError("동일 정류장 ID의 상충 좌표/이름: " + item["stop_id"])
            stats["duplicates"] += 1
            continue
        seen[key] = item
        result.append(item)
    stats["valid"] = len(result)
    return result, stats

def write_new_csv(path, rows, fields):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    payload = buf.getvalue().encode("utf-8")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"기존 산출물 보존: 새 출력 경로를 선택하세요: {path.name}")
    else:
        with path.open("xb") as out:
            out.write(payload)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", action="append", nargs=3, metavar=("CITY", "TYPE", "FILE"), required=True)
    p.add_argument("--output", default=str(ROOT / "data/processed/transit_stops.csv"))
    args = p.parse_args()
    rows, stats = [], []
    for city, kind, file in args.input:
        items, quality = normalize(read_rows(file), city, kind)
        rows.extend(items)
        stats.append({"city": city, "type": kind, "file": str(file), **quality})
    # Cross-file conflicts must also be rejected.
    unique = {}
    for row in rows:
        key = (row["city"], row["type"], row["stop_id"])
        if key in unique and unique[key] != row:
            raise ValueError("파일 간 동일 ID 상충")
        unique[key] = row
    write_new_csv(args.output, list(unique.values()), FIELDS)
    print(json.dumps(stats, ensure_ascii=False))
