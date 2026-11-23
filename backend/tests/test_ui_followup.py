"""Additional experiments stay separately dated in the Solar tool evidence."""
from backend.research import presentation as p

def test_method_tool_includes_separate_experiment_without_replacing_reference(monkeypatch):
    support={"available":True,"period_start":"2025-12-01","period_end":"2025-12-31",
             "scope_note":"December","revision":"fixture","limitations":[],"followup_available":False,
             "cities":[{"demand_matrix":{"available":False},"backtest":[]}],
             "recovery_evaluation":{"available":True,"evaluation_period_start":"2025-07-01","cities":[{"city":"seoul"}]}}
    monkeypatch.setattr(p,"read_support",lambda city:support)
    monkeypatch.setattr(p.precomputed,"read",lambda *a:{"sources":[]})
    value=p.tool_report("seoul")
    assert value["period_start"]=="2025-12-01"
    assert value["separate_method_experiment"]["evaluation_period_start"]=="2025-07-01"
    assert "대체하지" in value["separate_experiment_note"]
    value["separate_method_experiment"]["cities"].clear()
    assert len(support["recovery_evaluation"]["cities"])==1

def test_monthly_tool_defaults_to_all_verified_years():
    from backend.presentation.monthly_trends import read
    for city,minimum in (("daejeon",27),("sejong",72)):
        result=read(city)
        assert result["available"] and result["selected_year"]==0
        assert result["summary"]["month_count"]>=minimum

def test_old_reference_guard_still_rejects_summer_as_service_period(monkeypatch):
    monkeypatch.setattr(p,"read_support",lambda *a: (_ for _ in ()).throw(AssertionError("wrong period read")))
    assert not p.tool_report("seoul","2025-07-01","2025-07-31")["available"]
