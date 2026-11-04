import math
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


def cluster_stations(profiles):
    """profiles: station rows with hourly counts and optional weekend share."""
    rows = [p for p in profiles if p["rental_count"] > 0 and p["hourly"] is not None and sum(p["hourly"]) > 0]
    if len(rows) < 2:
        return {"available": False, "clusters": [], "diagnostics": [], "message": "이용 기록이 있는 대여소가 2개 이상 필요합니다."}
    feature_names = [f"hour_{i}" for i in range(24)] + ["log_volume"]
    if all(p.get("weekend_share") is not None for p in rows):
        feature_names.append("weekend_share")
    matrix = np.array([
        [v / p["rental_count"] for v in p["hourly"]] +
        [math.log1p(p["rental_count"])] +
        ([p["weekend_share"]] if "weekend_share" in feature_names else [])
        for p in rows
    ], dtype=float)
    scaled = StandardScaler().fit_transform(matrix)
    diagnostics = []
    max_k = min(8, len(rows) - 1)
    for k in range(2, max_k + 1):
        model = KMeans(n_clusters=k, random_state=42, n_init=10).fit(scaled)
        sample_size = min(len(rows), 1500)
        score = silhouette_score(scaled, model.labels_, sample_size=sample_size, random_state=42)
        diagnostics.append({"k": k, "inertia": round(float(model.inertia_), 3), "silhouette": round(float(score), 4)})
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
    result = [{"station_id": p["station_id"], "cluster_id": int(label), **groups[int(label)]}
              for p, label in zip(rows, model.labels_)]
    quality_note = " 군집 분리가 약하므로 유형 해석에 주의하세요." if diagnostics and max(x["silhouette"] for x in diagnostics) < 0.1 else ""
    return {"available": True, "clusters": result, "diagnostics": diagnostics,
            "selected_k": chosen, "features": feature_names, "message": "StandardScaler·K-means; k는 Silhouette 최고값 기준." + quality_note}
