"""Build a reproducible December-2025 transit/bike demand comparison.

The rail uploads contain monthly station totals, not hourly records or observed
transfers. Annual bus-stop averages are audited separately and never mixed into
the December comparison or planning score.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PERIOD_START = "2025-12-01"
PERIOD_END = "2025-12-31"


def nfc(value: object) -> str:
    return unicodedata.normalize("NFC", str(value))


def station_key(value: object) -> str:
    text = re.sub(r"\s+", "", nfc(value).strip())
    text = re.sub(r"\([^)]*\)$", "", text)
    return re.sub(r"역$", "", text)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_file(folder: Path, includes: tuple[str, ...], suffix: str) -> Path:
    matches = [path for path in folder.rglob(f"*{suffix}")
               if all(token in nfc(path.name) for token in includes)]
    if len(matches) != 1:
        raise ValueError(f"Expected one file for {includes}, found {len(matches)}")
    return matches[0]


def haversine(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    radius = 6_371_000.0
    dlat = np.radians(lats - lat)
    dlon = np.radians(lons - lon)
    part = np.sin(dlat / 2) ** 2 + np.cos(math.radians(lat)) * np.cos(np.radians(lats)) * np.sin(dlon / 2) ** 2
    return 2 * radius * np.arcsin(np.sqrt(part))


def read_rail(path: Path, year: int) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_excel(path, header=None)
    columns = ["year", "operator", "station_name", "line"]
    month_columns = []
    for month in range(1, 13):
        columns += [f"boardings_{month:02d}", f"alightings_{month:02d}"]
        month_columns += [f"boardings_{month:02d}", f"alightings_{month:02d}"]
    rows = raw.iloc[4:, list(range(4)) + list(range(6, 30))].copy()
    rows.columns = columns
    rows = rows[pd.to_numeric(rows["year"], errors="coerce") == year].copy()
    for column in month_columns:
        rows[column] = pd.to_numeric(rows[column], errors="coerce").fillna(0).astype(int)
    nonzero_months = [month for month in range(1, 13)
                      if int(rows[[f"boardings_{month:02d}", f"alightings_{month:02d}"]].to_numpy().sum()) > 0]
    return rows, {
        "file": nfc(path.name), "format": "XLS/BIFF", "encoding": "binary",
        "sha256": digest(path), "worksheet": str(pd.ExcelFile(path).sheet_names[0]),
        "sheet_rows": int(raw.shape[0]), "sheet_columns": int(raw.shape[1]),
        "valid_station_line_rows": int(len(rows)), "year": year,
        "nonzero_months": nonzero_months,
        "columns": ["연도", "기관", "역명", "호선", "월별 승차인원(명)", "월별 하차인원(명)"],
    }


def city_comparison(city: str, rail: pd.DataFrame, anchors: pd.DataFrame,
                    stations: pd.DataFrame) -> dict:
    rail = rail.copy()
    rail["key"] = rail["station_name"].map(station_key)
    grouped = rail.groupby("key", as_index=False).agg(
        station_name=("station_name", "first"),
        lines=("line", lambda values: " · ".join(sorted(set(map(str, values))))),
        boardings=("boardings_12", "sum"), alightings=("alightings_12", "sum"),
        source_rows=("station_name", "size"),
    )
    grouped["transit_total"] = grouped["boardings"] + grouped["alightings"]

    city_anchors = anchors[anchors["city"] == city].copy()
    city_anchors["key"] = city_anchors["name"].map(station_key)
    anchor_groups = city_anchors.groupby("key", as_index=False).agg(
        anchor_name=("name", "first"), latitude=("lat", "mean"), longitude=("lon", "mean"),
        anchor_rows=("stop_id", "size"),
    )
    compared = grouped.merge(anchor_groups, on="key", how="left", indicator=True)
    bike = stations[(stations["region_id"] == city) & stations["latitude"].notna() & stations["longitude"].notna()].copy()
    for radius in (300, 500):
        values = []
        for row in compared.itertuples():
            if pd.isna(row.latitude):
                values.append((0, 0, 0))
                continue
            distance = haversine(row.latitude, row.longitude, bike["latitude"].to_numpy(), bike["longitude"].to_numpy())
            nearby = bike[distance <= radius]
            values.append((len(nearby), int(nearby["rental_count"].sum()), int(nearby["return_count"].sum())))
        compared[[f"bike_station_count_{radius}m", f"bike_rentals_{radius}m", f"bike_returns_{radius}m"]] = pd.DataFrame(values, index=compared.index)
        compared[f"bike_activity_{radius}m"] = compared[f"bike_rentals_{radius}m"] + compared[f"bike_returns_{radius}m"]

    matched = compared[compared["_merge"] == "both"].copy()
    matched["transit_percentile"] = matched["transit_total"].rank(pct=True)
    matched["bike_percentile"] = matched["bike_activity_500m"].rank(pct=True)
    matched["joint_score"] = (matched["transit_percentile"] + matched["bike_percentile"]) / 2
    matched = matched.sort_values(["joint_score", "transit_total"], ascending=False)
    fields = ["station_name", "lines", "boardings", "alightings", "transit_total", "latitude", "longitude",
              "bike_station_count_300m", "bike_rentals_300m", "bike_returns_300m", "bike_activity_300m",
              "bike_station_count_500m", "bike_rentals_500m", "bike_returns_500m", "bike_activity_500m",
              "transit_percentile", "bike_percentile", "joint_score"]
    rows = json.loads(matched[fields].round(6).to_json(orient="records", force_ascii=False))
    return {
        "available": True, "city": city, "period_start": PERIOD_START, "period_end": PERIOD_END,
        "rail_station_line_rows": int(len(rail)), "rail_unique_station_names": int(len(grouped)),
        "matched_station_names": int(len(matched)),
        "unmatched_station_names": [str(value) for value in compared.loc[compared["_merge"] != "both", "station_name"]],
        "match_rate": round(len(matched) / len(grouped), 6) if len(grouped) else None,
        "transit_total": int(rail["boardings_12"].sum() + rail["alightings_12"].sum()),
        "correlations": {
            "pearson_300m": round(float(matched["transit_total"].corr(matched["bike_activity_300m"])), 6),
            "spearman_300m": round(float(matched["transit_total"].rank().corr(matched["bike_activity_300m"].rank())), 6),
            "pearson_500m": round(float(matched["transit_total"].corr(matched["bike_activity_500m"])), 6),
            "spearman_500m": round(float(matched["transit_total"].rank().corr(matched["bike_activity_500m"].rank())), 6),
        },
        "joint_score_definition": "도시 내 역 승하차량 백분위와 500m 내 자전거 대여+반납 백분위의 산술평균",
        "stations": rows,
        "limitations": [
            "월 단위 역별 승하차 총계이므로 시간대별 대중교통 수요 비교는 할 수 없음.",
            "역 300m·500m 내 자전거 활동의 동시 집중이며 실제 환승·인과관계를 뜻하지 않음.",
            "역명 정규화 후 위치 앵커와 일치한 역만 사용하며 미일치 역은 제외함.",
        ],
    }


def clean_mobile(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def audit_bus(upload_root: Path, bigdata: Path) -> tuple[dict, dict]:
    average_path = find_file(upload_root, ("시군구별", "정류장평균이용량"), ".csv")
    position_path = find_file(bigdata, ("버스정류장", "위치정보"), ".csv")
    average = pd.read_csv(average_path, encoding="cp949", dtype=str)
    positions = pd.read_csv(position_path, encoding="cp949", dtype=str)
    average["mobile_key"] = average["모바일ID"].map(clean_mobile)
    positions["mobile_key"] = positions["모바일단축번호"].map(clean_mobile)
    average["name_key"] = average["정류장명"].map(station_key)
    positions["name_key"] = positions["정류장명"].map(station_key)
    result = {}
    for city, province in (("seoul", "서울특별시"), ("daejeon", "대전광역시"), ("sejong", "세종특별자치시")):
        left = average[average["시도명"] == province].copy()
        right = positions[positions["도시명"].str.contains(province, na=False)].copy()
        mobile = set(right["mobile_key"]) - {""}
        names = set(right["name_key"])
        mobile_match = left["mobile_key"].isin(mobile) & left["mobile_key"].ne("")
        name_match = left["name_key"].isin(names)
        transfer = pd.to_numeric(left["평균환승이용량"], errors="coerce").fillna(0)
        result[city] = {
            "average_rows": int(len(left)), "position_rows": int(len(right)),
            "mobile_id_nonempty": int(left["mobile_key"].ne("").sum()),
            "mobile_id_matches": int(mobile_match.sum()), "name_matches": int(name_match.sum()),
            "either_candidate_matches": int((mobile_match | name_match).sum()),
            "positive_average_transfer_rows": int((transfer > 0).sum()), "status": "audit_only",
        }
    metadata = {
        "average_file": nfc(average_path.name), "average_sha256": digest(average_path),
        "average_rows": int(len(average)), "average_encoding": "CP949",
        "average_columns": list(average.columns[:11]), "period": "2025 annual daily average",
        "position_file": nfc(position_path.name), "position_sha256": digest(position_path),
        "position_rows": int(len(positions)), "position_encoding": "CP949",
    }
    return result, metadata


def build(upload_root: Path, output: Path) -> dict:
    bigdata = next(path for path in upload_root.iterdir() if path.is_dir() and nfc(path.name) == "빅데")
    anchors = pd.read_csv(ROOT / "data/processed/transit_anchors.csv")
    stations = pd.read_csv(ROOT / "data/processed/stations.csv")
    usage = pd.read_csv(ROOT / "data/processed/station_usage.csv")
    usage = usage[(usage["date"] >= PERIOD_START) & (usage["date"] <= PERIOD_END)]
    usage = usage.groupby(["region_id", "station_id"], as_index=False)[["rental_count", "return_count"]].sum()
    stations = stations.merge(usage, on=["region_id", "station_id"], how="left")
    stations[["rental_count", "return_count"]] = stations[["rental_count", "return_count"]].fillna(0)

    audits, rail_2025 = [], {}
    for city, token in (("seoul", "서울"), ("daejeon", "대전")):
        for year in (2025, 2026):
            path = find_file(bigdata, (str(year), token, "승강차실적"), ".xls")
            rows, metadata = read_rail(path, year)
            metadata.update({"city": city, "source": "철도산업정보센터/해당 도시철도 운영기관",
                             "source_url": "https://www.kric.go.kr/jsp/industry/rss/citystapassList.jsp",
                             "github_commit": "1f88dc59de0be469486a7ba5c4d0ce3d12c82a23", "used": year == 2025})
            audits.append(metadata)
            if year == 2025:
                rail_2025[city] = rows
    bus_audit, bus_metadata = audit_bus(upload_root, bigdata)
    result = {
        "revision": "additional-transit-demand-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_start": PERIOD_START, "period_end": PERIOD_END,
        "audit_files": audits, "bus_annual_reference": bus_audit, "bus_metadata": bus_metadata,
        "cities": {
            "seoul": city_comparison("seoul", rail_2025["seoul"], anchors, stations),
            "daejeon": city_comparison("daejeon", rail_2025["daejeon"], anchors, stations),
            "sejong": {"available": False, "city": "sejong", "period_start": PERIOD_START, "period_end": PERIOD_END,
                       "message": "2025년 12월 BRT 정류장별 승하차 자료가 없어 같은 기간 수요 비교를 수행하지 않았습니다.",
                       "annual_bus_reference": bus_audit["sejong"],
                       "limitations": ["연간 일평균 버스 자료를 12월 BRT 승하차량으로 대체하지 않음.",
                                       "정류장명 후보 연결은 공통 ID가 아니므로 분석 점수에 사용하지 않음."]},
        },
        "global_limitations": [
            "대중교통 승하차량과 인근 자전거 활동의 상관은 실제 환승률이 아님.",
            "서울·대전 XLS는 월 합계라 시간대별 대중교통 수요 비교를 구현하지 않음.",
            "국토교통부 정류장 평균 이용량은 2025년 연간 일평균이며 12월 분석과 합산하지 않음.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload-root", default=str(ROOT), help="Repository root containing 빅데/ and uploaded root CSV")
    parser.add_argument("--output", default=str(ROOT / "data/reference/transit_demand_202512.json"))
    args = parser.parse_args()
    built = build(Path(args.upload_root).resolve(), Path(args.output).resolve())
    print(json.dumps({city: {key: value for key, value in row.items() if key in {"available", "matched_station_names", "match_rate", "transit_total", "correlations", "message"}}
                      for city, row in built["cities"].items()}, ensure_ascii=False, indent=2))
