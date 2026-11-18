import copy
import pytest
from backend.presentation.selection import selection_context
from backend.agents import solar

STATIONS=[{"region_id":"sejong","station_id":"SJ_1","station_name":"실제 fixture 대여소"}]
POOL=[{"site_id":"grid-1","station_id":"grid-1","kind":"신규 입지","rank":1,"potential_added_area_m2":123.456789}]
PLAN={"scenario_pool":POOL,"selection_states":[{"selected_ids":["grid-1"],"added_area_m2":123.456789,"overlap_area_m2":0,"increase_ratio":0.0123456789}],"precomputed":{"revision":"fixture"}}
def read(*args):return copy.deepcopy(PLAN)

def test_selection_is_resolved_from_stored_rows_not_browser_values():
    c=selection_context("sejong","2025-10-01","2025-10-31",{"station":STATIONS[0],"candidate_city":"sejong","candidate_ids":["grid-1"],"score":999},reader=read,stations=STATIONS)
    assert c["selected_station"]["station_id"]=="SJ_1"
    assert c["selected_candidates"][0]["potential_added_area_m2"]==123.456789
    assert c["selected_scenario"]["increase_ratio"]==0.0123456789
    assert "score" not in c["selected_candidates"][0]
    assert c["date_start"]=="2025-10-01"

@pytest.mark.parametrize("selection",[
    {"candidate_city":"sejong","candidate_ids":["unknown"]},
    {"candidate_city":"seoul","candidate_ids":["grid-1"]},
    {"station":{"region_id":"sejong","station_id":"invented"}},
    {"candidate_ids":"grid-1"},
    {"candidate_ids":["x"]*7},
])
def test_selection_rejects_missing_foreign_or_invalid_ids(selection):
    with pytest.raises(ValueError):selection_context("sejong","2025-10-01","2025-10-31",selection,reader=read,stations=STATIONS)

def test_all_scope_includes_sejong_common_month():
    c=selection_context("all","2025-12-01","2025-12-31",stations=[])
    assert c["region_ids"]==["seoul","daejeon","sejong"]
    selected=selection_context("all","2025-12-01","2025-12-31",{"station":STATIONS[0]},stations=STATIONS)
    assert selected["selected_station"]["region_id"]=="sejong"

def test_station_tools_use_selected_station_and_period(monkeypatch):
    got={}
    monkeypatch.setattr(solar.real_data,"region_stations",lambda *a:got.update(args=a) or [{"station_id":"ST-919"}])
    monkeypatch.setattr(solar.real_data,"clusters",lambda *a:{"clusters":[]})
    monkeypatch.setattr(solar.real_data,"source_meta",lambda *a:{})
    monkeypatch.setattr(solar.real_data,"observed_dates",lambda *a:["2026-10-01"])
    c={"region_ids":["seoul","daejeon"],"date_start":"2026-10-01","date_end":"2026-10-31",
       "selected_station":{"region_id":"seoul","station_id":"ST-919"}}
    result=solar.run_tool("get_station_details",{"region_id":"daejeon","station_id":"wrong"},c)
    assert "error" not in result
    assert result["station"]["station_id"]=="ST-919"
    assert got["args"]==("seoul","2026-10-01","2026-10-31")
