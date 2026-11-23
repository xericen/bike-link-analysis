"""Run the three December experiments offline; do not write any production KPI."""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.research import method_validation as m
from backend.services import precomputed

ROOT = m.ROOT

def build(output=m.FILE):
    revision = precomputed.revision()
    if revision == "unverified-inputs":
        raise RuntimeError("현재 입력 검증이 필요합니다. 기존 KPI를 우회하지 않습니다.")
    dependencies = m.dependencies()
    report = {"schema": 1, "available": True, "revision": revision,
              "period_start": m.START, "period_end": m.END,
              "built_at": datetime.now(timezone.utc).isoformat(),
              "dependencies": dependencies, "cities": {},
              "scope_note": "공통 2025년 12월 별도 검증 실험. 개별 도시 전체 기간 결과와 합산하지 않습니다.",
              "limitations": [
                  "재발견은 관측 대여소 위치의 회복 실험이며 신규 설치 후 이용량·환승 증가의 검증이 아닙니다.",
                  "동일 월의 공간 가림 검증이며 다른 계절로의 일반화는 검증하지 않았습니다.",
                  "가중치와 거리는 사전 지정한 실험 조건이며 가장 좋아 보이는 조합을 운영 점수로 자동 채택하지 않습니다.",
                  "세종은 동일 기간 BRT 승하차량 미확보로 수요 매트릭스 N/A입니다."]}
    demand = json.loads((ROOT / "data/reference/transit_demand_202512.json").read_text())
    if (demand["period_start"], demand["period_end"]) != (m.START, m.END):
        raise RuntimeError("대중교통 수요와 실험 기간 불일치")
    for city in m.CITIES:
        started = time.perf_counter()
        boundary, stations, facilities, districts, anchors, od_rows = m.load_city(city)
        print(city, "sensitivity", flush=True)
        sensitivity = m.sensitivity(boundary, stations, facilities, districts, anchors, city)
        canonical = precomputed.read("planning", city, m.START, m.END)["new_sites"][:10]
        actual = sensitivity[0]["top"]
        assert [r["site_id"] for r in actual] == [r["site_id"] for r in canonical], (city, "canonical candidate mismatch")
        assert all(abs(a["score"] - b["score"]) < 1e-12 for a,b in zip(actual, canonical)), (city, "canonical scores")
        print(city, "mask and recover", flush=True)
        backtest = m.backtest(boundary, stations, facilities, districts, anchors, od_rows, city)
        matrix500 = m.demand_matrix(demand["cities"][city], 500)
        matrix300 = m.demand_matrix(demand["cities"][city], 300)
        if matrix500.get("available") and matrix300.get("available"):
            other = {r["station_name"]: r["quadrant"] for r in matrix300["rows"]}
            matrix500["radius_comparison"] = {
                "other_radius_m": 300, "common_stations": len(matrix500["rows"]),
                "unchanged_count": sum(other[r["station_name"]] == r["quadrant"] for r in matrix500["rows"]),
                "rule": "반경별 도시 내 중앙값을 각각 계산한 후 동일 역의 사분면을 비교"}
        report["cities"][city] = {"city": city, "available": True,
                                  "sensitivity": sensitivity, "backtest": backtest,
                                  "demand_matrix": matrix500, "demand_matrix_300m": matrix300,
                                  "canonical_top10_matches_production": True,
                                  "seconds": time.perf_counter() - started}
        print(city, "completed", round(time.perf_counter() - started, 3), flush=True)
    if precomputed.revision() != revision or m.dependencies() != dependencies:
        raise RuntimeError("실험 도중 입력 변경; 게시하지 않습니다.")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    os.replace(temp, output)
    return report

