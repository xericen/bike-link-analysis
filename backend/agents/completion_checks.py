"""Conservative candidate-specific claim checks and bounded LLM payloads."""
import copy,json,math,re
def check(answer,evidence,context=None):
    known={}
    for e in evidence:
        r=e.get("result",{})
        if e.get("tool")=="get_project_conclusion":
            for city in r.get("cities",[]):
                for row in city.get("candidates",[]):known[row["site_id"]]=row
    failures=[];checked=0
    clauses=re.split(r"\n|(?<=[.!?])\s+",answer)
    for clause in clauses:
        mentions=[(m.start(),m.group()) for m in re.finditer(r"(?:grid|격자)-\d+-\d+",clause)]
        if not mentions:
            for sid,row in known.items():
                aliases=[];anchor=row.get("route",{}).get("anchor_name")
                if anchor and sum(v.get("route",{}).get("anchor_name")==anchor for v in known.values())==1:
                    aliases.extend(m.start() for m in re.finditer(re.escape(anchor),clause))
                rank=row.get("rank")
                if rank and sum(v.get("rank")==rank for v in known.values())==1:
                    aliases.extend(m.start() for m in re.finditer(r"(?<!\d)"+str(rank)+r"\s*순위",clause) if not re.search(r"검토|별도",clause[max(0,m.start()-8):m.start()]))
                if aliases:mentions.append((min(aliases),sid))
        mentions.sort()
        for index,(start,sid) in enumerate(mentions):
            if sid.startswith("격자-"):
                failures.append({"reason":"원본 후보 ID를 번역·변형함","candidate_id":sid})
                sid="grid-"+sid.partition("-")[2]
            local_clause=clause[start:mentions[index+1][0] if index+1<len(mentions) else len(clause)]
            checked+=1
            if sid not in known and known:
                failures.append({"reason":"근거에 없는 후보 ID","candidate_id":sid});continue
            row=known.get(sid)
            if not row:continue
            if re.search(r"주변\s*1\s*km|주변\s*1킬로|관측\s*대여",local_clause):
                values=re.findall(r"([\d,]+(?:\.\d+)?)\s*건",local_clause)
                for v in values:
                    checked+=1
                    if not math.isclose(float(v.replace(",","")),float(row["nearby_rentals_1000m"]),abs_tol=.5):
                        failures.append({"reason":"후보와 관측 대여량의 연결 불일치","candidate_id":sid,"claim":v})
            for number,unit in re.findall(r"면적(?:은|는|이|:)?\s*([\d,.]+)\s*(km²|km2|㎡|m²|m2)",local_clause):
                checked+=1
                expected=row.get("potential_added_area_m2")
                if expected is not None:
                    expected=expected/1000000 if unit in {"km²","km2"} else expected
                    decimals=len(number.split(".")[-1]) if "." in number else 0
                    if not math.isclose(float(number.replace(",","")),expected,abs_tol=.5*10**(-decimals)+1e-8):
                        failures.append({"reason":"후보와 면적 수치의 연결 불일치","candidate_id":sid})
            for number in re.findall(r"도보(?:로|시간|는|가|:)?\s*([-+]?[\d,.]+)\s*분",local_clause):
                expected=row.get("route",{}).get("before_minutes");decimals=len(number.split(".")[-1]) if "." in number else 0;checked+=1
                if expected is None or not math.isclose(float(number.replace(",","")),expected,abs_tol=.5*10**(-decimals)+1e-8):
                    failures.append({"reason":"도보 시간에 다른 지표 값을 사용함","candidate_id":sid})
            gain=row.get("route",{}).get("improvement_minutes")
            if gain is not None:
                for number,direction in re.findall(r"([-+]?[\d,.]+)\s*분.{0,12}?(느립니다|느리다|느리고|빠릅니다|빠르다|빠르고)",local_clause):
                    decimals=len(number.split(".")[-1]) if "." in number else 0
                    if math.isclose(float(number.replace(",","")),gain,abs_tol=.5*10**(-decimals)+1e-8) and ((gain>0 and direction.startswith("느")) or (gain<0 and direction.startswith("빠"))):
                        failures.append({"reason":"단축값 부호와 빠름·느림 해석이 반대","candidate_id":sid})
            if "기본" in local_clause:
                for label,number in re.findall(r"(도보|연계|단축)(?:시간)?(?:은|는|이|:)?\s*([-+]?[\d,.]+)\s*분",local_clause):
                    field={"도보":"before_minutes","연계":"after_minutes","단축":"improvement_minutes"}[label]
                    expected=row.get("route",{}).get(field);checked+=1
                    decimals=len(number.split(".")[-1]) if "." in number else 0
                    if expected is None or not math.isclose(float(number.replace(",","")),expected,abs_tol=.5*10**(-decimals)+1e-8):
                        failures.append({"reason":"후보 기본 경로와 시간 수치의 연결 불일치","candidate_id":sid})
            assumption=re.search(r"(\d+(?:\.\d+)?)\s*분\s*가정",local_clause)
            if assumption:
                sensitivity=row.get("additional_validation",{}).get("overhead_sensitivity",[])
                found=next((x for x in sensitivity if x["overhead_minutes"]==float(assumption[1])),None)
                for number in re.findall(r"([-+]?[\d,.]+)\s*분\s*(?:단축|절약)",local_clause):
                    checked+=1;decimals=len(number.split(".")[-1]) if "." in number else 0
                    if not found or found.get("gain_minutes") is None or not math.isclose(float(number.replace(",","")),found["gain_minutes"],abs_tol=.5*10**(-decimals)+1e-8):
                        failures.append({"reason":"대여·반납 시간 가정과 단축값의 연결 불일치","candidate_id":sid})
            if re.search(r"(추가\s*)?면적",local_clause) and re.search(r"\d[\d.,]*\s*(건|분|명)",local_clause):
                failures.append({"reason":"면적의 단위 불일치","candidate_id":sid})
            if row.get("route",{}).get("status")!="model_connected" and re.search(r"경로.{0,8}(확인됐|확인되었|검증됐|검증되었|확보됐)",local_clause) and not re.search(r"미확인|못|않|보류",local_clause):
                failures.append({"reason":"미확인 경로를 확인된 것으로 서술","candidate_id":sid})
        if re.search(r"실제\s*환승률.{0,15}\d[\d.]*\s*%",clause) and not re.search(r"아니|미확인|않|못",clause):
            failures.append({"reason":"실제 환승률의 검증 근거 없음"})
        if re.search(r"설치(?:하면|\s*후).{0,25}(수요|이용량).{0,20}\d[\d.]*\s*%.{0,10}(증가|늘)",clause) and not re.search(r"가정|미검증|아니|않|못",clause):
            failures.append({"reason":"설치 후 효과의 검증 근거 없음"})
    return {"passed":not failures,"unsupported_claims":failures,"checked_candidate_claims":checked,
      "coverage":"후보ID·관측대여 연결·면적단위·미확인경로·실제환승/설치효과 단정 검사. 그 밖의 자유 서술 전체는 미검증."}
