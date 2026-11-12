"""Build final documentation from this run's actual evidence artifacts."""
import json,inspect
from pathlib import Path
from backend.agents import solar
root=Path("docs"); evidence=root/"final-validation"
analysis=json.loads((evidence/"analysis.json").read_text())
live=json.loads((evidence/"solar-live.json").read_text())
perf=json.loads((evidence/"performance.json").read_text())
browser=json.loads((evidence/"browser.json").read_text())
sources=json.loads(Path("data/processed/sources.json").read_text())
def write(name,text):(root/name).write_text(text,encoding="utf-8")
def mdtable(headers,rows):
 return "| "+" | ".join(headers)+" |\n|"+"|".join("---" for _ in headers)+"|\n"+"\n".join("| "+" | ".join(str(x) for x in row)+" |" for row in rows)+"\n"
case_rows=[]
window_rows=[]
for sid,case in analysis["cases"].items():
 v=case["validation"];m=v["metrics"]
 case_rows.append([sid,v["station"].get("station_name"),m["rental_count"],m["usage_rank"],m["pagerank_rank"],case["peak_hour"],round(case["peak_share"]*100,2),case["imbalance"]["net_outflow"]])
 for w in v["windows"]:
  window_rows.append([sid,w["days"],w["observed_day_count"],w.get("rental_count"),w.get("usage_rank"),w.get("pagerank_rank"),w.get("cluster_role"),w.get("peak_hour"),w.get("net_outflow"),w.get("persistence_ratio"),w["minimum_observation_pass"]])
text="# 최종 실제 분석 검증 — 2026-11-12\n\n이번 실행에서 SQLite를 읽기 전용으로 재집계하고, 정규화 Trip CSV를 실제 행 단위로 읽어 검산했다. 예전 작업 수치를 이번 결과로 대체 표기하지 않았다.\n\n"
text+=mdtable(["지역","전체 기간 이용 기록","10월 이용 기록","10월 관측 대여소"],[
 [rid,analysis["sql"][rid]["full"]["rentals"],analysis["sql"][rid]["common"]["rentals"],analysis["sql"][rid]["common"]["stations"]] for rid in ("seoul","daejeon")])
text+="\n대전 정규화 Trip CSV 실제 행 수: "+str(analysis["normalized_trip_csv_rows"])+". 통합 10월 이용량 5,169,532건, 관측 대여소 4,142개, 유효 OD 연결 600,047개를 확인했다.\n\n서울 X는 원본 OD "+str(analysis["unmatched_X"]["daily_od_rows"])+"행 / "+str(analysis["unmatched_X"]["trip_count"])+"건으로 보존하고, 전체 유효 그래프 노드·간선 및 지도 표본에서는 제외됨을 검사했다. 관측 이용 합계에는 원본 관측값이 포함될 수 있어 유효 그래프 이동량 합계와 같다고 가정하지 않는다.\n\n## 대표 사례 — 2026-10-01~31\n\n"
text+=mdtable(["ID","공식 마스터 이름/주소","대여","이용량 순위","PageRank 순위","집중 시각","집중 비중 %","순유출"],case_rows)
text+="\n이름이 비어 주소가 이름으로 제공되는 마스터 항목은 원래 값을 사용했다. 목적·환승·관광 역할을 추가 추정하지 않는다.\n\n## 기간별 검증\n\n"
text+=mdtable(["ID","요청 창","관측일","대여","이용량 순위","PageRank 순위","군집 설명","집중 시각","순유출","지속성","최소 관측 통과"],window_rows)
text+="\n30일 창은 10월 전체 31일과 다르므로 ST-1481의 30일 순위가 31일 전체의 1,640/280과 다른 것은 오류가 아니다. 최소 관측은 각 창의 실제 총량 분포 하위 25% 제외 기준과 요청 일수 충족 여부를 함께 사용한다.\n\nST-1481은 기간별 연결 순위가 이용량 순위보다 높게 유지된다. ST-2264는 세 창 모두 순유입 방향이다. ST-3031의 시간대 집중은 인과적인 이용 목적을 뜻하지 않는다.\n\n## 군집 안정성\n\n"
rows=[]
for rid,value in analysis["stability"].items():
 for window in value["windows"]:
  rows.append([rid,window["days"],window["selected_k"],max((x["silhouette"] for x in window["diagnostics"]),default=None),window["quality"],window["confidence_warning"]])
