"""Regression coverage for real observed failures; no external API calls."""
import json
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from openai import APITimeoutError
from openai.types.chat import ChatCompletion
from backend.agents import solar, solar_audit
from backend.tests.test_api import fixture_data

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "docs/solar-verification-20261112/execution.json"

def evidence():
    return [{"tool":"get_region_overview","arguments":{"region_id":"seoul"},"initiator":"solar",
             "result":{"region_id":"seoul","region_name":"서울","total_rentals":15,"observed_dates":["2026-10-01","2026-10-02"],
                       "daily":[{"date":"2026-10-01","rental_count":5},{"date":"2026-10-02","rental_count":10}],"sources":[]}}]

def test_actual_wrong_extremum_is_withheld():
    old = json.loads(OLD.read_text())["questions"][0]["response"]
    result = solar.finalize_answer("원 질문", old["answer"], old["evidence"], old["analysis_context"])
    assert result["answer_basis"] == "tool_summary"
    assert not result["semantic_validation"]["passed"]
    assert "2026-10-02" in result["answer"] and "166657" in result["answer"]

@pytest.mark.parametrize("answer,passed",[
    ("일별 최대는 2026-10-02의 10건입니다.",True),
    ("2026-10-01이 5건으로 가장 적고, 2026-10-02가 10건으로 가장 많습니다.",True),
    ("일별 최대는 2026-10-01의 5건입니다.",False),
    ("일별 최대는 2026-10-01의 10건입니다.",False),
    ("일별 최소는 2026-10-02의 5건입니다.",False),
    ("일별 최대 날짜는 확인하지 못했습니다.",False)])
def test_extremum_claim_date_and_value(answer, passed):
    result = solar.finalize_answer("질문",answer,evidence())
    assert result["semantic_validation"]["passed"] is passed

def test_tied_extrema():
    calls = evidence()
    calls[0]["result"]["daily"][0]["rental_count"] = 10
    result = solar.finalize_answer("질문","일별 최대는 2026-10-01의 10건입니다.",calls)
    assert result["semantic_validation"]["passed"]

def test_actual_day_count_no_false_rejection_and_fallback_has_counts():
    old = json.loads(OLD.read_text())["questions"][3]["response"]
    result = solar.finalize_answer("상세",old["solar_answer"],old["evidence"],old["analysis_context"])
    assert result["grounding_validation"]["passed"]
    assert result["answer_basis"] == "solar_interpretation"
    assert "926" in result["answer"] and "1322" in result["answer"]
    fallback = solar.finalize_answer("상세","999999건",old["evidence"],old["analysis_context"])
    assert fallback["answer_basis"] == "tool_summary"
    assert all(value in fallback["answer"] for value in ("926","1322","31"))

def test_days_do_not_whitelist_unobserved_count_or_strip_negative_sign():
    calls = evidence()
    assert solar._numeric_grounding("2일 관측",calls)["passed"]
    assert not solar._numeric_grounding("31일 관측",calls)["passed"]
    assert not solar._numeric_grounding("-5건",calls)["passed"]
    assert not solar._numeric_grounding("999건",calls)["passed"]

def completion(tool=False):
    message = {"role":"assistant","content":None if tool else "총 15건입니다."}
    if tool:
        message["tool_calls"]=[{"id":"call-1","type":"function","function":{"name":"get_region_overview","arguments":'{"region_id":"seoul"}'}}]
    return ChatCompletion.model_validate({"id":"reply-1","model":"solar-test","created":0,"object":"chat.completion",
        "choices":[{"index":0,"message":message,"finish_reason":"tool_calls" if tool else "stop"}],
        "usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}})

def setup_client(monkeypatch,tmp_path,steps):
    monkeypatch.setenv("UPSTAGE_API_KEY","test-credential-never-log")
    monkeypatch.setattr(solar_audit,"AUDIT_DIR",tmp_path)
    captured=[]
    def create(**kwargs):
        captured.append(kwargs)
        step = steps.pop(0)
        if isinstance(step,Exception):
            raise step
        return SimpleNamespace(status_code=200,parse=lambda:step)
    fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(with_raw_response=SimpleNamespace(create=create))))
    monkeypatch.setattr(solar,"OpenAI",lambda **kwargs:fake)
    monkeypatch.setattr(solar,"run_tool",lambda *args:evidence()[0]["result"])
    return captured

