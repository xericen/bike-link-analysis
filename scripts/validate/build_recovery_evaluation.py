"""Run frozen research experiment, separated from production KPI and web requests."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from backend.research import recovery_evaluation as e, method_validation as m

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("Preserve previous evidence; choose a new output directory: " + str(path))
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))

def source_manifest():
    paths = [Path(e.__file__), Path(__file__), m.FILE, m.ROOT / "backend/research/validation_followup.py",
             m.ROOT / "backend/research/method_validation.py"]
    for city in m.CITIES:
        folder = m.ROOT / "data/individual" / city
        paths += [folder / "analysis.sqlite", folder / "stations.csv", folder / "transit_anchors.csv"]
        paths += [m.ROOT / "data/processed" / f"planning_{kind}_{city}.json" for kind in ("facilities", "boundary")]
    paths += [m.ROOT / "data/processed/planning_population.json"]
    manifest = {}
    for path in paths:
        stat = path.stat()
        digest = __import__("hashlib").sha256()
        with path.open("rb") as stream:
            for part in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(part)
        manifest[str(path.relative_to(m.ROOT))] = {"sha256": digest.hexdigest(), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return manifest

def run():
    out = e.OUTPUT
    plan = {"created_at": datetime.now(timezone.utc).isoformat(), "periods": e.PERIODS,
            "steps_m": e.STEPS, "policies": e.POLICIES, "seeds": e.SEEDS,
            "matching_m": 300, "top_k": [10, 20],
            "selection": "June macro fold Recall@10; tie order 500/equal first; locked before July OD load",
            "spatial_test": "Remove all located stations in held1km block and all incident OD; test block at least2km from development block; no shared target IDs",
            "limitations": ["Historical coordinates/anchors/facilities are fixed reference snapshots, not reconstructed monthly.",
                            "All scores, including simple baselines, use the same generated candidate pool.",
                            "Two summer months are not a winter/general seasonal validation.",
                            "Prior December diagnostics already observed; June/July are new to this experiment, not untouched by the project's prior descriptive analyses.",
                            "Recovery of existing sites does not establish unmet demand or installation effects."]}
    write(out / "protocol.json", plan)
    print("protocol sealed; hashing read-only inputs", flush=True)
    manifest = source_manifest()
    write(out / "inputs.json", manifest)
    report = {"built_at": datetime.now(timezone.utc).isoformat(), "protocol": plan,
              "original_december_diagnostics": e.existing_diagnostics(), "cities": {}}
    for city in m.CITIES:
        started = time.perf_counter()
        inputs = e.load(city, *e.PERIODS["development"])
        dev_folds, eligibility = e.folds(inputs[1], inputs[0], "development")
        dev = []
        for f in dev_folds:
            print(city, "June", f["name"], len(f["targets"]), flush=True)
            dev.append(e.evaluate_fold(city, inputs, f))
        selected, scores = e.select_config(dev)
        dev_ids = {sid for f in dev_folds for sid in f["hidden_ids"]}
        block = next((f["block"] for f in dev_folds if f["name"] == "spatial_block"), None)
        lock = {"city": city, "selected": selected, "development_scores": scores,
                "locked_at": datetime.now(timezone.utc).isoformat(), "excluded_test_ids": sorted(dev_ids)}
        write(out / (city + "-selection-lock.json"), lock)
        inputs2 = e.load(city, *e.PERIODS["evaluation"])
        eval_folds, eligibility2 = e.folds(inputs2[1], inputs2[0], "evaluation", dev_ids, block)
        assert not dev_ids.intersection(sid for f in eval_folds for sid in f["hidden_ids"])
        final = []
        for f in eval_folds:
            print(city, "July", f["name"], len(f["targets"]), "locked", selected, flush=True)
            final.append(e.evaluate_fold(city, inputs2, f))
        value = {"development_data": inputs[-1], "evaluation_data": inputs2[-1],
                 "development_eligibility": eligibility, "evaluation_eligibility": eligibility2,
                 "selection": lock, "development": dev, "evaluation": final,
                 "selected_summary": e.summary(final, selected),
                 "baseline_summary": e.summary(final, "500:equal"),
                 "demand_baseline_summary": e.summary(final, "500:demand"),
                 "seconds": time.perf_counter() - started}
        write(out / (city + ".json"), value)
        report["cities"][city] = value
        print(city, "done", value["seconds"], flush=True)
    for rel, stamp in manifest.items():
        stat = (m.ROOT / rel).stat()
        if (stat.st_size, stat.st_mtime_ns) != (stamp["size"], stamp["mtime_ns"]):
            raise RuntimeError("Input changed during experiment: " + rel)
    report["input_metadata_unchanged"] = True
    write(out / "results.json", report)
    table(report, out / "RESULTS.md")
    return report

def table(report, path):
    lines = ["# 후보 재발견 방법 개선 검증", "",
             "고정 계획 → 6월 방법 선택 → 방법 잠금 → 7월 별도 지역·대여소 평가. 운영 추천은 변경하지 않았다.",
             "기존12월 인기 대여소0/10 결과도 보존한다. 두 여름 달의 관측 위치 재발견이며 설치 효과·겨울 일반화 검증이 아니다.", "",
             "## 원래12월 인기 대여소 실패 분해", "",
             "| 도시 | 목표 | 주변 후보 없음 | 후보 있으나 TOP10 미복구 | 복구 |",
             "|---|---:|---:|---:|---:|"]
    for city, rows in report["original_december_diagnostics"].items():
        r = next(r for r in rows if r["fold"] == "high_usage")
        lines.append(f"| {city} | {r['n']} | {r['no_candidate']} | {r['possible_not_matched_top10']} | {r['hits10']} |")
    lines += ["", "## 실제 관측기간", "", "| 도시 | 6월 이동 | 6월 관측일 | 7월 이동 | 7월 관측일 | 선택 방법 |",
              "|---|---:|---:|---:|---:|---|"]
    for city, c in report["cities"].items():
        a,b=c["development_data"],c["evaluation_data"]
        lines.append(f"| {city} | {a['trips']} | {a['observed_days']} | {b['trips']} | {b['observed_days']} | {c['selection']['selected']} |")
    lines += ["", "## 7월 별도 평가", "", "가능은300m 내 생성 후보가 있는 목표 수다. 매칭은 일대일이며 한 후보로 여러 목표를 복구하지 않는다.",
              "공간 블록 목표 수가10보다 많으면 Recall@10 상한은10/N이다. 겹치는 fold를 독립 표본으로 간주하지 않는다.",
              "", "| 도시 | 평가 | N | 후보 가능 | 기준 복구@10 | 선택 복구@10 | 선택 복구@20 | 수요만@10 | 무작위 평균 Recall@10 |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for city,c in report["cities"].items():
        for r,b,d in zip(c["selected_summary"],c["baseline_summary"],c["demand_baseline_summary"]):
            lines.append(f"| {city} | {r['fold']} | {r['n']} | {r['possible']} | {b['hits10']} | {r['hits10']} | {r['hits20']} | {d['hits10']} | {r['random_recall']:.4f} |")
    lines += ["", "## 해석과 진행 범위", "",
              "- 파라미터는6월에서만 선택하고7월 로드 전에 도시별 selection-lock.json을 저장했다.7월 결과로 재선택하지 않았다.",
              "- 500/250m 격자와 균등·주변수요만·공백우선·시설/인구만 순위를 비교했다. 거리 임계값과300m 평가 반경을 유리하게 늘리지 않았다.",
              "- 데이터 기간은 신규 평가이나 같은 위치·시설 참조를 재사용했다. 신규 신설 대여소의 미래 수요 예측이나 엄격한 모든 외생 자료 시점 분리 검증은 아니다.",
              "- 기존점수보다 개선하지 못하거나 단순수요/무작위보다 낫지 않으면 운영 추천에 반영하지 않는다.",
              "- 세종의 동일월BRT 승하차량은 추가 확보하지 않았다. 실제 보행 경로·설치 가능성·환승/재고 효과는 미검증이다.",
              "- 각도시JSON에 모든8조건, 목표별 후보생성/순위 실패 단계·최소거리·일대일 대응·반경/분모·OD 제거 감사를 보존한다.",
              "- baseline/selected는 같은 목표를 평가하지만 격자가 다르면 후보 풀이 다르다. 정책간 비교와 생성방식간 비교를 구분한다."]
    path.write_text("\n".join(lines)+"\n")

if __name__ == "__main__":
    run()
