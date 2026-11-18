# 앵커 용어·KPI 분모·출처·세종 지도 표시 검증 (2026-11-17)

리뷰 ID: qczzjjzymdxmludnqafyeaqoxazpuapi. 분석 계산식·거리·판정·원본 자료·사전 집계 결과는 변경하지 않았다.

## 명령별 결과

| 명령 | 변경 및 확인 |
|---|---|
| 1 | Solar 도구 설명·프롬프트·응답 카드·거리 한계와 프런트 표시를 서울/대전=지하철역(앵커), 세종=BRT 정류장(앵커)로 명시했다. 일반 버스 정류장 지표는 별도로 유지했다. 서울·세종 실제 질문 각각 1회에서 앵커 유형을 확인했다. |
| 2 | SQLite의 선택 기간별 대여/반납 기록과 위치 마스터 집합을 조회하고 27개 도시·기간 조합의 표시용 각주를 추가했다. 요청 중 실시간 분석이나 집계 캐시 수정 없이 검증 JSON을 읽는다. |
| 3 | 자료 메타데이터에 기록된 출처명·앵커 행 수를 3개 도시에서 표시했다. 세종은 기존 문맥 배너 안에 추가했다. 도시 비교의 세종 각주는 유지했다. |
| 4 | 세종 대시보드·취약 지도에서 좌표가 확보된 726개를 전수 circleMarker로 표시하고 BRT 152개를 상단 레이어·별도 범례로 강조했다. 서울·대전은 기존 표본과 취약 후보 표시 방식을 유지했다. 노선 선형은 만들지 않았다. |
| 5 | 85 tests passed(기존 deprecation 경고 31건), compileall 오류 0, React/웹 일반 빌드 통과. 로컬 FastAPI 8188의 9개 응답, 실제 웹 Chromium 화면·모바일 가로 넘침 없음, 27개 조합 KPI와 캐시 바이트 동일성을 확인했다. |

## DB 조회: 대시보드 분모와 분석 집합

서울·대전은 2026-10-01~31, 세종은 2025-10-01~31 기준이다. 분석 집합은 서비스가 사용하는 대여량 양수 대여소 기준이며, 반납만 있는 대여소와 구별한다.

| 도시 | 위치 분모 | 대여 기록 연결 분석 대여소 | 확인된 차이 |
|---|---:|---:|---|
| 서울 | 2,762 | 2,759 | ST-48: 대여 0/반납 99, ST-380: 0/17, ST-74: 0/1. 3개 모두 반납 기록이 있으므로 단순 기록 미연결이라고 쓰지 않았다. |
| 대전 | 1,403 | 1,383 | 차이 20개는 선택 기간 station_usage 행이 없다. 원인 추정은 하지 않았다. |
| 세종 | 726 | 728 | 마스터 728개 중 251009(대여321/반납363), SJ_00045(대여519/반납421)는 이용 기록은 있으나 위치 미연결로 분모에서 제외된다. |

대전 20개 ID: ST0075, ST0294, ST0325, ST0454, ST0502, ST0620, ST0691, ST0818, ST0841, ST0859, ST0860, ST0933, ST0935, ST1066, ST1130, ST1133, ST1179, ST1363, ST1450, ST1539.

원문 조회 근거와 각 기간의 상세 수치는 [검증 JSON](anchor_presentation_context.json), 재실행은 `PYTHONPATH=. python scripts/validate/anchor_presentation_audit.py`이다. 이 스크립트는 DB를 읽고 docs JSON만 생성한다. 자료 개정 시 이 표시용 JSON도 재검증해야 하며 현재 자료 revision과 다르면 API가 409로 안내한다.

## 실제 앵커 자료와 지도

| 도시 | 출처명(저장 메타데이터 그대로) | 사용 앵커 |
|---|---|---:|
| 서울 | 전국 도시철도 역사정보 전체기관 | 340행 |
| 대전 | 전국 도시철도 역사정보 전체기관 | 22행 |
| 세종 | 세종특별자치시 BRT노선별 정류장 현황 | 152개 |

도시철도는 운영기관·노선별 행 기준이며 고유 물리 역사 수와 같다고 단정하지 않는다. 세종 원본 `data/raw/sejong-brt-20250717.csv`는 343행, 정류장 ID·좌표 중복 제거 후 152개다. 출처 URL은 https://www.data.go.kr/data/15118026/fileData.do 이며 저장 메타데이터 `transit_anchors_sources.json`을 사용했다. 자료에 없는 브랜드/기관명은 추가하지 않았다.

