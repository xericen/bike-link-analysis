"""Per-city full histories never silently substitute common-month results."""
import pytest
from backend.research import individual_recovery as i,presentation as p,method_validation as m

def test_full_history_reader_returns_actual_periods_and_no_december_replacement():
    if not (i.OUT/"summary.json").exists() or not (m.ROOT/"data/individual/seoul/analysis.sqlite").exists():pytest.skip("full-history artifact absent")
    expected={"seoul":("2025-01-01","2025-12-31"),"daejeon":("2024-08-01","2026-10-31"),"sejong":("2020-01-01","2025-12-31")}
    for city,(start,end) in expected.items():
        r=i.read(city)
        assert r["available"] and (r["period_start"],r["period_end"])==(start,end)
        assert r["summary"]["whole_city"] and r["scope"]=="individual_full"
        assert not i.read(city,"2025-02-01","2025-03-31")["available"]
    assert not i.read("all")["available"]

def test_tool_uses_selected_full_history_without_reading_common_support(monkeypatch):
    if not (m.ROOT/"data/individual/seoul/analysis.sqlite").exists():pytest.skip("private source absent")
    monkeypatch.setattr(p,"read_support",lambda *a:pytest.fail("common month read"))
    result=p.tool_report("sejong","2020-01-01","2025-12-31")
    assert result["available"] and result["scope"]=="individual_full"
    assert result["period_start"]=="2020-01-01"
    assert "source_names" in result and "matrix" not in result

def test_full_scope_report_does_not_claim_unprovided_transit_demand_algorithm():
    from backend.agents import solar
    result={"available":True,"city":"seoul","scope":"individual_full",
            "period_start":"2025-01-01","period_end":"2025-12-31",
            "summary":{"strict":{"hits":1},"diagnostic":{"hits":2}}}
    r=solar._report("full","facts",[{"tool":"get_method_validation","arguments":{"region_id":"seoul"},"result":result}])
    assert "city median demand quadrants" not in r["algorithms"]
    assert any(f["value"]==1 and "전체 기간" in f["label"] for f in r["key_findings"])
