import math
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler


def _feature_matrix(rows, feature_set):
    shape = [[v / p["rental_count"] for v in p["hourly"]] for p in rows]
    volume = [[math.log1p(p["rental_count"])] for p in rows]
    weekend = [[p["weekend_share"]] for p in rows] if all(p.get("weekend_share") is not None for p in rows) else None
    if feature_set == "time_share":
        return np.array(shape, dtype=float), [f"hour_{i}_share" for i in range(24)]
    if feature_set == "volume_only":
        return np.array(volume, dtype=float), ["log_volume"]
    values = [shape[i] + volume[i] + (weekend[i] if weekend else []) for i in range(len(rows))]
    names = [f"hour_{i}_share" for i in range(24)] + ["log_volume"]
    if weekend:
        names.append("weekend_share")
    return np.array(values, dtype=float), names


def _diagnostics(matrix, row_count):
    scaled = StandardScaler().fit_transform(matrix)
    diagnostics = []
    for k in range(2, min(8, row_count - 1) + 1):
        model = KMeans(n_clusters=k, random_state=42, n_init=10).fit(scaled)
        score = silhouette_score(scaled, model.labels_, sample_size=min(row_count, 1500), random_state=42)
        diagnostics.append({"k": k, "inertia": round(float(model.inertia_), 3), "silhouette": round(float(score), 4)})
    return scaled, diagnostics


def compare_feature_sets(profiles):
    """Evaluate shape and scale separately without selecting data to improve a score."""
    rows = [p for p in profiles if p["rental_count"] > 0 and p["hourly"] is not None and sum(p["hourly"]) > 0]
    if len(rows) < 3:
        return []
    comparisons = []
    for feature_set, label in (("time_share", "시간대 비율"), ("volume_only", "이용량 규모"),
                               ("combined", "시간대 비율+이용량 규모")):
        matrix, names = _feature_matrix(rows, feature_set)
        _, diagnostics = _diagnostics(matrix, len(rows))
        best = max(diagnostics, key=lambda item: item["silhouette"])
        comparisons.append({"feature_set": feature_set, "label": label, "features": names,
            "selected_k": best["k"], "best_silhouette": best["silhouette"],
            "diagnostics": diagnostics, "station_count": len(rows),
            "quality": "low" if best["silhouette"] < 0.2 else "exploratory"})
    return comparisons


def cluster_stations(profiles):
    """profiles: station rows with hourly counts and optional weekend share."""
    rows = [p for p in profiles if p["rental_count"] > 0 and p["hourly"] is not None and sum(p["hourly"]) > 0]
    if len(rows) < 2:
        return {"available": False, "clusters": [], "diagnostics": [], "message": "이용 기록이 있는 대여소가 2개 이상 필요합니다."}
    matrix, feature_names = _feature_matrix(rows, "combined")
    scaled, diagnostics = _diagnostics(matrix, len(rows))
    chosen = max(diagnostics, key=lambda x: x["silhouette"])["k"] if diagnostics else 2
    model = KMeans(n_clusters=chosen, random_state=42, n_init=10).fit(scaled)
    groups = {}
    for label in range(chosen):
        members = [p for p, value in zip(rows, model.labels_) if value == label]
        total = sum(p["rental_count"] for p in members)
        hours = [sum(p["hourly"][h] for p in members) for h in range(24)]
        morning = sum(hours[6:10]) / total
        evening = sum(hours[17:21]) / total
        daytime = sum(hours[10:17]) / total
        weekend = sum(p["rental_count"] * p["weekend_share"] for p in members) / total if "weekend_share" in feature_names else None
        # Descriptions only state the measured dominant pattern.
        dominant = max((morning / 4, "오전"), (evening / 4, "오후"), (daytime / 7, "주간"))[1]
        groups[label] = {
            "role": f"{dominant} 이용 비중 우세",
            "description": f"관측된 시간대 중 {dominant} 시간당 평균 이용 비중이 가장 높습니다.",
            "station_count": len(members), "mean_rentals": round(total / len(members), 1),
            "morning_share": round(morning, 4), "evening_share": round(evening, 4),
            "weekend_share": round(weekend, 4) if weekend is not None else None,
        }
    best_score = max((x["silhouette"] for x in diagnostics), default=None)
    quality_low = best_score is not None and best_score < 0.2
    if quality_low:
        for summary in groups.values():
            summary["role"] = "유형 해석 보류"
            summary["description"] = "Silhouette가 0.2 미만입니다. 시간대 대표 패턴은 참고값이며 유형으로 확정하지 않습니다."
    result = [{"station_id": p["station_id"], "cluster_id": int(label), **groups[int(label)]}
              for p, label in zip(rows, model.labels_)]
    quality_note = " 군집 분리가 낮아 유형 명칭을 부여하지 않았습니다." if quality_low else ""
    return {"available": True, "clusters": result, "diagnostics": diagnostics,
            "cluster_summaries": [{"cluster_id": label, **summary} for label, summary in sorted(groups.items())],
            "selected_k": chosen, "features": feature_names, "feature_comparisons": compare_feature_sets(profiles),
            "quality": "low" if quality_low else "exploratory", "interpretation_allowed": not quality_low,
            "message": "시간대 비율과 log(이용량)을 StandardScaler로 표준화했습니다. k는 Silhouette 최고값 기준입니다." + quality_note}


def adjusted_rand(left, right):
    """Compare labels only for station IDs observed in both periods."""
    left_by_id = {row["station_id"]: row["cluster_id"] for row in left}
    right_by_id = {row["station_id"]: row["cluster_id"] for row in right}
    common = sorted(set(left_by_id) & set(right_by_id))
    if len(common) < 2:
        return {"available": False, "common_station_count": len(common), "ari": None}
    score = adjusted_rand_score([left_by_id[sid] for sid in common], [right_by_id[sid] for sid in common])
    return {"available": True, "common_station_count": len(common), "ari": round(float(score), 4)}