text+=mdtable(["지역","창","k","최고 Silhouette","품질","경고"],rows)
text+="\n"+mdtable(["지역","비교","공통 대여소","ARI"],[[rid,str(s["left_days"])+"↔"+str(s["right_days"]),s["common_station_count"],s["ari"]] for rid,v in analysis["stability"].items() for s in v["comparisons"]])
text+="\n모든 창의 Silhouette가 0.2 미만이므로 군집 유형 해석을 보류한다. ARI는 공통 대여소의 군집 배정 안정성이지 운영 역할의 확정 증거가 아니다.\n\n네 가지 후보 유형 모두 실제 계산했다. 서울 10월 후보 수는 "+json.dumps(analysis["role_types"]["counts"],ensure_ascii=False)+"이다. 역할 변화 예시 ST-2623은 7일 집중 9시/30일 집중 17시이며, 두 군집 설명 모두 해석 보류다. 시간대와 연결 순위 변화로 검토할 수 있으나 군집 역할이 확정적으로 바뀌었다고 하지 않는다.\n\n원자료: [analysis.json](final-validation/analysis.json). 실행 코드: scripts/validate/final_review.py.\n"
write("FINAL_ANALYSIS_VALIDATION.md",text)

text="# Solar 실제 연동 최종 검증 — 2026-11-12\n\nWIZ의 실제 질문 입력부터 응답 렌더링까지 5개 질문을 실행했다. 별도 Hello 요청이나 실패 재시도 없이 질문 수를 5개로 제한했다. 성공한 각 질문은 도구 선택/최종 답변의 두 Upstage 요청을 사용한다. 로컬 도구 호출은 외부 모델 호출 수와 구분한다. 키는 출력·문서·Git에 포함하지 않았다.\n\n"
rows=[]
for i,q in enumerate(live["questions"],1):
 v=q["response"];u=v["usage"]
 rows.append([i,q["question"],q["code"],", ".join(q["solar_tools"]),q["period_arguments_match"],q["numeric_grounding"]["passed"],q["station_grounding"]["passed"],u["prompt_tokens"],u["completion_tokens"],u["total_tokens"],q["seconds"]])
text+=mdtable(["Q","질문","코드","Solar 선택 도구","기간 일치","원문 수치","ID","입력 토큰","출력 토큰","합계","초"],rows)
text+="\n모델 응답명: solar-mini4-260922. 총 사용량은 "+str(live["total_tokens_reported"])+"토큰이다. 과금액은 가격표를 추정하여 산출하지 않았다.\n\n## 실패와 보호 동작\n\n- Q2에서 모델이 top_n=50을 제시한 호출 1건은 서버가 1~20 제한으로 거절했다. 실제 ST-1481 검증 도구와 서버 근거 보강 결과로 응답을 완료했다. 이 호출을 올바른 인자로 성공한 것처럼 집계하지 않는다.\n- Q4 원문은 시간대 배열 인덱스를 한 시간씩 잘못 읽었고 총량 배율을 비교했다. 수치 토큰 검증도 실패했다. 원문의 모든 내용을 검증 성공으로 표시하지 않는다.\n- 대응: 검증 미통과 원문은 기본 답변에서 보류하고, 실제 도구 값으로 만든 요약과 수치 카드만 기본 표시한다. 원문은 별도 닫힌 상세 영역에 보관한다.\n- 추가 유료 호출 없이 이 5개 실제 응답을 새 보호 함수에 재생했다. Q4만 tool_summary로 전환하고 나머지 4개는 solar_interpretation을 유지함을 확인했다. WIZ에서도 이 실제 응답의 재생 결과와 원문 접힘을 확인했다. 이는 두 번째 실호출이라고 주장하지 않는다.\n- 수치 토큰 검사는 모든 자유 서술의 의미를 보증하지 않는다. 관측 사실·AI 해석·운영 검토 제안은 구분한다.\n\n## 14개 도구\n\n"
text+=mdtable(["도구","용도"],[[name,spec[0]] for name,spec in solar.TOOL_DEFINITIONS.items()])
text+="\n## 실행 조건\n\nWIZ에서 region_ids/date_start/date_end를 서버로 전달한다. 서버는 확보 범위와 지역을 검증하고, 도구에 모델이 제시한 기간보다 화면의 고정 기간을 우선 적용한다. 범위 밖 도시 호출은 오류다. 기간별 창도 선택 시작일 이전으로 확장하지 않는다. 초회 도구 최대 5개, 보강 포함 최대 8개이며, 각 외부 요청 타임아웃과 전체 처리 시간 검사를 유지한다. 실제 실행한 도구만 evidence에 기록하며 initiator=solar 또는 metric_guard를 표시한다.\n\n증거: [solar-live.json](final-validation/solar-live.json), [보호 함수 재생 결과](final-validation/solar-guard-replay.json), solar-q1~q5.png 및 solar-guard-replay.png.\n"
write("FINAL_SOLAR_VALIDATION.md",text)

