# Bike Link Analysis 최종 검증 결과 — 2026-11-12

## 완료 범위
실사용 WIZ Angular 다섯 메뉴를 기준으로 기간 선택, 통합 도시 조회, 대여소·네트워크 탐색, 군집 안정성, Solar 근거 보고서를 연결했다. 기존 React·FastAPI·SQLite·14개 Solar 도구와 실제 원본은 보존했다.

## 데이터 재검산
| 범위 | 실제 이용량 | 관측 대여소 | 관측일 |
|---|---:|---:|---:|
| 서울 2026-10-01~31 | 4,245,954 | 2,759 | 31 |
| 대전 2025-12-01~2026-10-31 | 7,605,738 | 1,403 | 335 |
| 대전 2026-10-01~31 | 923,578 | 1,383 | 31 |
| 전체 공통 2026-10-01~31 | 5,169,532 | 4,142 | 31 |

전체 유효 고유 OD 연결은 600,047개다. 서울 집계 OD와 대전 개별 Trip 정의는 유지하며 통합 건수는 이질적 관측 기록의 합이다. 세종 연간값은 일별 OD 합계에 넣지 않는다. 서울 X 관련 원본 18,535건은 보존하고 지도·유효 중심성에서는 제외했다.

## 핵심 사례와 신뢰성
서울 10월 ST-1481 이용량 1,640위·PageRank 280위, ST-3031 17시 비중 40.91%, ST-2264 순유출 -1,582건을 재검산했다. ST-1481의 7/14/30일 PageRank 순위는 256/256/285위, ST-2264 순유출은 -380/-724/-1,503건으로 관측 기간 모두 반납 우세다. 재고 부족·환승 역할·재배치 효과는 확정하지 않는다.

서울 7/14/30일 Silhouette는 .0939/.1082/.1239, 공통 대여소 ARI는 .6794/.7164다. 대전은 .0803/.0843/.1212, ARI .5946/.5828이다. 낮은 군집 분리도는 경고하고 군집 목적 해석을 보류한다. 매개 중심성은 32개 표본 근사다.

## 실행 검증
- 기존 15개 포함 백엔드 22개 테스트 통과, 기존 deprecation 경고 2건.
- React TypeScript/Vite 빌드 성공, 최종 WIZ 일반 빌드 성공(errors null).
- Chromium 데스크톱/모바일 다섯 메뉴, 도시·전체, 7/14/30일, 검색·지도·노드·카드 이동, 군집 안정성, 빈 자료·범위 오류 확인. 페이지 오류 0, 가로 넘침 없음.
- 기간 KPI SQL 독립 대조: 7일 890,565 / 14일 1,748,118 / 30일 4,080,713건. 이전 기간 응답이 덮어쓰지 않도록 요청 세대·캐시 키·화면 초기화 적용.
- Solar 실제 질문 5건 HTTP 200, 총 89,772토큰. Q2 잘못된 top_n 인자 거절 후 근거 보강. Q4 원문 수치 불일치 발견: 기본 답변 보류, 도구 기반 요약 표시. 모든 자유 서술의 정확성 검증 완료로 보고하지 않는다.
- 실제 응답의 일부 문장 잘림 확인. 당시 종료 사유는 기록하지 않아 확정 불가. 최종 길이 종료 보호와 간결 응답 지시는 테스트했으나 추가 실호출하지 않았다.
- 서울 7일 overview 캐시 우회 재계산 .4100초/준비 후 .0668초, network 1.6058초/.0229초. TestClient 처리 시간으로 OS 캐시 초기화와 전송 지연은 포함하지 않는다. 최초 새 리비전 분석이 모두 이 속도라고 보장하지 않는다.

## 변경 파일
- src/app/component.bike.link/{view.ts,view.pug,view.scss,api.py}
- bike-link-analysis/backend/services/{periods.py,all_regions.py,real_data.py,wiz_bridge.py}
- bike-link-analysis/backend/analysis/clustering.py
- bike-link-analysis/backend/agents/solar.py
- bike-link-analysis/backend/models/schemas.py
- bike-link-analysis/backend/main.py
- bike-link-analysis/backend/tests/test_final_review.py
- bike-link-analysis/scripts/validate/{final_review.py,final_performance.py,final_solar_browser.py,final_browser.py,final_documents.py}
- bike-link-analysis/docs/FINAL_*.md 및 docs/final-validation/*

## 미해결·제한
세종 상세 데이터 미확보 및 공식 기준일/보유 메타데이터 불일치, 서울 과거 좌표 정확성 미검증, OA-14994 두 열 일별 총량의 OD 대체 불가, 낮은 군집 품질과 근사 중심성, AI 자유 서술 의미 전체 자동 보증 불가, 새 데이터 최초 분석 비용이 남는다. 추가 외부 호출을 늘리지 않고 보호 동작을 검증했다.

## 검증 자료
- [실제 분석](FINAL_ANALYSIS_VALIDATION.md)
- [지표 계산식](FINAL_ANALYSIS_FORMULAS.md)
- [Solar 실호출과 실패 보호](FINAL_SOLAR_VALIDATION.md)
- [브라우저·성능](FINAL_BROWSER_PERFORMANCE.md)
- [공식 출처 확인](FINAL_DATA_SOURCES.md)
- [최종 발표 흐름](FINAL_SERVICE_GUIDE.md)

Git push·실제 배포·서버 재시작은 수행하지 않았다. 다른 프로젝트와 기존 사용자 변경을 보존했다.
