"""Regression: history is separate, partial months are not zero-filled or ranked as complete."""
import json
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.presentation import monthly_trends
from backend.agents.solar import run_tool
from scripts.preprocess.build_monthly_trends import accumulate

@pytest.fixture
def history(tmp_path,monkeypatch):
    def month(key,complete,count,sid):
        return {"month":key,"period_start":key+"-01","period_end":key+"-28","complete":complete,"rental_count":count,"observed_days":28 if complete else 27,"daily_average":count/(28 if complete else 27),"hourly_rentals":[count]+[0]*23,
                "top_candidates":[{"station_id":sid,"station_name":sid,"rank":1}]}
    value={"available":True,"region_id":"seoul","scope":"single_city_longitudinal","period_start":"2024-01-01","period_end":"2025-12-31",
           "months":[month("2024-01",True,99,"A"),month("2025-01",True,5,"B"),month("2025-02",False,7,"C")],
           "limitations":[],"common_comparison":{"date_start":"2025-12-01","date_end":"2025-12-31"}}
    (tmp_path/"seoul.json").write_text(json.dumps(value))
    monkeypatch.setattr(monthly_trends,"REFERENCE",tmp_path)
    return value

def test_year_filter_and_partial_month_recurrence(history):
    data=monthly_trends.read("seoul",2025)
    assert data["selected_year"]==2025
    assert [r["rental_count"] for r in data["months"]]==[5,7]
    assert data["eligible_months"]==1
    assert [r["station_id"] for r in data["repeated_candidates"]]==["B"]
    assert data["common_comparison"]["date_start"]=="2025-12-01"
    assert not monthly_trends.read("seoul",2026)["available"]

def test_all_does_not_merge_different_city_periods(history):
    result=monthly_trends.read("all")
    assert result["available"] is False
    assert "months" not in result
    assert "12월" in result["message"]

def test_api_and_solar_history_keep_explicit_scope(history):
    response=TestClient(app).get("/api/regions/seoul/monthly-trends?year=2024")
    assert response.status_code==200
    assert response.json()["display_start"]=="2024-01-01"
    result=run_tool("get_city_monthly_trends",{"region_id":"seoul","year":2024},
                    {"region_ids":["seoul"],"date_start":"2025-12-01","date_end":"2025-12-31"})
    assert result["selected_year"]==2024
    assert result["scope"]=="single_city_longitudinal"
    assert "error" in run_tool("get_city_monthly_trends",{"region_id":"daejeon","year":2024},{"region_ids":["seoul"]})

def test_monthly_dedup_dates_and_same_month_return():
    frame=pd.DataFrame([
        {"순번":"1","시작 대여소":"A","반납 대여소":"B","대여시간":"2025-01-31 23:59:00","반납시간":"2025-02-01 00:05:00","주행시간":"6","환승 유무":"N"},
        {"순번":"1","시작 대여소":"A","반납 대여소":"B","대여시간":"2025-01-31 23:59:00","반납시간":"2025-02-01 00:05:00","주행시간":"6","환승 유무":"N"},
        {"순번":"2","시작 대여소":"A","반납 대여소":"B","대여시간":"2025-01-01 12:00:00","반납시간":"2025-01-01 11:00:00","주행시간":"-60","환승 유무":"N"},
    ])
    months={}
    accumulate(frame,"sejong",months,{})
    row=months["2025-01"]
    assert sum(row["rentals"].values())==1
    assert sum(row["returns"].values())==0
    assert row["duplicate_rows"]==1
    assert row["excluded_rows"]==1
    assert set(row["days"])=={"2025-01-31"}

def test_fingerprint_dedup_across_chunks():
    frame=pd.DataFrame([{"대여일시":"2025-12-01 12:00:00","반납일시":"2025-12-01 12:05:00",
        "이용시간(분)":"5","대여_대여소ID":"A","반납_대여소ID":"B","대여_대여소명":"가","반납_대여소명":"나"}])
    months,seen={},{}
    accumulate(frame,"daejeon",months,seen)
    accumulate(frame,"daejeon",months,seen)
    assert months["2025-12"]["rentals"]["A"]==1
    assert months["2025-12"]["duplicate_rows"]==1

def test_anchor_or_rule_and_unknown_endpoint_count():
    rows=[]
    for a,b in [("A","B"),("B","A"),("B","X")]:
        rows.append({"순번":str(len(rows)),"시작 대여소":a,"반납 대여소":b,
         "대여시간":"2025-01-01 12:00:00","반납시간":"2025-01-01 12:05:00","주행시간":"5","환승 유무":"N"})
    months={}
    accumulate(pd.DataFrame(rows),"sejong",months,{},near={"A"},known={"A","B"})
    assert months["2025-01"]["linked_count"]==2
    assert months["2025-01"]["unknown_count"]==1

def test_default_scope_exposes_all_available_months():
    for city,count,start,end in [("seoul",12,"2025-01-01","2025-12-31"),("daejeon",27,"2024-08-01","2026-10-31"),("sejong",72,"2020-01-01","2025-12-31")]:
        result=monthly_trends.read(city)
        assert result["selected_year"]==0
        assert len(result["months"])==count
        assert result["display_start"]==start and result["display_end"]==end
        assert result["summary"]["rental_count"]==sum(m["rental_count"] for m in result["months"])
        assert sum(h["count"] for h in result["summary"]["hourly"])==result["summary"]["rental_count"]
        assert monthly_trends.read(city,2025)["available_month_count"]==count

def test_common_scope_only_uses_three_december_rows():
    result=monthly_trends.read("all")
    assert result["scope"]=="common_comparison"
    assert len(result["months"])==3
    assert {r["month"] for r in result["months"]}=={"2025-12"}
    assert result["summary"]["rental_count"]==2487201
    assert result["summary"]["month_count"]==1
    assert result["summary"]["observed_days"]==31
    assert result["summary"]["daily_average"]==2487201/31
    assert TestClient(app).get("/api/regions/all/monthly-trends").status_code==200

def test_static_views_match_live_readers_and_react_copy():
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    for city in ("all","seoul","daejeon","sejong"):
        prepared=root/"frontend/public/assets/bike-link/usage"/(city+".json")
        react=root/"frontend/public/assets/bike-link/usage"/(city+".json")
        assert prepared.read_bytes()==react.read_bytes()
        payload=json.loads(prepared.read_text())
        assert payload["views"]["all"]==monthly_trends.read(city)
