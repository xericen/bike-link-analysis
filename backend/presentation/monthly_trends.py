"""Prepared city-wide history; common comparison never mixes different periods."""
import json
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REFERENCE=ROOT/"data/reference/monthly_trends"

def summarize(rows):
    total=sum(r["rental_count"] for r in rows)
    days=sum(r["observed_days"] for r in rows)
    hourly=[sum(r.get("hourly_rentals",[0]*24)[h] for r in rows) for h in range(24)]
    max_hour=max(hourly,default=0)
    return {"rental_count":total,"month_count":len({r["month"] for r in rows}),"observed_days":days,
        "daily_average":total/days if days else None,"partial_months":sum(not r["complete"] for r in rows),
        "anchor_linked_ratio":sum(r.get("anchor_linked_trips",0) for r in rows)/total if total else None,
        "unknown_endpoint_ratio":sum(r.get("unknown_endpoint_trips",0) for r in rows)/total if total else None,
        "hourly":[{"hour":h,"count":v,"height":100*v/max_hour if max_hour else 0} for h,v in enumerate(hourly)],
        "peak_hours":[h for h,v in enumerate(hourly) if v==max_hour] if max_hour else []}

def read(region_id,year=None):
    if region_id not in {"seoul","daejeon","sejong","all"}:raise ValueError("알 수 없는 도시입니다.")
    if region_id=="all":
        cities=[]
        for city in ("seoul","daejeon","sejong"):
            result=read(city,2025)
            if not result.get("available"):
                return {"available":False,"scope":"common_comparison","message":"세 도시의 공통 12월 집계가 준비되지 않았습니다."}
            row=next((m for m in result["months"] if m["month"]=="2025-12"),None)
            if row is None:return {"available":False,"scope":"common_comparison","message":"공통 12월 자료가 없습니다."}
            cities.append({**row,"region_id":city})
        summary=summarize(cities)
        summary.update(city_count=3,city_observation_days=summary["observed_days"],observed_days=31,daily_average=summary["rental_count"]/31)
        return {"available":True,"region_id":"all","scope":"common_comparison","selected_year":2025,"years":[2025],
            "months":cities,"summary":summary,"period_start":"2025-12-01","period_end":"2025-12-31",
            "display_start":"2025-12-01","display_end":"2025-12-31","repeated_candidates":[],
            "scope_note":"서울·대전·세종의 같은 2025년 12월만 비교합니다.",
            "limitations":["도시별 장기 이용량을 합산하지 않습니다. 세 도시 관측일 합계는 도시-일 단위이며 달력 일수가 아닙니다."]}
    file=REFERENCE/(region_id+".json")
    if not file.exists():
        return {"available":False,"region_id":region_id,"scope":"single_city_longitudinal","message":"이 도시의 월별 자료를 검증하고 있습니다. 기존 12월 분석은 계속 이용할 수 있습니다."}
    data=json.loads(file.read_text(encoding="utf-8"))
    if region_id=="daejeon":
        data["limitations"].append("원본 파일명에 2025년 2월26~28일·3월1~3일 시스템 장애가 명시됩니다. 2월26일 일부 기록이 있어도 해당 날짜의 완전성은 보장하지 않습니다.")
    years=sorted({int(row["month"][:4]) for row in data["months"]},reverse=True)
    if year not in (None,0) and (type(year) is not int or year not in years):
        return {"available":False,"region_id":region_id,"years":years,"scope":"single_city_longitudinal","message":"검증된 자료가 없는 연도입니다."}
    selected=year or 0
    rows=[row for row in data["months"] if not selected or row["month"].startswith(str(selected)+"-")]
    ranks=defaultdict(list);names={}
    for row in rows:
        if not row["complete"]:continue
        for c in row["top_candidates"]:
            names[c["station_id"]]=c["station_name"]
            ranks[c["station_id"]].append({"month":row["month"],"rank":c["rank"]})
    repeated=sorted([{"station_id":sid,"station_name":names[sid],"top10_months":len(entries),"ranks":entries} for sid,entries in ranks.items()],key=lambda r:(-r["top10_months"],r["station_id"]))[:5]
    max_daily=max((r["daily_average"] or 0 for r in rows),default=0)
    return {**data,"available_period_start":data["period_start"],"available_period_end":data["period_end"],
        "period_start":rows[0]["period_start"],"period_end":rows[-1]["period_end"],"years":years,"selected_year":selected,
        "display_start":rows[0]["period_start"],"display_end":rows[-1]["period_end"],"eligible_months":sum(r["complete"] for r in rows),
        "months":[{**r,"trend_height":100*r["daily_average"]/max_daily if max_daily else 0,"top_candidates":r["top_candidates"][:3]} for r in rows],
        "available_month_count":len(data["months"]),"summary":summarize(rows),"repeated_candidates":repeated,
        "scope_note":"선택 도시·기간의 전체 이용을 집계한 별도 분석입니다. 공통 비교는 2025년 12월로 유지합니다."}
