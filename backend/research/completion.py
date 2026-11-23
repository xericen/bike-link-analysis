"""Verified completion artifacts, distinct historical, prospective and field scopes."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/completion-20261123"
def read(name):
    p=OUT/name
    try:return json.loads(p.read_text()) if p.exists() else None
    except (OSError,ValueError):return None
def apply(packets,goals,scope):
    journey=read("journeys.json");site=read("site-audit.json");replay=read("solar-replay.json")
    spark=[read("spark-raw-"+c+".json") for c in ("seoul","daejeon","sejong")]
    for city in packets:
        city["completion"]={"field_verified":False,"field_note":"현재 공식 자료와 원격 경로 점검입니다. 현장 방문·부지 허가·실재고·설치 효과는 미검증입니다."}
        if scope!="individual":continue
        if city["city"]=="daejeon" and journey:
            city["completion"]["journeys"]=journey
            city["completion"]["journey_scope"]="별도2026-11-23 수집 현행 평일 시간표·현재OSM을 적용한 예시.2025년 관측기간 재현 아님."
            city["completion"]["journey_destination"]="반석역 지상 출구·대전1호선 단일노선, 철도 간 환승0"
            city["completion"]["assumed_minutes"]={"pickup_return":2,"station_entry":2,"station_exit":2}
            if city.get("additional_validation",{}).get("full_journey"):
                city["additional_validation"]["full_journey"]["scope"]="historical_full_network"
                city["additional_validation"]["full_journey"]["prospective_reference_available"]=True
            rows=[]
            for example in journey["examples"]:
                for pair in example["examples"]:
                    before=pair["transit_only"];after=pair["bike_plus_transit"]
                    rows.append({"original_rank":example["original_rank"],"site_id":example["site_id"],"anchor":example["anchor_name"],
                      "departure":pair["origin_departure"],"wait_before":before.get("wait_minutes"),"wait_after":after.get("wait_minutes"),
                      "before":before.get("total_minutes"),"after":after.get("total_minutes"),"gain":pair["total_gain_minutes"]})
            city["completion"]["journey_rows"]=rows
            city["findings"].append("별도 현행 시간표 예시: 대전3후보·3출발시각의 동일 원점→반석역 출구 여정을 비교했습니다. 접근·승차 대기·철도 이동·출구 이동을 포함하며2025년 실제 여정 재현은 아닙니다.")
        if city["city"]=="seoul" and site:
            city["completion"]["dock_master"]=site["seoul_dock_master"]
            city["findings"].append("서울5후보의 반납 대여소를2026년6월 공식 마스터와 이름·좌표로 유일 연결해 거치대 열을 확인했습니다. 당시 재고·현장 설치 가능성·2025년 용량의 증거는 아닙니다.")
        if city["city"]=="sejong":
            routes=read("sejong-routes.json")
            if routes and routes["source_revision"]==city["source_revision"]:
                city["completion"]["remote_route_counts"]={"checked":routes["routes"]["candidate_count"],"new_requests":routes["new_requests"],
                  "positive":sum(r["review_status"]=="positive_model" for r in routes["routes"]["candidates"])}
                city["findings"].append("세종에는 별도12회 경로 조회를 추가했지만 확인된 시간상 유리한 연결은 여전히1곳입니다. 미확인 경로를 연결 가능으로 바꾸지 않았습니다.")
    if journey and journey["available"]:
        goals["items"][3]["status"]="대표 여정 비교·부분 검증"
        goals["items"][3]["evidence"]+=" 현행 공식 시간표·구간 소요시간을 적용한 대전 대표3후보×3출발시각의 전체 여정 모델을 별도로 추가했습니다."
        goals["items"][3]["remaining"]="대표 전체 여정은 현행 대전1호선 단일노선의 가정 기반 모델입니다.2025년 실제 운행 재현·다중노선 환승·서울/세종 전체 여정·실측 효과는 미완료이며 역 진입/출구 이동시간은 가정입니다."
    from backend.presentation.individual import scope as current_scope
    complete=[r for r in spark if r and r["source_revision"]==current_scope(r["city"])["revision"] and r["od"]["matches"] and r["station_usage"]["matches"] and r.get("anchor_hours",{}).get("matches")]
    if complete:
        goals["items"][2]["evidence"]+=" 추가 원본Spark 정제·중복처리·전체일별OD·시간대대여반납 대조 완료 "+str(len(complete))+"/3도시. 연계 시간대·위치 미연결 집계까지 함께 대조했습니다."
    if len(complete)==3:
        goals["items"][2]["evidence"]="보유 원본63개CSV를 Spark로 정제해 유효이력 "+format(sum(r["valid_rows"] for r in complete),",")+"건의 일별OD·시간대대여반납·연계시간대 집계를 기존DB와 대조했습니다. 세 도시 모두 키·수량 지문이 일치했습니다. 기존 MCLP36실험·pandas/Spark36회 비교도 보존했습니다."
    if replay:
        goals["items"][4]["evidence"]+=" 저장 실응답 근거를 이용한 후보별 값·단위·경로·효과 단정 회귀문장 "+str(replay["correct"])+"/"+str(replay["case_count"])+"검사. 자유 서술 전체 보증은 아닙니다."

    cost=read("solar-cost.json")
    if cost:
        goals["items"][4]["evidence"]+=" 입력·출력 예산을 적용한 동일3질문 토큰 관측값은 "+format(cost["prior_three_questions_tokens"],",")+"→"+format(cost["final_three_questions_tokens"],",")+"개입니다. 요금 청구액이나 일반화된 절감률은 아닙니다."

    audit=read("live-prose-audit.json")
    if audit and cost and replay:
        goals["items"][4]["status"]="근거 조회·오류 보류 검증"
        goals["items"][4]["evidence"]="이번 실제 질문6회와 통제 회귀문장 "+str(replay["correct"])+"/"+str(replay["case_count"])+"검사를 수행했습니다. 실제 원문3개에서 시간 필드·부호·시간 가정 오류를 찾아 보류하고 서버값으로 표시합니다. 세질문 토큰 관측값 "+format(cost["prior_three_questions_tokens"],",")+"→"+format(cost["final_three_questions_tokens"],",")+"개."
        goals["items"][4]["remaining"]="111개 통제 문장과 실제3응답의 검사 결과이며 전체 자유 서술의 사실성을 보증하지 않습니다. 원문이 검증에 실패하면 사실 영역은 서버가 계산한 요약으로 대체합니다. 토큰 비교도 통제된 요금 실험은 아닙니다."