def timeout():
    return APITimeoutError(request=httpx.Request("POST","https://api.upstage.ai/v1/chat/completions"))

def test_final_timeout_preserves_tool_result_known_tokens_and_unknown_billing(monkeypatch,tmp_path):
    setup_client(monkeypatch,tmp_path,[completion(True),timeout()])
    result=solar.chat("조회")
    assert result["llm_status"]=="incomplete" and result["answer_basis"]=="tool_summary"
    assert "15" in result["answer"] and result["evidence"][0]["initiator"]=="solar"
    assert result["usage"]["total_tokens"]==12 and not result["usage_complete"]
    assert result["provider_calls"][1]["state"]=="failed"
    assert result["provider_calls"][1]["usage"] is None
    rows=[json.loads(line) for p in tmp_path.glob("*.jsonl") for line in p.read_text().splitlines()]
    assert [x["state"] for x in rows]==["pending","completed","pending","failed"]
    assert all("test-credential-never-log" not in json.dumps(row) for row in rows)

def test_selection_timeout_returns_audit_without_invented_usage(monkeypatch,tmp_path):
    setup_client(monkeypatch,tmp_path,[timeout()])
    with pytest.raises(HTTPException) as exc:
        solar.chat("조회")
    assert exc.value.status_code==504
    assert exc.value.detail["usage"]["total_tokens"]==0
    assert not exc.value.detail["usage_complete"]
    assert exc.value.detail["billing_status"]=="unknown_for_unreported_calls"
    assert exc.value.detail["request_id"]

def test_success_has_two_http_responses_and_complete_usage(monkeypatch,tmp_path):
    captured=setup_client(monkeypatch,tmp_path,[completion(True),completion()])
    result=solar.chat("조회")
    assert result["usage_complete"] and result["usage"]["total_tokens"]==24
    assert [x["http_status"] for x in result["provider_calls"]]==[200,200]
    assert captured[0]["tool_choice"]=="required" and captured[1]["tool_choice"]=="none"

def test_pagerank_avoids_hidden_hubs_and_betweenness(fixture_data,monkeypatch):
    def forbidden(*args,**kwargs):
        pytest.fail("PageRank must not run hidden-hub/betweenness analysis")
    forbidden.cache_clear = lambda: None
    monkeypatch.setattr(real_data := solar.real_data,"hidden_hubs",forbidden)
    original=real_data.centrality
    def centrality(*args,**kwargs):
        assert kwargs["include_betweenness"] is False
        return original(*args,**kwargs)
    monkeypatch.setattr(real_data,"centrality",centrality)
    result=solar.run_tool("get_centrality_ranking",{"region_id":"seoul","metric":"pagerank","top_n":1})
    assert result["available"] and len(result["rankings"])==1
    assert result["rankings"][0]["pagerank"]>0
    assert result["rankings"][0]["betweenness"] is None

def test_hourly_extremum_cannot_reuse_non_extreme_counts():
    calls = [{"tool":"get_station_details","arguments":{},"result":{"available":True,
        "station":{"station_id":"ST-1","rental_count":5,"return_count":10,"hourly_net_outflow":[-5,3,2]}}}]
    assert not solar.finalize_answer("질문","2시가 2건으로 가장 큰 순유출입니다.",calls)["semantic_validation"]["passed"]
    assert solar.finalize_answer("질문","1시가 3건으로 가장 큰 순유출입니다.",calls)["semantic_validation"]["passed"]
    assert solar.finalize_answer("질문","0시가 5건으로 가장 큰 순유입입니다.",calls)["semantic_validation"]["passed"]