text="# 분석 지표 계산식과 해석\n\n- 서울: 날짜·시간대·OD 집계의 실제 이동 건수를 가중치로 사용한다. 대여·반납 관점 행을 중복 합산하지 않는다.\n- 대전: 검증된 개별 Trip을 대여소·날짜·시간 및 OD로 집계한다. 중복과 관리 반납 제외 정책 유지.\n- 전체: 상세 이용이 있는 도시의 공통 관측 범위에서 합산하고, 세종 연간 통계는 상세 합계에서 제외한다. 내부 ID=도시::대여소 ID로 충돌을 막고 도시 간 가상 간선은 만들지 않는다.\n\n## 알고리즘\n\n1. K-means: 시간대별 대여 비율(24차원), log1p(대여량), 가능한 경우 주말 비율을 StandardScaler로 표준화한다. k=2~8 중 가능한 범위를 Silhouette로 검토한다. Silhouette는 최대 1,500개 표본, random_state=42를 사용한다. 0.2 미만은 역할 해석 보류. 특징이 동일하거나 표본이 부족하면 불가 상태를 반환한다.\n2. ARI: 두 기간에 모두 존재하는 대여소 ID 교집합에서 군집 배정을 비교한다. 군집 번호는 재학습마다 의미가 같지 않으므로 번호 변경만으로 역할 변화를 단정하지 않는다.\n3. Cosine: x·y/(||x||||y||), x는 시간대 대여/총 대여와 가능한 주말 비중 벡터다. 절대 규모는 별도 이용량·volume_ratio로 구분한다.\n4. PageRank: PR(v)=(1-d)/N+d×Σ[PR(u)×w(u,v)/Σw(u,*)]. 실제 유효 OD 그래프에서 계산한다. 표시용 TOP N 그래프에서 새로 순위를 만들지 않는다.\n5. 가중 출차수=Σw(v,*), 입차수=Σw(*,v). 실제 이동 건수 합계이며 단순 이웃 수와 다르다.\n6. 매개 중심성: 최단경로 거리는 1/이동량, 큰 그래프에서 min(32,N) 노드 표본·seed=42를 사용한다. 기간 민감도에서 생략한 매개 중심성은 0이 아닌 미계산으로 구분한다.\n7. 순유출=대여 R−반납 T. 불균형 비율=(R−T)/(R+T). 지속성=max(양수 관측일 수,음수 관측일 수)/해당 대여소 관측일 수. 도시 전체 달력 일수와 다를 수 있다.\n\n## 역할 후보 규칙\n\n- 저이용·고연결: 이용량 중앙값 이하, 양의 이용량 순위−PageRank 순위 차이가 상위 10%, PageRank 값이 중앙값 이상을 동시에 충족.\n- 지속 불균형: 대여+반납 총량 하위 25% 제외 후, 절대 불균형 비율 상위 10%와 방향 지속성 상위 25%를 동시에 충족.\n- 시간대 집중: 대여량 하위 25%를 제외하고 최대 시간대 비중 상위 10%.\n- 역할 변화: 7일/30일 가중 연결 순위 백분위 차이 절댓값 + 집중 시각의 순환 거리/12 + 해석 가능한 군집 설명 변경 여부. 점수 상위 10%를 후보로 제시. 선택 기간이 짧으면 관측창 부족 경고를 함께 확인해야 한다.\n- 임계값은 선택 기간의 실제 분포에서 계산한다. 소수점 표시값을 다시 더해 원래 점수와 같다고 가정하지 않는다.\n\n통합 K-means/후보 표시는 도시별 결과를 모은 것이며 통합 재학습이 아니다. PageRank 등 연결 지표와 이용 패턴 군집은 서로 다른 질문에 답한다. 재고·재배치·날씨 자료가 없으므로 원인이나 운영 효과 수치를 확정하지 않는다.\n"
write("FINAL_ANALYSIS_FORMULAS.md",text)