def compact(tool,result,byte_limit=24000):
    """Omit explicit detail fields; never invent or silently alter numeric facts."""
    if tool=="get_project_conclusion":
        result=copy.deepcopy(result)
        result.pop("project_goals",None)
        result.pop("comparison",None)
        for city in result.get("cities",[]):
            city.pop("additional_validation",None)
            city.pop("findings",None)
            if city.get("completion"):
                city["completion"].pop("journeys",None)
            for candidate in city.get("candidates",[]):
                candidate.pop("unchecked",None)
                candidate.pop("score_components",None)
        result["payload_compacted"]=True
        result["notice"]="목표별 긴 설명과 보조 검증 상세를 생략했습니다. 후보의 원래 수치는 변경하지 않았습니다."
    if len(json.dumps(result,ensure_ascii=False,default=str).encode())<=byte_limit:return result
    value=copy.deepcopy(result);omitted=[]
    def prune(x,path=""):
        if isinstance(x,dict):
            for key in list(x):
                p=path+"/"+key
                if key in {"geometry","monthly_ranks","months","matrix","experiments","sweeps","daily","observed_dates","station_bucket","stations","nodes","edges","series","candidate_sites","project_goals","training_patterns"}:
                    raw=x.pop(key);omitted.append({"path":p,"items":len(raw) if hasattr(raw,"__len__") else None})
                    if key=="daily" and isinstance(raw,list) and raw and all(isinstance(r,dict) and isinstance(r.get("rental_count"),(int,float)) for r in raw):
                        high=max(raw,key=lambda r:r["rental_count"]);low=min(raw,key=lambda r:r["rental_count"])
                        x["daily_extrema"]={"max":high,"min":low}
                    if key=="observed_dates" and isinstance(raw,list):x["observed_days"]=len(set(raw))
                else:prune(x[key],p)
        elif isinstance(x,list):
            for i,r in enumerate(x):prune(r,path+"/"+str(i))
    prune(value)
    metadata={"payload_compacted":True,"omitted_detail_fields":omitted,"notice":"생략된 상세 값을 추측하지 마세요. 서버 원문은 evidence에 보존됩니다."}
    value.update(metadata)
    if len(json.dumps(value,ensure_ascii=False,default=str).encode())>byte_limit:
        # Fail closed: a large tool cannot silently consume an unbounded provider budget.
        keys=("available","city","region_id","scope","period_start","period_end","message","limitations","coverage_note")
        small={k:result[k] for k in keys if k in result}
        small.update({"payload_compacted":True,"details_withheld":True,"notice":"근거 응답이 입력 예산을 초과했습니다. 이 도구의 상세 수치는 설명하지 말고 서버 결과를 확인하도록 안내하세요."})
        value=small
    return value
def model_json(tool,result):
    return json.dumps(compact(tool,result),ensure_ascii=False,default=str)
