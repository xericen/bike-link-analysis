# Solar 실제 도구 호출 검증 — 2026-11-04

키 원문은 출력·저장하지 않았다. `.env` 로딩은 참으로 확인했고, Upstage `solar-mini4` 단문 요청은 HTTP 성공, 모델 응답 및 토큰 사용량 62를 확인했다. API 엔드포인트는 `https://api.upstage.ai/v1/chat/completions`이다.

| 질문 | 실제 결과 | 핵심 도구·검증 |
|---|---|---|
| Q1 서울 PageRank TOP 5 | 200, 한국어, 도구 수치 차트 | `get_centrality_ranking`; ST-3388 0.0035523이 상위. 미매칭 X 제외 |
| Q2 대전 이용량·중심성 차이 | 200, 한국어, 대여소 비교 보강 후 재검증 | `get_centrality_ranking`, `get_region_overview`, `get_station_details`; ST1067·ST0191·ST0408 상세 조회 성공 |
| Q3 서울·대전 비교 | 200, 한국어 | `get_region_overview`, `compare_region_patterns`; 공통 관측일 2026-10-25, 2026-10-29 |
| Q4 세종 군집 가능 여부 | 200, 한국어, 불가 안내 | `get_data_availability`, `get_station_clusters`; 대여소 단위 자료 없음 |
| Q5 부산 연결 중심성 | 200, 한국어, 불가 안내 | `get_centrality_ranking`은 OD 미확보 결과, `get_data_availability`는 운영 메타데이터만 반환 |
| Q6 서울 운영 제안 | 200, 한국어 | `get_network_analysis`, `get_centrality_ranking`, `get_region_overview`; 효과 수치 추정 없음 |

첫 전체 검증에서는 Q2~Q6의 최종 요청에 `tools`가 빠져 Solar가 HTTP 400을 반환했다. `tools`와 `tool_choice=none`을 함께 전달하도록 수정한 뒤 재검증했다. 다음 검증에서 Solar가 Q2·Q5에 내부 도구 문법을 출력하거나 잘못된 metric을 요청한 사례를 확인했다. 도구 호출 한도, 서버의 명시 지표 보강, 내부 문법 출력 시 사실 기반 안내로 대체하는 처리를 추가했다. 최종 6개 질문은 모두 200·한국어 응답이었다. 잘못된 metric 호출은 오류 근거로 남기고 분석 지표로 사용하지 않았다.

Q2 최종 추가 실호출에서는 ST0412 대여량 232건·이용량 순위 12·중심성 순위 1·순위 차이 +11, ST1067 245건·8·2·+6, ST0191 330건·2·3·-1을 확인했다. 순위 차이와 표는 도구 결과에서 계산한다. 이 추가 확인 스크립트는 API 200 및 비교값을 출력한 후, 검증 출력 코드가 일별 차트에 없는 metric 키를 조회해 종료 코드 1을 냈다. API 실패는 아니다.

구조화 카드·차트 수치는 도구 응답에서 복사한다. Q2 최신 재검증에서 세 대여소 상세 조회가 성공했다. Q1~Q6 전체 검증 응답의 토큰 수는 차례로 4,627 / 8,603 / 9,505 / 3,281 / 2,664 / 10,963이다. 반복 시험 비용을 줄이기 위해 이후 수정은 Q2·Q5만 다시 실제 호출했다. 자유 서술의 모든 문장에 대한 자동 수치 감사는 미구현이다.

`pytest backend/tests/test_api.py` 7건 통과. FastAPI `/api/health` HTTP 200. 프론트엔드 `npm run build` 성공. Chromium에서 `/agent` 로드, API 설정 상태, 세종 질문 입력, 응답 보고서, 도구 근거 및 한계 표시를 확인했다. 캡처: `docs/screenshots/stage4-agent.png`. 브라우저에서 6개 질문을 각각 재실행하지는 않았다.

추가 직접 도구 검증: 서울 ST-3388에 대해 `find_similar_stations`를 실행해 실제 유사 대여소 5건을 반환했다. 6개 Solar 질문에서 유사도 도구는 모델이 선택하지 않았다.
