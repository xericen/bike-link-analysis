from backend.tests.local_requirements import requires_local_files, requires_local_inputs
"""Independent small exact solutions, resampling invariants, factual citation checks and live prepared scopes."""
import itertools,json,math
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.research import advanced_methods as a,advanced_presentation as p
from backend.main import app
from backend.agents.solar import run_tool
from scripts.validate.evaluate_advanced_solar import score

def test_mclp_matches_exhaustive_and_beats_greedy_counterexample(tmp_path):
    covers=[[0,1],[0,2],[1],[2]];weights=[6,6,5,5]
    row=a.compare(covers,weights,3,2,tmp_path/"solve.log")
    optimum=max(a.covered(s,covers,weights) for s in itertools.combinations(range(3),2))
    assert row["solver"]["proven_optimal"]
    assert row["solver"]["objective"]==optimum==22
    assert row["methods"]["score"]["covered"]==17
    assert row["methods"]["greedy"]["covered"]==17
    assert row["methods"]["score"]["optimal_fraction"]==17/22

def test_cover_demand_is_counted_once_and_budget_is_exact(tmp_path):
    row=a.mclp([[0,1]],[10],2,2,tmp_path/"duplicate.log")
    assert row["objective"]==10
    assert len(set(row["selected"]))==2
    assert row["proven_optimal"]

def test_pulp_optimal_label_without_cbc_proof_is_not_called_optimal(tmp_path,monkeypatch):
    import pulp
    def fake(self,solver):
        for v in self.variables():v.varValue=1 if v.name in {"site_0","covered_0"} else 0
        self.status=pulp.LpStatusOptimal;self.sol_status=pulp.LpSolutionIntegerFeasible
        Path(solver.optionsDict["logPath"]).write_text("Result - Stopped on time limit\nUpper bound: 10\n")
    monkeypatch.setattr(pulp.LpProblem,"solve",fake)
    row=a.compare([[0],[1]],[5,4],2,1,tmp_path/"timeout.log")
    assert not row["solver"]["proven_optimal"]
    assert row["methods"]["score"]["optimal_fraction"] is None

@pytest.mark.parametrize("weights,count,k", [([-1],1,1),([float('nan')],1,1),([1],1,2)])
def test_invalid_optimization_inputs_rejected(weights,count,k,tmp_path):
    with pytest.raises(ValueError):a.mclp([[0]],weights,count,k,tmp_path/"invalid.log")

def test_bootstrap_uses_ratio_of_sums_and_is_reproducible():
    a1=a.block_ci([1,90],[10,100],replicates=100,block=1)
    a2=a.block_ci([1,90],[10,100],replicates=100,block=1)
    assert a1==a2 and a1["estimate"]==91/110
    assert a1["estimate"]!=.5

def test_calendar_bootstrap_preserves_month_composition_and_never_bridges_gaps():
    dates=["2025-01-01","2025-01-02","2025-01-03","2025-01-10","2025-01-11","2025-01-12","2025-02-01","2025-02-02"]
    result=a.calendar_ci(dates,[2]*6+[8]*2,[10]*8,replicates=100,block=7)
    assert result["month_strata"]==2 and result["actual_block_min"]==2
    assert result["lower"]==result["upper"]==28/80
    assert result["observed_days"]==8

@pytest.mark.parametrize("change",[{"unit":"km2"},{"period":"wrong"},{"value":11},{"field":"invented"}])
def test_numeric_coincidence_does_not_validate_wrong_field_unit_or_period(change):
    truth={"area":{"value":10.,"unit":"m2","period":"P"}}
    claim={"field":"area","value":10.,"unit":"m2","period":"P",**change}
    assert a.typed_claims([claim],truth)["unsupported_count"]==1

def test_explicit_citation_value_and_field_schema_are_separate():
    truth={"area":{"value":10.,"unit":"m2","period":"P"}}
    r=score(json.dumps({"claims":[{"field":"추가 면적","evidence":"area","value":10.,"unit":"m2","period":"P"}]}),truth)
    assert r["citation_rate"]==1 and r["answer_coverage"]==1
    assert r["schema_field_match_rate"]==0 and r["grounded_claim_rate"]==0
    assert r["factual_unsupported_count"]==0 and r["unverified_separation_rate"] is None
    r=score(json.dumps({"claims":[{"field":"추가 면적","evidence":"area","value":10.,"unit":"km2","period":"P"}]}),truth)
    assert r["citation_rate"]==0

@pytest.mark.parametrize("city",["seoul","daejeon","sejong"])
@requires_local_inputs("docs/advanced-research-20261123/results.json")
def test_prepared_scopes_do_not_recompute_or_mix_dates(city,monkeypatch):
    monkeypatch.setattr(a,"compare",lambda *a,**k:pytest.fail("runtime optimization"))
    full=p.read(city,"individual");common=p.read(city,"common")
    assert full["scope"]=="individual" and common["period_start"]=="2025-12-01"
    assert full["period_start"]!="2025-12-01"
    with pytest.raises(HTTPException):p.read(city,"individual","2025-12-01","2025-12-31")
    with pytest.raises(HTTPException):p.read(city,"individual",end="1900-01-01")
    for row in full["cities"][0]["location"]["comparisons"]:
        for v in row["methods"].values():
            assert len(set(v["sites"]))==row["k"]
            assert v["gap_area_m2"]<=v["candidate_buffer_gross_m2"]+.01
        assert row["solver"]["proven_optimal"]
    context={"region_ids":[city],"date_start":full["period_start"],"date_end":full["period_end"]}
    tool=run_tool("get_advanced_research",{"region_id":city},context)
    assert tool["period_start"]==full["period_start"] and not tool["operational_update"]
    r=TestClient(app).get("/api/advanced-research",params={"city":city,"scope":"individual"})
    assert r.status_code==200 and r.json()["period_start"]==full["period_start"]

@requires_local_inputs("docs/advanced-research-20261123/results.json")
def test_whole_city_comparison_stays_common_and_benchmark_checks_every_run():
    report=p.read("all","common")
    assert len(report["cities"])==3
    assert report["headline_ci"]["total_trips"]==2487201
    with pytest.raises(HTTPException):p.read("all","individual")
    value=json.loads((p.ROOT/"docs/advanced-research-20261123/benchmark.json").read_text())
    assert len(value["runs"])==36 and value["all_checksums_match"]
    for n in (50000,250000,1000000):
        assert len({r["sha256"] for r in value["runs"] if r["rows"]==n})==1

def test_cached_reader_rechecks_changed_input_metadata(tmp_path,monkeypatch):
    source=tmp_path/"input";source.write_text("original")
    value=json.loads(p.FILE.read_text());value["inputs"]={str(source):{"size":source.stat().st_size,"mtime_ns":source.stat().st_mtime_ns}}
    packet=tmp_path/"results.json";packet.write_text(json.dumps(value))
    monkeypatch.setattr(p,"FILE",packet)
    p.read("all","common")
    source.write_text("changed size")
    with pytest.raises(HTTPException):p.read("all","common")

@pytest.mark.parametrize("bad",[{"field":[]},{"field":"area","evidence":[]}])
def test_malformed_model_reference_does_not_crash_evaluation(bad):
    r=score(json.dumps({"claims":[bad]}),{"area":{"value":1,"unit":"m2","period":"P"}})
    assert not r["parsed"] and r["answer_coverage"]==0