def tables(report, output):
    lines = ["# 방법 검증 실측 결과", "",
             f"관측 기간: {m.START} ~ {m.END}. 아래 수치는 실제 오프라인 재계산 결과다.",
             "운영 후보 점수·KPI는 변경하지 않았다. 낮은 재발견률도 그대로 기록한다.", "",
             "## 신규 입지 민감도", "",
             "지리 중첩률은 기준 TOP10과 변경 TOP10을 300m 이내 일대일로 연결한 비율이다. 격자 크기가 다르면 ID 일치율만으로 판단하지 않는다.",
             "", "| 도시 | 앵커m | 격자m | 가중치 | 후보버퍼m | 후보수 | ID Jaccard | 지리 중첩 | TOP10 추가면적 km² |",
             "|---|---:|---:|---|---:|---:|---:|---:|---:|"]
    for city, value in report["cities"].items():
        for r in value["sensitivity"]:
            lines.append(f"| {city} | {r['anchor_radius_m']} | {r['grid_step_m']} | {r['policy']} | {r['candidate_buffer_m']} | {r['candidate_count']} | {r['exact_jaccard']:.4f} | {r['geographic_top10_overlap']:.4f} | {r['union_added_area_m2']/1e6:.6f} |")
    lines += ["", "후보 버퍼500m는 순위 입력이 아니라 면적 시나리오만 바꾼다. 이 경우 순위 일치를 강건성 성과로 세지 않는다.",
              "", "## 대여소 가림 후 재발견", "",
              "이용상위·구간표본은 N≤10, 공간실험은 선택 1km 격자 내 이용 대여소 전수를 숨기고 TOP10을 평가. 300m 이내 최대 일대일 매칭. 전체 재발견률이 주 지표이며, 후보 생성 가능한 위치만의 조건부 비율은 보조값이다.",
              "무작위 기준선은 같은 후보 풀에서 30회 추출. 반복 fold가 독립 표본이라는 신뢰구간을 만들지 않았다. 공간실험의 N>10일 때 TOP10 재발견률 상한은 10/N이며 실험별 상한을 JSON에 기록한다.", "",
              "| 도시 | 가림 유형/seed | N | 생성가능 N | 전체 방법 hits/N | 주변수요만 | 시설·인구만 | 무작위 평균 |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
    for city, value in report["cities"].items():
        for r in value["backtest"]:
            methods = r["methods"]
            lines.append(f"| {city} | {r['fold']}/{r['seed']} | {r['target_count']} | {r['feasible_within_match_radius_count']} | {methods['full']['hits']}/{r['target_count']} | {methods['demand_only']['hits']}/{r['target_count']} | {methods['facilities_population_only']['hits']}/{r['target_count']} | {r['random_recall_mean']:.4f} |")
    lines += ["", "## 서울·대전 수요 매트릭스", "",
              "도시 내 중앙값 이상을 높음으로 분류하되 0은 낮음으로 분류. 역별 승하차와 반경500m 자전거 대여+반납의 공존이며 실제 환승률·잠재 수요 예측이 아니다.",
              "", "| 도시 | 연결역수 | 양쪽높음 | 대중교통높음·자전거낮음 | 대중교통낮음·자전거높음 | 양쪽낮음 | 300/500m 분류 유지 |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for city, value in report["cities"].items():
        x = value["demand_matrix"]
        if x.get("available"):
            c=x["counts"]; stability=x["radius_comparison"]
            lines.append(f"| {city} | {x['matched_count']} | {c['high_high']} | {c['high_low']} | {c['low_high']} | {c['low_low']} | {stability['unchanged_count']}/{stability['common_stations']} |")
        else:
            lines.append(f"| {city} | N/A | N/A | N/A | N/A | N/A | N/A |")
    lines += ["", "서울은 위치 연결233개 중 승하차 합계0인 신내역1개를 무수요로 단정하지 않고 분류 보류했다. 원본 수요 API는 변경하지 않았다.", "", "세종: " + report["cities"]["sejong"]["demand_matrix"]["message"], "",
              "이 보고서는 방법의 조건 민감성과 관측 위치 재발견을 평가하며 실제 설치·재배치의 인과 효과를 입증하지 않는다."]
    Path(output).write_text("\n".join(lines)+"\n")

if __name__ == "__main__":
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", default=str(m.FILE))
    parser.add_argument("--tables", default="docs/METHOD_VALIDATION_RESULTS.md")
    args=parser.parse_args()
    value=build(args.output)
    tables(value,args.tables)
