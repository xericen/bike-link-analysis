"""Transit enrichment is separate from immutable original station master."""
import csv
from backend.services import real_data
from backend.analysis.transit import match_stations

def stops():
    path = real_data.PROCESSED / "transit_stops.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def linkage(city, date_start=None, date_end=None):
    selected = [s for s in stops() if s["city"] == city]
    metadata = {"city": city, "date_start": date_start, "date_end": date_end,
                "distance_unit": "m", "radius_m": [300, 500], "available": bool(selected),
                "source_document": "docs/TRANSIT_LINKAGE.md",
                "sources": [{"dataset_name": "서울시 버스정류소 위치정보", "verification_status": "VERIFIED", "source_url": "https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do", "reference_date": "2026-09-02"},
                            {"dataset_name": "서울교통공사 1~8호선 역사 좌표", "verification_status": "VERIFIED", "source_url": "https://data.seoul.go.kr/dataList/OA-22534/F/1/datasetView.do", "reference_date": "2025-08-14"}] if city == "seoul" else [],
                "limitations": ["직선거리이며 보행 경로·출입구 접근성과 다릅니다.",
                 "서울 지하철 자료는 서울교통공사 1~8호선 276행으로 전체 수도권 철도망이 아닙니다. 좌표 기준일과 OD 관측 기간이 다릅니다.",
                 "역 연계 비율은 공간적 근접 이동 비중이며 실제 환승률이 아닙니다.",
                 "자료가 없는 수단의 수치와 역 연계 비율은 null입니다."]}
    if not selected:
        return {**metadata, "stations": [], "hourly_station_linkage": None,
                "message": "정류장 위치 자료 미확보: 공식 CSV 가져오기 또는 API 키 설정 필요"}
    stations = match_stations(real_data.region_stations(city, date_start, date_end), selected)
    hourly, selected_dates = {}, []
    path = real_data.PROCESSED / f"transit_hourly_{city}_verified.csv"
    if path.exists() and any(s["type"] == "지하철" for s in selected):
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if date_start and row["date"] < date_start or date_end and row["date"] > date_end:
                    continue
                selected_dates.append(row["date"])
                h = int(row["hour"])
                item = hourly.setdefault(h, {"hour": h, "total_count": 0, "linked_count": 0, "unknown_endpoint_count": 0})
                for key in ["total_count", "linked_count", "unknown_endpoint_count"]:
                    item[key] += int(row[key])
    for item in hourly.values():
        item["linkage_share"] = item["linked_count"] / item["total_count"] if item["total_count"] else None
    return {**metadata, "stop_count": len(selected), "stop_types": sorted({s["type"] for s in selected}),
            "stations": stations, "hourly_station_linkage": list(sorted(hourly.values(), key=lambda x:x["hour"])) or None,
            "hourly_period_start": min(selected_dates) if selected_dates else None,
            "hourly_period_end": max(selected_dates) if selected_dates else None}
