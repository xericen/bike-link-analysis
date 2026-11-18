"""Paired Solar ablation: identical model, prompt and questions, tools as treatment."""
import json,os,re,math
from pathlib import Path
from datetime import datetime,timezone
from dotenv import load_dotenv
from openai import OpenAI
from backend.agents.solar import TOOLS,run_tool
from backend.services import precomputed
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"data/processed/research"
PROMPT="""공공자전거 분석가입니다. 확인할 수 없는 값은 null로 답하고 일반 상식으로 지역 수치를 만들지 마세요.
가능한 도구로 먼저 근거를 확인한 다음 JSON만 반환하세요.
형식: {"facts":{"candidate_count":null,"top_station_id":null,"top_rentals":null,"top_anchor_distance_m":null,"linked_trip_share":null},"narrative_claims":[]}
candidate_count는 앵커 500m 밖+실제 대여량 존재인 기존 대여소 수입니다.
top은 기존 개선 순위 1위입니다. linked_trip_share는 0~1 값입니다.
narrative_claims에는 위 다섯 필드 밖의 주장을 쓰되 근거 없는 주장을 만들지 마세요."""
def parse(text):
    try:return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$","",text.strip()))
    except (ValueError,TypeError):return None
def score(answer,truth):
    obj=parse(answer);facts=(obj or {}).get("facts",{});checks=[]
    for key,expected in truth.items():
        val=facts.get(key);provided=val is not None
        correct=provided and (val==expected if isinstance(expected,str) else type(val) in (int,float) and math.isclose(val,expected,rel_tol=1e-5,abs_tol=.1 if key=="top_anchor_distance_m" else 1e-5))
        checks.append({"field":key,"value":val,"expected":expected,"provided":provided,"correct":correct})
    n=sum(c["provided"] for c in checks);ok=sum(c["correct"] for c in checks)
    claims=(obj or {}).get("narrative_claims",[])
    return {"parsed":obj is not None,"provided_facts":n,"possible_facts":len(checks),"coverage":n/len(checks),"evidence_agreement":ok/n if n else None,
       "station_id_correct":next(c["correct"] for c in checks if c["field"]=="top_station_id"),
       "station_id_provided":facts.get("top_station_id") is not None,
       "unsupported_structured_claims":n-ok,"narrative_claims_outside_automatic_check":len(claims) if isinstance(claims,list) else 1,"checks":checks}
def run():
    load_dotenv(ROOT/".env");client=OpenAI(api_key=os.environ["UPSTAGE_API_KEY"],base_url="https://api.upstage.ai/v1",timeout=60,max_retries=0)
    model=os.getenv("UPSTAGE_MODEL","solar-mini4")
    inputs=json.loads((OUT/"decision-inputs.json").read_text());cases=[];calls=[]
    for city in ("seoul","daejeon","sejong"):
        x=inputs["cities"][city]
        precomputed.read("vulnerability",city,x["period_start"],x["period_end"])
        precomputed.read("transit_linkage",city,x["period_start"],x["period_end"])
    selected=[t for t in TOOLS if t["function"]["name"] in {"get_improvement_ranking","get_transit_linkage"}]
    def complete(messages,**kwargs):
        r=client.chat.completions.create(model=model,messages=messages,temperature=0,**kwargs)
        calls.append({"model":r.model,"usage":r.usage.model_dump() if r.usage else None,"finish_reason":r.choices[0].finish_reason})
        return r
    for city in ("seoul","daejeon","sejong"):
        x=inputs["cities"][city];top=x["ranking"][0]
        truth={"candidate_count":x["candidate_count"],"top_station_id":top["station_id"],"top_rentals":top["rental_count"],"top_anchor_distance_m":top["nearest_stop_distance_m"],"linked_trip_share":x["goal_metrics"]["linked_trip_share"]}
        question=f"{city}, {x['period_start']}~{x['period_end']} 기존 취약 후보 수, 개선 1위 대여소 ID·대여량·최근접 앵커 직선거리, 앵커300m 연계 OD 비중을 알려 주세요."
        base=[{"role":"system","content":PROMPT},{"role":"user","content":question}]
        final_instruction={"role":"system","content":"이제 도구를 더 호출하지 마세요. 내부 도구 문법을 출력하지 마세요. 현재 확보한 근거만으로 요청한 JSON 객체를 반환하세요. 확인하지 못한 값은 null입니다."}
        plain=complete(base+[final_instruction],max_tokens=700);plain_text=plain.choices[0].message.content or ""
        context={"region_ids":[city],"date_start":x["period_start"],"date_end":x["period_end"]}
        choice=complete(base,tools=selected,tool_choice="required",max_tokens=450)
        message=choice.choices[0].message;messages=base+[message.model_dump(exclude_none=True)];evidence=[]
        for call in message.tool_calls or []:
            args=json.loads(call.function.arguments)
            value=run_tool(call.function.name,args,context)
            if call.function.name=="get_improvement_ranking":
                compact={k:value.get(k) for k in ("available","candidate_count","ranking","city","period_start","period_end")};compact["ranking"]=(compact.get("ranking") or [])[:3]
            else:compact={k:value.get(k) for k in ("available","goal_metrics","period_start","period_end","city")}
            evidence.append({"tool":call.function.name,"arguments":args,"result":compact})
            messages.append({"role":"tool","tool_call_id":call.id,"content":json.dumps(compact,ensure_ascii=False)})
        final=complete(messages+[final_instruction],max_tokens=700);tool_text=final.choices[0].message.content or ""
        cases.append({"city":city,"question":question,"period_start":x["period_start"],"period_end":x["period_end"],
             "baseline":{"answer":plain_text,"evaluation":score(plain_text,truth)},"tool_assisted":{"answer":tool_text,"evaluation":score(tool_text,truth),"evidence":evidence}})
        print(city,"paired",cases[-1]["baseline"]["evaluation"]["provided_facts"],cases[-1]["tool_assisted"]["evaluation"]["provided_facts"],flush=True)
        (OUT/"solar-paired-evaluation.json").write_text(json.dumps({"status":"partial","cases":cases,"calls":calls},ensure_ascii=False,indent=2))
    result={"status":"completed","model":model,"temperature":0,"final_max_tokens":700,"system_prompt":PROMPT,"final_instruction":final_instruction,"recorded_at":datetime.now(timezone.utc).isoformat(),"cases":cases,"calls":calls,
      "limitations":["동일 Solar 모델의 도구 유무 제거 실험이며 모든 일반 LLM과의 비교가 아닙니다.","세 도시 질문 각 1회로 통계적 일반화 불가. 도구 조건은 근거 선택 추가 호출·토큰을 사용합니다.","미응답은 오류 대신 coverage로 평가합니다. 자유 서술은 자동 검증 범위 밖 주장 수이며 거짓 주장 수와 다릅니다.","운영 에이전트의 모든 자유 서술 정확성을 입증하지 않습니다."]}
    (OUT/"solar-paired-evaluation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":run()