BRT CSV에는 노선명·정류장 순번·정류장 좌표만 있다. 저장소에 실제 노선 선형 자료가 없어 Polyline을 추정해 그리지 않았다. 세종 728개 중 좌표 있는 726개와 BRT 152개가 대시보드 및 취약 지도 양쪽에서 실제 DOM 마커 수와 일치했다. 미연결 2개는 각주로 명시했다. 정류장 점은 청록 채움/네이비 테두리, 크기와 상단 pane으로 강조했다.

## KPI 회귀 및 실행 근거

- 서울: 31.499% / 취약 후보 1,276 / 연계 이동 62.211% / 접근 불가 면적 회복 8.34%.
- 대전: 취약 후보 1,127 / 회복 1.286%.
- 세종: 46.556% / 72.9% / 취약 후보 236 / 회복 0.909%.
- 27개 조합의 goal_metrics, candidate_count, scenario, 통합 도시 시나리오가 변경 전과 동일했다.
- 사전 집계 SQLite SHA256: `3400515982a03aaf68cafabfc3c05106386bc2cbe82f808dff371c36a8726771`. 작업 전후 파일 바이트가 동일해 기존 수치 전체가 보존됨을 확인했다.
- [회귀 JSON](presentation-regression-20261117.json): 로컬 8188 API 9건 HTTP200, 27개 조합 비교.
- [최종 브라우저 검사](presentation-browser-20261117.json): 세 도시 각주·출처·KPI 로딩 완료 후 검증, 세종 지도 두 곳의 마커 수, 페이지 오류 0, 모바일 가로 넘침 없음.
- [실제 Solar 원본](presentation-browser-live-20261117.json): 서울·세종 각 1회 질문. 총 27,328토큰(도구 선택 및 최종 응답 총 4회 제공자 요청). 응답에 지하철역/BRT 유형 명시를 확인했다. 추가 유료 호출은 하지 않았다.
- 실제 세종 자유 서술에서 점수 순위 1위를 ‘최대 수요’라고 부른 표현을 발견해, 도구의 실제 첫 순위 ID와 대조하여 ‘개선 검토 우선순위가 가장 높은 후보’라는 문구로만 교정했다. 수치·거리·계산·도구 결과는 그대로다. [최종 표시 함수 재생 검증](presentation-answer-replay-20261117.json)은 기록된 실제 응답을 재생한 결과이며 새 모델 응답으로 보고하지 않는다. 원본 응답도 보존했다.
- 초기 브라우저 수집은 비동기 KPI 로딩 전 캡처가 포함되어 최종 검사는 KPI 로딩 완료를 기다리도록 보완했다. 최종 브라우저 재검사는 이전 실제 Solar 결과를 근거로 재사용하며 외부 모델을 다시 호출하지 않았다.
- 캡처: [세종 대시보드](presentation-sejong-dashboard-20261117.png), [세종 취약 지도](presentation-sejong-map-20261117.png), [서울 실제 AI](presentation-agent-seoul-20261117.png), [세종 실제 AI 원본](presentation-agent-sejong-20261117.png).
- 명령: `python -m pytest backend/tests -q`, `python -m compileall -q backend scripts`, `npm run build`(frontend), 웹 `web_project_build(clean=false)`. Python 병렬 수치 라이브러리 스레드 수는 테스트 실행 시 1로 제한했다.

## 변경 파일

- backend/agents/solar.py, backend/main.py
- backend/presentation/anchors.py
- backend/tests/test_anchor_presentation.py
- frontend/src/services/anchorPresentation.ts
- frontend/src/components/TransitLinkage.tsx, TransitPanel.tsx
- frontend/src/maps/StationMap.tsx
- frontend/src/{components,maps,services}의 React 화면 소스
- scripts/validate/{anchor_presentation_audit.py,presentation_regression_20261117.py}
- 본 문서 및 위 검증 JSON·화면 캡처, 프로젝트/작업 루트 개발로그.

기존 사용자 변경을 보존했으며 서비스/분석 계산 모듈·집계 DB·원본은 이 작업에서 수정하지 않았다. Git push와 배포는 하지 않았다.

## 남은 한계

세종 위치 미연결 2개는 지도에 표시할 수 없다. BRT 실제 노선 선형이 없어 정류장 점만 표시한다. 외부 모델 자유 서술 전체의 의미 정확성을 보장하는 검증은 아니며, 이번 실제 두 질문과 기록 재생에서 확인한 범위만 보고한다. 기존 shapely 등 deprecation 경고는 이번 표시 수정 범위 밖으로 남겼다.
