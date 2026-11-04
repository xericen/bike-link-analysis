from sklearn.metrics.pairwise import cosine_similarity


def station_similarity(profiles, station_id, limit=10):
    target = next((p for p in profiles if p["station_id"] == station_id), None)
    if target is None:
        raise ValueError("대여소를 찾을 수 없습니다.")
    if target["rental_count"] <= 0 or target["hourly"] is None:
        return []
    others = [p for p in profiles if p["station_id"] != station_id and p["rental_count"] > 0 and p["hourly"] is not None]
    if not others:
        return []
    def vector(p):
        total = p["rental_count"]
        values = [hour / total for hour in p["hourly"]]
        if p.get("weekend_share") is not None and target.get("weekend_share") is not None:
            values += [p["weekend_share"]]
        return values
    scores = cosine_similarity([vector(target)], [vector(p) for p in others])[0]
    return sorted(({
        "station_id": p["station_id"], "station_name": p.get("station_name"),
        "score": round(float(score), 5), "rental_count": p["rental_count"],
        "volume_ratio": round(p["rental_count"] / target["rental_count"], 3),
    } for p, score in zip(others, scores)), key=lambda x: x["score"], reverse=True)[:limit]
