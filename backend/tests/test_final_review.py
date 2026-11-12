"""Final-review regression checks; fixture-only data is never displayed."""
import pytest
from backend.services import periods, real_data
from backend.agents import solar
from backend.analysis.clustering import cluster_stations
from backend.tests.test_api import fixture_data

def test_date_limits_and_common_range(monkeypatch):
    monkeypatch.setattr(real_data,"observed_dates",lambda rid: {"seoul":["2026-10-01","2026-10-31"],
        "daejeon":["2025-12-01","2026-10-31"],"sejong":[]}[rid])
    assert periods.resolve("all") == ("2026-10-01","2026-10-31")
    with pytest.raises(ValueError): periods.resolve("all","2026-09-30","2026-10-31")
    with pytest.raises(ValueError): periods.resolve("seoul","2026-10-20","2026-10-01")
    assert periods.bounds("sejong")["available"] is False
    with pytest.raises(ValueError): periods.resolve("sejong","2026-10-01","2026-10-31")

def test_solar_date_and_city_context_pinned(monkeypatch):
    monkeypatch.setattr(real_data,"overview",lambda rid,start,end: {"region_id":rid,"period_start":start,"period_end":end,"map_stations":[]})
    context={"region_ids":["seoul"],"date_start":"2026-10-25","date_end":"2026-10-31"}
    result=solar.run_tool("get_region_overview",{"region_id":"seoul","date_range":{"date_start":"2020-01-01"}},context)
    assert result["period_start"] == "2026-10-25"
    assert result["period_end"] == "2026-10-31"
    assert "error" in solar.run_tool("get_region_overview",{"region_id":"daejeon"},context)

def test_small_numbers_and_unknown_station_are_checked():
    evidence=[{"result":{"station_id":"ST-1481","count":5,"peak_hour_share":.4091}}]
    assert not solar._numeric_grounding("7건",evidence)["passed"]
    assert solar._numeric_grounding("5건, 비중 40.91%",evidence)["passed"]
    assert not solar._station_grounding("ST-9999",evidence)["passed"]
    assert solar._station_grounding("ST-1481",evidence)["passed"]

def test_degenerate_cluster_is_explicit():
    rows=[{"station_id":str(i),"rental_count":24,"hourly":[1]*24,"weekend_share":None} for i in range(3)]
    result=cluster_stations(rows)
    assert result["available"] is False
    assert result["quality"] == "insufficient"

def test_history_does_not_escape_selected_dates(fixture_data):
    result=real_data.station_role_history("seoul","A","2026-10-29","2026-10-29")
    assert all(x["date_start"] >= "2026-10-29" for x in result["windows"])
    assert all(x["observed_day_count"] == 1 for x in result["windows"])
    assert all(x["confidence_warning"] for x in result["windows"])
    validation=real_data.hidden_hub_validation("seoul","A","2026-10-29","2026-10-29")
    assert all(not x["minimum_observation_pass"] for x in validation["windows"])

def test_unsupported_prose_is_withheld():
    evidence=[{"tool":"get_region_overview","arguments":{"region_id":"seoul"},
               "result":{"region_name":"서울","region_id":"seoul","total_rentals":5,"sources":[]}}]
    result=solar.finalize_answer("검증 질문","ST-9999에서 999건 개선됩니다.",evidence,
        {"region_ids":["seoul"],"date_start":"2026-10-01","date_end":"2026-10-31"})
    assert result["answer_basis"] == "tool_summary"
    assert "ST-9999" not in result["answer"]
    assert "ST-9999" in result["solar_answer"]
    assert result["report"]["key_findings"][0]["value"] == 5

def test_truncated_model_answer_is_withheld():
    evidence=[{"tool":"get_region_overview","arguments":{"region_id":"seoul"},
               "result":{"region_name":"서울","region_id":"seoul","total_rentals":5,"sources":[]}}]
    result=solar.finalize_answer("질문","5건으로...",evidence,finish_reason="length")
    assert result["answer_basis"] == "tool_summary"
    assert result["model_finish_reason"] == "length"
    assert result["solar_answer"] == "5건으로..."