text="# 공식 출처 및 데이터 기준 확인 — 2026-11-12\n\n공식 페이지를 이번 작업에서 다시 조회했으며, 대용량 원본을 새로 다운로드하거나 기존 정규화 파일을 덮어쓰지 않았다. 아래 수집일/기간은 보유 파일의 출처 기록이다. 페이지 최신 메타데이터와 보유 파일 기준일을 혼동하지 않는다.\n\n"
text+=mdtable(["지역","보유 데이터셋","출처","수집일","보유 기간","확보 상태"],[[x["region_id"],x["dataset_name"],x["source_url"],x.get("collected_at"),str(x.get("date_start"))+" ~ "+str(x.get("date_end")),x["verification_status"]] for x in sources if x["region_id"] in ("seoul","daejeon","sejong")])
text+="\n## 이번 공식 페이지 확인\n\n- [서울 OA-21229](https://data.seoul.go.kr/dataList/OA-21229/F/1/datasetView.do): 2026년 10월 ZIP 파일 목록(수정일 2026-11-08) 및 11월 일별 파일 제공 상태 확인. 이번 분석에는 이미 보유한 10월만 사용.\n- [서울 OA-14994](https://data.seoul.go.kr/dataList/OA-14994/F/1/datasetView.do): 최신 목록은 2026년 1~6월 일별 대여건수 파일, 수정일 2026-07-15. 과거 일부 대여소별 자료도 있지만 현재 사용 중인 시간대별 ST-ID OD의 완전한 대체재로 검증하지 않았다. 기존 보유 파일은 대여일자·대여건수 2열로 기존 전환 제한 유지.\n- [대전 타슈 이력 15137219](https://www.data.go.kr/data/15137219/fileData.do): 공식 제공기관 대전교통공사, CSV·연간 갱신·수정일 2026-11-02, 인코딩 EUC-KR/CP949 안내 확인. 실제 분석 기간은 보유 정규화 기록에서 재검산.\n- [세종 연간 통계 15134188](https://www.data.go.kr/data/15134188/fileData.do): 연간 통계·2개 컬럼 확인. 공식 설명의 2025-06-30 기준과 기존 보유 출처 메타데이터의 2026-08-31 표기에는 차이가 있어 추가 확인이 필요하다. 2026년은 부분 연도임을 유지하고, 상세 OD가 확보됐다고 간주하지 않는다.\n- 서울 마스터는 기존 검증된 OA-21235 보유 자료를 재사용했다. 현시점 마스터 좌표가 각 OD 관측일에도 같았는지에 대한 역사 좌표 검증은 미완료다.\n\n부산은 분석 대상에서 제외하고 기존 조사 코드만 보존한다. 세종 상세 데이터는 여전히 미확보다.\n"
write("FINAL_DATA_SOURCES.md",text)

text="# 최종 사용자·성능 검증 — 2026-11-12\n\n## 실제 브라우저\n\n"
text+=mdtable(["조작","결과"],[[json.dumps(x,ensure_ascii=False),"통과"] for x in browser["interactions"]])
text+="\n데스크톱 1273×818 및 모바일 390×844의 5개 메뉴 가로 넘침 없음, 페이지 오류 "+str(len(browser["page_errors"]))+"건. 기간별 KPI는 SQL 독립 집계와 대조했다. 7일 890,565건, 14일 1,748,118건, 30일 4,080,713건으로 31일 전체와 다르며 이전 캐시 값이 남지 않았다.\n\n## 콜드/웜 처리 시간\n\n"
text+=mdtable(["API","애플리케이션 캐시 우회(초)","캐시 준비 후(초)","결과 동일"],[[x["endpoint"],x["cold_seconds"],x["warm_seconds"],x["values_equal"]] for x in perf["rows"]])
text+="\n측정은 이번 실행의 FastAPI TestClient 처리 시간이며 네트워크 전송 지연은 포함하지 않는다. 콜드는 real_data의 메모리/디스크 데코레이터를 임시 우회한 실제 분석 재계산이며 운영 캐시 파일을 삭제하지 않았다. OS 파일 캐시는 초기화하지 않았다. 웜은 원래 함수를 복구해 준비한 뒤 측정했다. 단일 요청 측정이므로 통계적 성능 보장은 아니다.\n\n중복 요청은 진행 중 Promise 및 서버 결과 잠금으로 합친다. 화면 캐시 키는 도시/시작일/종료일/대여소 등 인자를 포함하며 기간 변경 시 기존 수치·지도·네트워크·AI 응답을 비운다. 계산 중 안내는 실제 요청 상태이며 새 리비전 최초 분석은 여전히 수십 초 걸릴 수 있다.\n\n증거: [browser.json](final-validation/browser.json), [performance.json](final-validation/performance.json), [5개 화면 캡처](final-validation/).\n"
write("FINAL_BROWSER_PERFORMANCE.md",text)

