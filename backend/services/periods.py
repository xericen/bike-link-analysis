"""Validated date bounds shared by the WIZ UI and its Solar context."""
from datetime import date
from backend.services import real_data

def bounds(region_id):
    if region_id == "all":
        days = [real_data.observed_dates(r["region_id"]) for r in real_data.REGIONS]
        days = [x for x in days if x]
        low = max((x[0] for x in days), default=None)
        high = min((x[-1] for x in days), default=None)
        if low and high and low > high: low, high = None, None
    else:
        if region_id not in {r["region_id"] for r in real_data.REGIONS}: raise ValueError("알 수 없는 도시입니다.")
        days = real_data.observed_dates(region_id)
        low, high = (days[0], days[-1]) if days else (None, None)
    return {"min":low, "max":high, "available":bool(low and high),
            "message":"" if low and high else "상세 날짜별 자료가 없어 연간 통계만 제공합니다."}

def resolve(region_id, start=None, end=None):
    limits = bounds(region_id)
    if not limits["available"]:
        if start or end: raise ValueError("이 도시에는 선택 가능한 상세 날짜별 자료가 없습니다.")
        return None, None
    start, end = start or limits["min"], end or limits["max"]
    try: date.fromisoformat(start); date.fromisoformat(end)
    except (ValueError, TypeError): raise ValueError("기간은 YYYY-MM-DD 형식이어야 합니다.")
    if start > end: raise ValueError("시작일이 종료일보다 늦습니다.")
    if start < limits["min"] or end > limits["max"]:
        raise ValueError("확보된 데이터 범위를 벗어난 기간입니다: " + limits["min"] + " ~ " + limits["max"])
    return start, end

def all_bounds():
    return {rid:bounds(rid) for rid in [r["region_id"] for r in real_data.REGIONS] + ["all"]}
