# 대중교통 연계 주제 확장 최종 보고 — 팀234
검증일 2026-11-12. Phase 완료 기준 순서에 따라 진행했고, 원본·기존 분석 기능·Demo Mode를 보존했다.

| Phase | 완료 근거 | 로컬 커밋 |
|---|---|---|
| 1 | 서울 정류장11,504개, 대여소2,762개 연계, 서울 OD합계4,245,954건 일치, 28 tests·compileall·React 통과 | 43b40df / feat: add transit stop linkage analysis |
| 2 | 실제 후보9개 지도·순위·시나리오 API·Solar 신규 도구 실호출, 30 tests·React·WIZ 통과 | add2940 / feat: detect transit-vulnerable segments and improvement ranking |
| 3 | 원본8,008,537행 Spark실행, 유효7,605,738건 및 상세 집계 동등성, 31 tests | 2a796f4 / feat: add pyspark batch aggregation pipeline for tashu trips |
| 4 | 세종 원본 미확보·신청 절차 공식 근거, README 연구 질문·기능·API·검증 정렬 | docs: realign research question to transit-linkage theme |

## 실제 결과
서울2026-10 역300m 인접 이동2,220,479건/4,245,954건(52.2964%). 실제 환승률이 아니다.
취약 후보9개. ST-3277 570.948m/836건/점수0.870370, ST-2488 624.494m/122건/0.574074, ST-405 545.469m/645건/0.574074.
공간 커버540.162489→541.035186km²(+0.161562%), 커버 대여소2753→2756개(+0.108972%). 인구 효과는 null.
Solar 실호출1질문, 신규도구 get_transit_vulnerability 선택, 수치41/41·ID 검증 통과·finish_reason stop, 입력5066/출력567/총5633토큰. 검증은 원문 의미 전체를 보증하지 않는다.
Spark 일별OD5,350,360행·station_usage4,502,831행이 기존SQLite와 양방향 차이0. 시간OD6,855,588행은 기존Trip 독립SQLite와 차이0. 월/시간OD4,164,960행은 시간OD 월집계와 차이0.

## 변경 영역
- 수집: collect_transit_stops.py, normalize_transit.py, build_transit_linkage.py.
- 분석/API: analysis/transit.py, services/transit.py·vulnerability.py, backend/main.py.
- Solar: 기존14개+신규2개 도구, 구조화 거리·수요 카드·출처·제안, 기존 기간·수치 보호 유지.
- 화면: WIZ component.bike.link api.py/view.ts/view.pug, React TransitPanel·NetworkAnalysis.
- Spark: spark_tashu.py 전처리·검증, 선택형 requirements, fixture·스모크.
- 문서/기록: README, DATA_SOURCES, data-contract, 아래 전문 문서, 날짜별 개발로그.

## 검증 기록
최종 백엔드31 tests passed(2개 기존 경고), compileall 통과. React tsc/Vite489모듈·WIZ 빌드 성공. WIZ 데스크톱·모바일 취약 지도9마커·토글·상세 이동·AI근거 카드7개·출처2개 렌더링, 페이지 오류0·가로넘침 없음. React의 별도 브라우저 조작은 이번에 하지 않았고 빌드로 확인했다.
실제 원본/대용량 산출물은 기존 gitignore 정책으로 제외했다. 파일 삭제·운영DB 교체·Git push·실제 배포 없음. 다른 사용자 변경은 스테이징하지 않았다. 개발로그 요약은 기존 미커밋 이력을 포함하지 않고 이번 행만 부분 스테이징했다.

## 한계·필요한 수동 작업
1. 대전·세종 정류장: TAGO 활용신청 승인 후 키 또는 공식CSV 제공 필요. 미확보 도시 취약도를0으로 표시하지 않음.
2. 세종 일/시간/OD: 세담터 개인정보 동의·이용신청 절차 필요. 현재 총량 수준 비교까지만 지원. 공개 메타데이터를 실제 원본으로 혼동하지 않음.
3. 서울 지하철1~8호선 일부 범위·자료 시점 차이. 취약 후보 과대 탐지 가능.
4. 인구·보행망·행정경계 미확보. 공간버퍼는 실제 개선 효과가 아님. 효과 검증에는 보행·환승·재고·운영자료와 시나리오 가정 검토 필요.
5. 동등 가중 검토 점수는 최적 운영 효과 예측이 아님. 기존 낮은 K-means 분리도와 표본 매개 중심성 한계도 유지.

## 문서·실제 증거
- [자료/스키마/재현](TRANSIT_LINKAGE.md)
- [취약도/시나리오/순위/화면](TRANSIT_VULNERABILITY.md)
- [Spark 상세 동등성](SPARK_TASHU_PIPELINE.md)
- [세종 원본 접근 확인](SEJONG_TRANSIT_AVAILABILITY.md)
- [실제 JSON·캡처](transit/)
