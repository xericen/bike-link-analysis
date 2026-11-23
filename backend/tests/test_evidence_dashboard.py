from backend.tests.local_requirements import requires_local_files, requires_local_inputs
"""New evidence is visible without mixing periods or turning observations into effects."""
import json
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.research.conclusion import read,tool
from backend.research import evidence_dashboard as dashboard
from scripts.validate.seoul_transfer_journeys import seconds,solve
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/visibility-20261123"
@pytest.mark.parametrize("city,total",[("all",65072555),("seoul",37176546),("daejeon",14992420),("sejong",12903589)])
@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_evidence_matches_selected_city_and_independent_periods(city,total):
    r=read(city);d=r["evidence_dashboard"]
    assert d["spark"]["valid_total"]==total and d["spark"]["matched"]==d["spark"]["city_count"]
    assert sum(s["raw_rows"]-s["excluded_rows"]-s["duplicate_rows"] for s in d["spark"]["rows"])==total
    assert d["solar"]["correct"]==d["solar"]["case_count"] and d["solar"]["case_count"]>0
    assert sum(x["count"] for x in d["solar"]["categories"])==d["solar"]["case_count"]
    assert all(x["label"] for x in d["solar"]["categories"])
    assert len(d["transfer_sensitivity_rows"])==(18 if city in {"all","seoul"} else 0)
    assert all(s["city"]==city for s in d["spark"]["rows"]) if city!="all" else len(d["spark"]["rows"])==3
    assert bool(d["seoul_transfer_rows"])==(city in {"all","seoul"})
    assert bool(d["opening"])==(city in {"all","seoul"})
    assert not d["operational_update"] and not d["field_verified"]
@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_technical_dashboard_does_not_expand_paid_agent_payload_or_replace_common_dates():
    assert "evidence_dashboard" not in tool("seoul")
    r=read("all")
    assert r["scope"]=="common_multi_month" and len(r["comparison"])==10
    assert r["evidence_dashboard"]["seoul_transfer"]["reference_date"]=="2025-09-30"
    assert not r["evidence_dashboard"]["seoul_transfer"]["historical_december_validated"]
def test_opening_cohort_exclusions_and_observation_formula():
    r=json.loads((OUT/"opening-events.json").read_text())
    assert r["raw_2025_opening_count"]==r["opening_2025_mapped_count"]+len(r["unmatched_openings"])==67
    assert r["opening_2025_mapped_count"]==r["eligible_count"]+len(r["excluded"])
    assert r["eligible_count"]==len(r["all_events"])==55
    assert [x["event_date"] for x in r["examples"]]==sorted(x["event_date"] for x in r["all_events"])[:3]
    for x in r["all_events"]:
        assert not x["causal_effect_verified"] and x["coverage_before_days"]>=21 and x["coverage_after_days"]>=21
        assert abs((pd.Timestamp(x["first_trip_date"])-pd.Timestamp(x["installed_at"])).days)<=14
        assert .5<=x["control_pre_daily"]/x["pre_daily_rentals"]<=2
        assert (pd.Timestamp(x["before_end"])-pd.Timestamp(x["before_start"])).days==27
        assert (pd.Timestamp(x["after_end"])-pd.Timestamp(x["event_date"])).days==27
        assert x["difference_in_changes_daily"]==pytest.approx((x["post_daily_rentals"]-x["pre_daily_rentals"])-(x["control_post_daily"]-x["control_pre_daily"]))
    assert any(x["difference_in_changes_daily"]<0 for x in r["examples"]) and any(x["difference_in_changes_daily"]>0 for x in r["examples"])
@requires_local_files("data/raw/visibility-20261123/seoul-timetable-20250930.csv")
def test_transfer_train_ids_and_times_exist_in_actual_official_source():
    f=pd.read_csv(ROOT/"data/raw/visibility-20261123/seoul-timetable-20250930.csv",dtype=str)
    f=f[(f.WEEKTAG=="DAY")&(f.GUBHANG=="0")]
    departures={(r.LINE,r.TRAIN_NO,r.INOUTTAG,r.SI_ID,seconds(r.EDT)) for r in f.itertuples(index=False)}
    arrivals={(r.LINE,r.TRAIN_NO,r.INOUTTAG,r.SI_ID,seconds(r.STT)) for r in f.itertuples(index=False)}
    r=json.loads((OUT/"seoul-transfer-journeys.json").read_text())
    assert len(r["examples"])==2 and r["missing_week_tag_rows"]==109481
    for e in r["examples"]:
        for pair in e["pairs"]:
            a,b=pair["before"],pair["after"]
            assert a["origin_departure_s"]==b["origin_departure_s"]
            assert pair["gain"]==pytest.approx(a["total_minutes"]-b["total_minutes"])
            for trip in (a,b):
                assert trip["transfers"]==1 and trip["transfer_wait_minutes"]>=0
                assert trip["total_minutes"]==pytest.approx(sum(trip[k] for k in ("access_minutes","entry_minutes","first_wait_minutes","rail_minutes","transfer_walk_minutes","transfer_wait_minutes","exit_minutes")))
                for leg in trip["legs"]:
                    assert (leg["line"],leg["train_id"],leg["direction"],leg["origin_station_code"],leg["departure_s"]) in departures
                    assert (leg["line"],leg["train_id"],leg["direction"],leg["destination_station_code"],leg["arrival_s"]) in arrivals
def test_waiting_constraints_and_late_service_hours_are_explicit():
    assert seconds("25:01:30")==90090 and seconds("08:70:00") is None
    first=[{"departure_s":600,"arrival_s":900,"train_id":"fixture-a"}]
    second=[{"departure_s":960,"arrival_s":1200,"train_id":"fixture-b"},{"departure_s":1260,"arrival_s":1500,"train_id":"fixture-c"}]
    assert solve(0,0,first,second,transfer_minutes=1)["arrival_s"]<solve(0,0,first,second,transfer_minutes=5)["arrival_s"]
    assert not solve(1000,0,first,second)["available"]
@requires_local_inputs("docs/conclusion-20261123/results.json")
def test_existing_public_api_exposes_four_specific_blockers():
    r=TestClient(app).get("/api/conclusion?city=seoul")
    assert r.status_code==200
    d=r.json()["evidence_dashboard"]
    assert {b["key"] for b in d["blockers"]}=={"journeys","field","effects","solar"}
    assert all(b["done"] and b["reason"] and b["next"] for b in d["blockers"])
