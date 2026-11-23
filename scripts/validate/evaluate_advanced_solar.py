"""Replay real prior responses; optional bounded paired live Solar rendering evaluation."""
import argparse,json,os,re,time
from pathlib import Path
from datetime import datetime,timezone
from backend.agents.solar_checks import numeric_grounding
from backend.research.advanced_methods import typed_claims
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/advanced-research-20261123"
def parse(text):
    try:return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$","",text.strip()))
    except (TypeError,ValueError):return None

def score(text,truth):
    obj=parse(text)
    if not isinstance(obj,dict):return {"parsed":False,"answer_coverage":0.,"claim_count":0,"numeric_match_rate":None,"citation_rate":None,"unverified_separation_rate":None,"error":"JSON parse failed"}
    submitted=obj.get("claims",[])
    if not isinstance(submitted,list) or any(not isinstance(c,dict) for c in submitted):return {"parsed":False,"error":"claims shape","answer_coverage":0.}
    if any(not isinstance(c.get("field"),str) or (c.get("evidence") is not None and not isinstance(c.get("evidence"),str)) for c in submitted):return {"parsed":False,"error":"field/evidence must be strings","answer_coverage":0.}
    judged=typed_claims(submitted,truth)
    # Check citation content against the exact field, period and unit, not merely the presence of a tag.
    cited=typed_claims([{**c,"field":c.get("evidence")} for c in submitted],truth)
    citations=cited["supported_count"]
    unsupported=[c for c,ref in zip(judged["claims"],cited["claims"]) if not c["supported"] and not ref["supported"]]
    held=sum(c.get("verification")=="unverified" for c in unsupported)
    numeric=numeric_grounding(text,[{"result":{"facts":truth,"prespecified_request_k":3}}])
    presented={c.get("field") for c in judged["claims"] if c["supported"]} | {c.get("field") for c in cited["claims"] if c["supported"]}
    return {**judged,"parsed":True,"answer_coverage":len(presented)/len(truth),
       "citation_rate":citations/len(submitted) if submitted else None,
       "cited_value_match_rate":citations/len(submitted) if submitted else None,
       "schema_field_match_rate":sum(c.get("field") in truth for c in submitted)/len(submitted) if submitted else None,
       "unverified_separation_rate":held/len(unsupported) if unsupported else None,
       "factual_unsupported_count":len(unsupported),
       "strict_schema_unsupported_count":judged["unsupported_count"],
       "numeric_match_rate":numeric["matched_numeric_tokens"]/numeric["checked_numeric_tokens"] if numeric["checked_numeric_tokens"] else None,
       "numeric_check":numeric,"free_statements_outside_typed_audit":len(obj.get("unverified_statements",[])) if isinstance(obj.get("unverified_statements",[]),list) else None,
       "limitation":"보류율은 정답표 범위의 구조화된 미검증 주장만 평가. 자유 서술 전체의 사실성·분류 정확도는 별도 검토 필요."}

def replay():
    path=ROOT/"data/processed/research/solar-paired-evaluation.json"
    old=json.loads(path.read_text());rows=[]
    units={"candidate_count":"개","top_station_id":"ID","top_rentals":"건","top_anchor_distance_m":"m","linked_trip_share":"ratio"}
    for case in old["cases"]:
        period=case["period_start"]+"~"+case["period_end"]
        truth={c["field"]:{"value":c["expected"],"unit":units[c["field"]],"period":period} for c in case["tool_assisted"]["evaluation"]["checks"]}
        for method in ("baseline","tool_assisted"):
            answer=case[method]["answer"];parsed=parse(answer)
            facts=(parsed or {}).get("facts",{})
            claims=[{"field":k,"value":v,"unit":units[k],"period":period,"evidence":k if method=="tool_assisted" else None} for k,v in facts.items() if k in units and v is not None]
            converted={"claims":claims,"unverified_statements":(parsed or {}).get("narrative_claims",[])}
            result=score(json.dumps(converted,ensure_ascii=False),truth)
            result["citation_rate"]=None # Old protocol did not ask model for explicit citations.
            result["citation_evaluable"]=False
            rows.append({"city":case["city"],"method":method,"period":period,"evaluation":result,"original_answer":answer})
    return {"source":str(path.relative_to(ROOT)),"recorded_at":old.get("recorded_at"),"conditions":"existing archived live paired experiment; no new inference repetitions","cases":rows}