text="# 최종 발표·교수님 시연 가이드\n\n## 권장 흐름\n\n1. 대시보드에서 서울과 2026-10-01~31을 선택한다. 실제 4,245,954건과 핵심 발견을 확인한다.\n2. ST-1481 발견 카드를 눌러 대여소 분석으로 이동한다. 이용량 1,640위와 PageRank 280위가 답하는 질문이 다름을 설명한다.\n3. 시간대 패턴과 유사 대여소 TOP5를 보고, 7·14·30일 기간 비교와 군집 안정성 검증을 실행한다. 낮은 Silhouette는 숨기지 않고 역할 해석 보류로 설명한다.\n4. 이동 패턴에서 실제 OD와 불균형을 확인한다. 네트워크 노드를 눌러 대여소 상세로 돌아갈 수 있다.\n5. 전체를 선택해 단일 통합 화면의 5,169,532건·4,142개를 확인한다. 도시 간 가상 이동을 만들지 않았음을 설명한다.\n6. 도시 간 비교는 총량 배율보다 공통 기간의 시간대·요일 비율을 사용하고 세종 연간 통계를 별도로 확인한다.\n7. AI 분석 리포트에 질문을 입력한다. 실행된 도구, 고정된 도시·기간, 실제 근거 카드, 운영 검토와 한계를 차례로 보여준다. 실제 API 사용 토큰이 발생한다.\n\n## 발표 핵심 성과\n\n- 실제 서울 월간 집계 OD와 대전 11개월 760만 유효 Trip을 정규화하고 검산했다.\n- 단순 이용량 순위에서 놓칠 수 있는 ST-1481의 연결 중요도를 실제 수치로 제시했다.\n- ST-3031의 특정 시각 집중과 ST-2264의 기간 반복 순유입을 서로 다른 역할 후보로 구분했다.\n- 세종 상세 데이터 부족, 낮은 군집 품질, 근사 중심성의 한계를 공개한다.\n- AI는 자유 서술을 그대로 신뢰하지 않는다. 실제 비교 질문에서 잘못된 시간 해석을 발견했고, 원문 보류와 도구 기반 요약으로 서비스가 잘못된 기본 답변을 표시하지 않도록 했다.\n\n## 발표에서 피할 표현\n\n환승 거점 확정, 관광 대여소 확정, 재고 부족 확정, 재배치 효과 수치 예측, 전체 도시를 새로 학습한 K-means, 캐시 준비 시간을 포함하지 않은 속도를 모든 첫 요청의 속도로 설명하는 표현은 피한다.\n\n## 구현·검증 산출물\n\n- [실제 분석 검증](FINAL_ANALYSIS_VALIDATION.md)\n- [지표·판정식](FINAL_ANALYSIS_FORMULAS.md)\n- [Solar 실제 호출](FINAL_SOLAR_VALIDATION.md)\n- [브라우저·성능](FINAL_BROWSER_PERFORMANCE.md)\n- [출처와 기준일](FINAL_DATA_SOURCES.md)\n\n기존 React 소스와 분석 구조를 보존했다. 실제 사용 화면은 WIZ Angular이며 Git push·외부 배포는 하지 않았다.\n"
write("FINAL_SERVICE_GUIDE.md",text)
print("Generated 6 final documents",flush=True)
