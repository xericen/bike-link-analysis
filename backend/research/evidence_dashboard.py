"""Compact screen-ready evidence with explicit research scopes and unresolved requirements."""
import json
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"docs/completion-20261123";NEW=ROOT/"docs/visibility-20261123"
NAMES={"seoul":"서울","daejeon":"대전","sejong":"세종"}
@lru_cache(maxsize=32)
def _read(path,stamp,size):return json.loads(Path(path).read_text())
def read(path):
    p=Path(path)
    if not p.exists():return None
    try:return _read(str(p),p.stat().st_mtime_ns,p.stat().st_size)
    except (OSError,ValueError):return None
def build(city):
    selected=list(NAMES) if city=="all" else [city]
    from backend.presentation.individual import scope
    spark=[]
    for c in selected:
        r=read(BASE/("spark-raw-"+c+".json"))
        if not r or r["source_revision"]!=scope(c)["revision"]:continue
        checks={k:bool(r.get(k,{}).get("matches")) and r[k]["actual"]==r[k]["expected"] for k in ("od","station_usage","anchor_hours")}
        spark.append({"city":c,"name":NAMES[c],"period":r["period_start"]+" ~ "+r["period_end"],"files":r["members"],
          "raw_rows":r["raw_rows"],"excluded_rows":r["excluded_rows"],"duplicate_rows":r["duplicate_rows"],"valid_rows":r["valid_rows"],
          "od_rows":r["od"]["actual"]["rows"],"usage_rows":r["station_usage"]["actual"]["rows"],"hour_rows":r["anchor_hours"]["actual"]["rows"],
          "checks":checks,"matches":all(checks.values()),"seconds":r["seconds_including_extraction"]})
    replay=read(BASE/"solar-replay.json") or {};cases=[r for r in replay.get("cases",[]) if r["city"] in selected]
    cost_rows=[]
    for c in selected:
        prior=read(ROOT/"docs/final-validation-20261123"/("solar-"+c+".json"))
        after=read(BASE/"live-solar"/("solar-"+c+".json"))
        if prior and after:
            b=prior["response"].get("usage",{}).get("total_tokens");a=after["response"].get("usage",{}).get("total_tokens")
            cost_rows.append({"city":c,"name":NAMES[c],"before":b,"after":a,"ratio":a/b if b else None})
    audit=read(BASE/"live-prose-audit.json") or {}
    errors=[{**r,"name":NAMES[r["city"]]} for r in audit.get("cases",[]) if r["city"] in selected]
    categories={}
    for row in cases:
        label=row["kind"];group=categories.setdefault(label,{"kind":label,"count":0,"correct":0})
        group["count"]+=1;group["correct"]+=int(row["correct"])
    category_labels={"correct_candidate_value":"후보별 대여량 정상 문장","wrong_candidate_same_global_number":"다른 후보의 대여량 혼용","unknown_id":"근거에 없는 후보ID","wrong_area_unit":"면적 단위 오류","unsupported_actual_transfer":"미검증 실제 환승률 단정","unsupported_installed_effect":"미검증 설치 효과 단정","unconfirmed_route_assertion":"미확인 경로를 확인됐다고 서술","correct_candidate_area":"후보별 면적 정상 문장","wrong_candidate_area":"후보별 면적 수치 오류","correct_basic_time":"기본 경로 시간 정상 문장","wrong_basic_time":"기본 경로 시간 오류","correct_multiple_candidates_one_sentence":"복수 후보를 함께 쓴 정상 문장","translated_candidate_id":"원본 후보ID 번역·변형","correct_overhead_assumption":"시간 가정과 수치 정상 연결","wrong_overhead_assumption":"시간 가정과 수치 혼용"}
    for group in categories.values():group["label"]=category_labels.get(group["kind"],group["kind"])
    solar={"case_count":len(cases),"correct":sum(r["correct"] for r in cases),"errors":errors,"cost_rows":cost_rows,
      "before_tokens":sum(r["before"] or 0 for r in cost_rows),"after_tokens":sum(r["after"] or 0 for r in cost_rows),
      "categories":list(categories.values()),"method":"같은 도시 질문의 저장 기록 비교. 선택 도구와 답변 길이도 달라진 관측값이며 입력 축약만의 인과적 비용 절감 실험은 아닙니다.",
      "scope":"통제 문장 회귀와 실제 오류 원문 재생. 전체 자유 서술의 사실성이나 외부 독립 정확도 평가가 아닙니다."}
    method_report=read(ROOT/"docs/final-validation-20261123/results.json") or {};patterns=read(ROOT/"docs/final-validation-20261123/training-patterns.json") or {}
    methods=[]
    for c in selected:
        r=method_report.get("cities",{}).get(c)
        if r and r["source_revision"]==scope(c)["revision"]:
            base,graph=r["temporal"]["methods"]
            methods.append({"city":c,"name":NAMES[c],"train":"2025년1·4~6월","test":"2025년7~12월",
              "baseline_demand":base["test_nearby_rentals_unique"],"graph_demand":graph["test_nearby_rentals_unique"],
              "top3_overlap":r["temporal"]["selection_overlap"],"hits":base["test_top10_hits"],"patterns":patterns.get(c)})
    opening_global=read(NEW/"opening-events.json")
    transfer_global=read(NEW/"seoul-transfer-journeys.json")
    seoul_version=scope("seoul")["revision"]
    if opening_global and opening_global.get("source_revision")!=seoul_version:opening_global=None
    if transfer_global and transfer_global.get("source_revision")!=seoul_version:transfer_global=None
    opening=opening_global if city in {"all","seoul"} else None
    transfer=transfer_global if city in {"all","seoul"} else None
    transfer_rows=[]
    if transfer:
        for e in transfer["examples"]:
            for pair in e["pairs"]:
                a,b=pair["before"],pair["after"]
                if not (a["available"] and b["available"]):continue
                transfer_rows.append({"site_id":e["site_id"],"rank":e["original_rank"],"route":e["route_label"],"departure":pair["departure"],
                  "before":a["total_minutes"],"after":b["total_minutes"],"gain":pair["gain"],
                  "before_wait":a["first_wait_minutes"]+a["transfer_wait_minutes"],"after_wait":b["first_wait_minutes"]+b["transfer_wait_minutes"],
                  "transfers":1,"before_trains":" → ".join(l["train_id"] for l in a["legs"]),"after_trains":" → ".join(l["train_id"] for l in b["legs"]),"before_legs":a["legs"],"after_legs":b["legs"]})
    sensitivity_rows=[{"rank":e["original_rank"],**r} for e in (transfer or {}).get("examples",[]) for r in e["sensitivity"]]
    opening_count=(opening_global or {}).get("eligible_count",0)
    blockers=[
      {"key":"journeys","title":"배차·환승을 포함한 여정","status":"대표 모델 구현",
       "done":"대전9개 단일노선 여정과 서울6개 두 노선 환승 여정을 계산했습니다.",
       "reason":"서울 자료는2025-09-30 공개본이며12월 시행 여부와 요일 누락 행의 보완은 미확인입니다. 대전은 현행 시간표이고 세종BRT는 중간 정류장 도착시각이 없습니다.",
       "next":"12월 시행 이력과 BRT 중간시각이 필요합니다. 환승보행 시간은 실측 전까지 가정으로 표시합니다.",
       "source_url":"https://data.seoul.go.kr/dataList/OA-22522/L/1/datasetView.do","source_label":"확보한 서울 공식 시간표"},
      {"key":"field","title":"부지·통행·재고 확인","status":"현장 증거 필요",
       "done":"서울 반납소5곳의 공식 거치대 열을 연결하고 세종 경로를12회 추가 점검했습니다.",
       "reason":"원격 경로와 마스터만으로 통행 가능·부지 사용 허가·과거 재고를 증명할 수 없습니다. 방문일·사진·허가·재고 로그가 제공되지 않았습니다.",
       "next":"15후보 현장 확인표에 방문 기록과 증빙을 연결해야 합니다. 실시간API는 인증키가 필요하며 과거 재고 이력이 아닙니다.",
       "source_url":"https://data.seoul.go.kr/dataList/OA-15493/A/1/datasetView.do","source_label":"실시간 정보의 제공 범위"},
      {"key":"effects","title":"설치 후 실제 개선 효과","status":"관측 사례 보완",
       "done":"서울 기존 개설 사례"+str(opening_count)+"곳의 전후28일과 비교지역 관측 변화를 추가했습니다.",
       "reason":"이번에 제안한 후보는 아직 설치되지 않았습니다. 기존 사례도 날씨·시설·ID변경 등을 완전히 통제하지 않아 인과 효과로 확정할 수 없습니다.",
       "next":"실제 사업 시행일·비교지역·과거 위치와 재고 자료가 필요합니다. 현재 수치는 관측 참고로만 사용합니다.",
       "source_url":None,"source_label":None},
      {"key":"solar","title":"AI 설명의 사실성","status":"오류 보류 동작",
       "done":"111개 통제 문장과 실제3원문의 시간 필드·부호·가정 오류를 검사하고 근거값 요약으로 대체했습니다.",
       "reason":"검사에 없는 표현까지 모두 증명하지는 못합니다. 발견된 오류를 사용한 회귀검사여서 독립 평가 정확도로 일반화할 수 없습니다.",
       "next":"새 독립 질문과 검토 기준으로 평가 범위를 넓혀야 합니다. 통과하지 못한 서술은 현재도 보류합니다.",
       "source_url":None,"source_label":None}]
    return {"scope_label":("세 도시" if city=="all" else NAMES[city])+"의 별도 분석·검증 기록",
      "spark":{"rows":spark,"raw_total":sum(r["raw_rows"] for r in spark),"valid_total":sum(r["valid_rows"] for r in spark),
        "excluded_total":sum(r["excluded_rows"]+r["duplicate_rows"] for r in spark),"files":sum(r["files"] for r in spark),
        "matched":sum(r["matches"] for r in spark),"city_count":len(spark),
        "note":"도시별 확보 전체기간의 처리 검증입니다. 서로 다른 기간의 이용량을 도시 성과로 비교하지 않습니다. 단일 서버local[2], 기존 운영DB 보존."},
      "solar":solar,"methods":methods,"seoul_transfer":transfer,"seoul_transfer_rows":transfer_rows,"transfer_sensitivity_rows":sensitivity_rows,
      "opening":opening,"blockers":blockers,"operational_update":False,"field_verified":False}
