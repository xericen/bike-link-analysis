# Solar 실제 연동 최종 검증 — 2026-11-12

WIZ의 실제 질문 입력부터 응답 렌더링까지 5개 질문을 실행했다. 별도 Hello 요청이나 실패 재시도 없이 질문 수를 5개로 제한했다. 성공한 각 질문은 도구 선택/최종 답변의 두 Upstage 요청을 사용한다. 로컬 도구 호출은 외부 모델 호출 수와 구분한다. 키는 출력·문서·Git에 포함하지 않았다.

| Q | 질문 | 코드 | Solar 선택 도구 | 기간 일치 | 원문 수치 | ID | 입력 토큰 | 출력 토큰 | 합계 | 초 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 서울에서 이용량은 적지만 연결상 중요한 대여소는? | 200 | get_hidden_hubs | True | True | True | 14658 | 897 | 15555 | 18.917 |
| 2 | ST-1481이 숨은 연결 후보인 이유는? | 200 | get_hidden_hubs, get_hidden_hub_validation | True | True | True | 11677 | 904 | 12581 | 38.047 |
| 3 | 대전에서 반복적인 대여·반납 불균형이 나타나는 곳은? | 200 | get_station_imbalance | True | True | True | 33745 | 899 | 34644 | 16.557 |
| 4 | 서울과 대전의 이용 패턴 차이는? | 200 | compare_region_patterns, get_data_availability, get_data_availability | True | False | True | 19646 | 928 | 20574 | 23.892 |
| 5 | 서울 ST-1481 대여소의 역할은 최근 7일과 30일 사이에 달라졌는가? | 200 | get_station_role_history, get_station_details | True | True | True | 5512 | 906 | 6418 | 21.511 |

모델 응답명: solar-mini4-260922. 총 사용량은 89772토큰이다. 과금액은 가격표를 추정하여 산출하지 않았다.

## 실패와 보호 동작

- Q2에서 모델이 top_n=50을 제시한 호출 1건은 서버가 1~20 제한으로 거절했다. 실제 ST-1481 검증 도구와 서버 근거 보강 결과로 응답을 완료했다. 이 호출을 올바른 인자로 성공한 것처럼 집계하지 않는다.
- Q4 원문은 시간대 배열 인덱스를 한 시간씩 잘못 읽었고 총량 배율을 비교했다. 수치 토큰 검증도 실패했다. 원문의 모든 내용을 검증 성공으로 표시하지 않는다.
- 대응: 검증 미통과 원문은 기본 답변에서 보류하고, 실제 도구 값으로 만든 요약과 수치 카드만 기본 표시한다. 원문은 별도 닫힌 상세 영역에 보관한다.
- 추가 유료 호출 없이 이 5개 실제 응답을 새 보호 함수에 재생했다. Q4만 tool_summary로 전환하고 나머지 4개는 solar_interpretation을 유지함을 확인했다. WIZ에서도 이 실제 응답의 재생 결과와 원문 접힘을 확인했다. 이는 두 번째 실호출이라고 주장하지 않는다.
- 수치 토큰 검사는 모든 자유 서술의 의미를 보증하지 않는다. 관측 사실·AI 해석·운영 검토 제안은 구분한다.

## 14개 도구

| 도구 | 용도 |
|---|---|
| get_region_overview | 지역의 관측 기간, 이용량, 시간대별 이용과 출처 |
| get_station_details | 대여소 실제 이용량, 좌표, 군집 세부 정보 |
| get_station_clusters | 실제 이용 기록의 K-means 군집과 유형 |
| get_centrality_ranking | 전체 OD 그래프에서 계산한 중심성 순위 |
| get_network_analysis | 실제 OD 이동 연결, 상위 PageRank 노드 시각화 |
| find_similar_stations | 시간대 패턴 코사인 유사 대여소 |
| compare_region_patterns | 지역별 기간과 비교 가능 범위 |
| get_data_availability | 원천 자료의 확보 상태 및 분석 가능 범위 |
| get_cluster_stability | 7일·14일·30일 K-means 군집 안정성과 ARI |
| get_station_imbalance | 대여·반납 순유출, 불균형 비율과 지속성 |
| get_hidden_hubs | 이용량 순위보다 연결 중심성 순위가 높은 대여소와 근거 연결 |
| get_hidden_hub_validation | 특정 대여소의 이름·위치·대여/반납·TOP 10 연결·순위 백분위와 7·14·30일 민감도 |
| get_station_role_history | 동일 대여소의 7·14·30일 군집·집중 시간·가중 연결 순위 변화 |
| get_role_candidates | 분포 기반 네 가지 숨은 역할 후보와 판정 임계값 |

## 실행 조건

WIZ에서 region_ids/date_start/date_end를 서버로 전달한다. 서버는 확보 범위와 지역을 검증하고, 도구에 모델이 제시한 기간보다 화면의 고정 기간을 우선 적용한다. 범위 밖 도시 호출은 오류다. 기간별 창도 선택 시작일 이전으로 확장하지 않는다. 초회 도구 최대 5개, 보강 포함 최대 8개이며, 각 외부 요청 타임아웃과 전체 처리 시간 검사를 유지한다. 실제 실행한 도구만 evidence에 기록하며 initiator=solar 또는 metric_guard를 표시한다.

증거: [solar-live.json](final-validation/solar-live.json), [보호 함수 재생 결과](final-validation/solar-guard-replay.json), solar-q1~q5.png 및 solar-guard-replay.png.

## 최종 응답 길이 보호 보완

저장된 실제 응답 일부는 문장 또는 목록 중간에서 끝난다. 당시 실호출 기록에 finish_reason을 저장하지 않아 제공자 종료 원인을 확정하지 않는다. 최종 구현은 이후 응답의 finish_reason을 기록하고 length이면 수치 검사를 통과하더라도 원문을 보류한다. 답변을 3개 사례·짧은 문장으로 제한하는 지시도 추가했다. 이 최종 보완은 단위 테스트와 저장 응답 재생으로 검증했으며 추가 유료 실호출은 하지 않았다. 따라서 4건의 수치 토큰 통과를 자유 서술 전체의 정확성·완결성 통과로 해석하지 않는다.

최종 전체 도시 문맥의 보호 화면: [실제 응답 재생 캡처](final-validation/solar-guard-replay-final.png). 재생으로 추가한 외부 API 호출은 0건이다.
