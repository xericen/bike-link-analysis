"""Read the verified December transit/bike demand comparison artifact."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "data/reference/transit_demand_202512.json"
VALID = {"seoul", "daejeon", "sejong", "all"}


def read(region_id: str, date_start: str | None = None, date_end: str | None = None) -> dict:
    if region_id not in VALID:
        raise ValueError("지원하지 않는 도시입니다.")
    if not REFERENCE.exists():
        return {"available": False, "region_id": region_id, "message": "대중교통 수요 비교 결과가 준비되지 않았습니다."}
    data = json.loads(REFERENCE.read_text(encoding="utf-8"))
    start, end = data["period_start"], data["period_end"]
    if (date_start and date_start != start) or (date_end and date_end != end):
        return {"available": False, "region_id": region_id, "period_start": start, "period_end": end,
                "message": "대중교통 승하차 자료와 겹치는 2025년 12월 결과만 제공합니다."}
    if region_id == "all":
        return {"available": True, "region_id": "all", "period_start": start, "period_end": end,
                "cities": [data["cities"][city] for city in ("seoul", "daejeon", "sejong")],
                "limitations": data["global_limitations"], "revision": data["revision"]}
    return {**data["cities"][region_id], "revision": data["revision"],
            "global_limitations": data["global_limitations"]}
