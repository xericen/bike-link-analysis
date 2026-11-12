# 최종 사용자·성능 검증 — 2026-11-12

## 실제 브라우저

| 조작 | 결과 |
|---|---|
| {"quick_days": 7, "start": "2026-10-25", "expected_sql": 890565, "loading_observed": ["분석 자료를 불러오는 중입니다…"]} | 통과 |
| {"quick_days": 14, "start": "2026-10-18", "expected_sql": 1748118, "loading_observed": ["분석 자료를 불러오는 중입니다…", "실제 이용·연결·불균형 결과를 계산 중입니다…"]} | 통과 |
| {"quick_days": 30, "start": "2026-10-02", "expected_sql": 4080713, "loading_observed": ["분석 자료를 불러오는 중입니다…", "실제 이용·연결·불균형 결과를 계산 중입니다…"]} | 통과 |
| {"invalid_order_error": true} | 통과 |
| {"map_station_click": "서울 ST-735"} | 통과 |
| {"station_search": "ST-1481", "history_bars": 3, "cluster_stability_rendered": true} | 통과 |
| {"network_node_click": true} | 통과 |
| {"unified_dashboard": true} | 통과 |
| {"sejong_annual_only": true, "date_controls_disabled": true} | 통과 |
| {"finding_card_to_detail": "ST-1481"} | 통과 |
| {"actual_response_guard_replay": true, "extra_paid_calls": 0, "raw_prose_closed": true} | 통과 |
| {"server_out_of_bounds": 422} | 통과 |

데스크톱 1273×818 및 모바일 390×844의 5개 메뉴 가로 넘침 없음, 페이지 오류 0건. 기간별 KPI는 SQL 독립 집계와 대조했다. 7일 890,565건, 14일 1,748,118건, 30일 4,080,713건으로 31일 전체와 다르며 이전 캐시 값이 남지 않았다.

## 콜드/웜 처리 시간

| API | 애플리케이션 캐시 우회(초) | 캐시 준비 후(초) | 결과 동일 |
|---|---|---|---|
| /api/regions/seoul/overview?date_start=2026-10-25&date_end=2026-10-31 | 0.41 | 0.0668 | True |
| /api/regions/seoul/network?date_start=2026-10-25&date_end=2026-10-31 | 1.6058 | 0.0229 | True |

측정은 이번 실행의 FastAPI TestClient 처리 시간이며 네트워크 전송 지연은 포함하지 않는다. 콜드는 real_data의 메모리/디스크 데코레이터를 임시 우회한 실제 분석 재계산이며 운영 캐시 파일을 삭제하지 않았다. OS 파일 캐시는 초기화하지 않았다. 웜은 원래 함수를 복구해 준비한 뒤 측정했다. 단일 요청 측정이므로 통계적 성능 보장은 아니다.

중복 요청은 진행 중 Promise 및 서버 결과 잠금으로 합친다. 화면 캐시 키는 도시/시작일/종료일/대여소 등 인자를 포함하며 기간 변경 시 기존 수치·지도·네트워크·AI 응답을 비운다. 계산 중 안내는 실제 요청 상태이며 새 리비전 최초 분석은 여전히 수십 초 걸릴 수 있다.

증거: [browser.json](final-validation/browser.json), [performance.json](final-validation/performance.json), [5개 화면 캡처](final-validation/).

## 이번 WIZ HTTP 캐시 응답 측정

같은 실행에서 측정한 WIZ HTTP 준비된 캐시 응답은 서울 overview 0.0453초/network 0.0174초/research 0.0382초, 전체 overview 0.0280초/network 0.0234초/research 0.0505초였다. 모두 코드 200이다. 위 TestClient 재계산 시간과 측정 조건이 다르며 첫 계산 속도로 해석하지 않는다. [원시 측정](final-validation/wiz-warm-performance.json)

최종 CSS에서 사이드바 세로 스크롤을 허용해 짧은 화면에서도 기간 입력에 접근할 수 있게 했다. 최종 전체 도시 문맥의 응답 보호 화면도 별도로 재생 확인했다. 총 캡처 13장을 보관한다.