def run(live=False,max_calls=0,repeats=2):
    OUT.mkdir(parents=True,exist_ok=True)
    result={"available":True,"replay":replay(),"live":{"executed":False,"calls":[],"cases":[]},"built_at":datetime.now(timezone.utc).isoformat()}
    # Known field/unit/period counterexamples measure the detector, separately from model prose.
    truth={"area":{"value":100.25,"unit":"m2","period":"2025-01~12"}}
    controlled=[]
    for kind,change in [("wrong_value",{"value":200.25}),("wrong_unit",{"unit":"km2"}),("wrong_period",{"period":"2024-01~12"}),("invented_field",{"field":"future_bike_gain"})]:
        claim={"field":"area","value":100.25,"unit":"m2","period":"2025-01~12","verification":"unverified",**change}
        controlled.append({"case":kind,"evaluation":score(json.dumps({"claims":[claim]}),truth)})
    result["controlled_counterexamples"]=controlled
    existing=OUT/"agent-evaluation.json"
    if existing.exists() and not live:
        saved=json.loads(existing.read_text())
        result["live"]=saved.get("live",result["live"])
        result["rescored_at"]=datetime.now(timezone.utc).isoformat()
        for case in result["live"].get("cases",[]):
            if "answer" in case and "truth" in case:case["evaluation"]=score(case["answer"],case["truth"])
    if live:
        if max_calls<3*2*repeats:raise ValueError("Budget smaller than prespecified paired design")
        from dotenv import load_dotenv
        from openai import OpenAI
        from backend.research.advanced_presentation import read
        load_dotenv(ROOT/".env")
        if not os.getenv("UPSTAGE_API_KEY"):
            result["live"]["reason"]="UPSTAGE_API_KEY未設定"
        else:
            client=OpenAI(api_key=os.environ["UPSTAGE_API_KEY"],base_url="https://api.upstage.ai/v1",timeout=45,max_retries=0)
            model=os.getenv("UPSTAGE_MODEL","solar-mini4")
            result["live"].update(executed=True,model=model,repeats=repeats,max_calls=max_calls,design="3 cities x 2 conditions x repetitions; real stored-tool facts supplied, renderer evaluation, not autonomous tool-selection evaluation")
            system='공공자전거 연구 보고서 평가입니다. JSON만 반환하세요. 형식: {"claims":[{"field":"...","value":0,"unit":"...","period":"...","evidence":"field명","verification":"verified"}],"unverified_statements":[]}. 제공된 근거에서 확인한 주장만 claims에 넣고 수치·단위·기간을 그대로 복사하세요. 근거가 없으면 claims는 빈 배열로 두고 확인 불가를 unverified_statements에 쓰세요. 미래 설치효과·실제 환승을 추측하지 마세요.'
            for city in ("seoul","daejeon","sejong"):
                value=read(city,"individual");data=value["cities"][0];period=data["period_start"]+"~"+data["period_end"]
                row=next(c for c in data["location"]["comparisons"] if c["objective"]=="gap_area" and c["k"]==3)
                truth={"score_area":{"value":row["methods"]["score"]["gap_area_m2"],"unit":"m2","period":period},
                  "optimized_area":{"value":row["methods"]["mclp"]["gap_area_m2"],"unit":"m2","period":period},
                  "score_fraction":{"value":row["methods"]["score"]["optimal_fraction"],"unit":"ratio","period":period}}
                for repeat in range(repeats):
                    for condition in ("baseline","grounded"):
                        question=city+" "+period+"에서 K=3 점수순 추가 면적, MCLP 추가 면적, 점수순의 최적해 대비 비율을 알려주세요."
                        if condition=="grounded":question+="\n서버의 실제 저장 도구 결과: "+json.dumps(truth,ensure_ascii=False)
                        started=time.perf_counter()
                        try:
                            response=client.chat.completions.create(model=model,messages=[{"role":"system","content":system},{"role":"user","content":question}],temperature=0,max_tokens=700)
                            text=response.choices[0].message.content or ""
                            usage=response.usage.model_dump() if response.usage else None
                            item={"city":city,"condition":condition,"repeat":repeat,"period":period,"answer":text,"truth":truth,"evaluation":score(text,truth),"finish_reason":response.choices[0].finish_reason,"seconds":time.perf_counter()-started}
                            result["live"]["calls"].append({"city":city,"condition":condition,"usage":usage})
                            result["live"]["cases"].append(item)
                        except Exception as error:
                            result["live"]["calls"].append({"city":city,"condition":condition,"error_type":type(error).__name__})
                            result["live"]["cases"].append({"city":city,"condition":condition,"repeat":repeat,"error_type":type(error).__name__,"evaluation":{"parsed":False,"answer_coverage":0.}})
                        (OUT/"agent-evaluation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    result["limitations"]=["숫자 토큰 일치는 문장 의미의 보증이 아님","기존 응답의 인용률은 당시 출력 형식상 측정 불가","새 평가의 근거 조건은 실제 도구 사실을 제공한 렌더러 평가이며 자율 도구 선택 성능은 별도","2회 반복은 소규모 확인이며 통계적 우월성 검정이 아님","정확한 field ID 준수와 명시적 evidence 경로의 값/단위/기간 일치는 별도 지표. 한국어 field 라벨을 임의 정답 처리하지 않음","수치 토큰 대조에는 질문의 사전 지정 K=3도 포함"]
    (OUT/"agent-evaluation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print("READY evaluation",len(result["live"]["calls"]),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--live",action="store_true");p.add_argument("--max-calls",type=int,default=0);p.add_argument("--repeats",type=int,default=2);args=p.parse_args();run(args.live,args.max_calls,args.repeats)
