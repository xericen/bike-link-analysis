> 최신: planning을 포함한 **27조합×8액션=216개**, SHA256 입력 manifest·대상 서버 verify-only·readiness 점검을 사용합니다. 아래 mtime·189/162/135개 설명은 이전 단계 기록입니다. [현재 운영·자료·공식](PLANNING_IMPROVEMENTS.md).

> 목표 화면 개편 후 최신 상태: transit_linkage를 추가하여 **27조합×7액션=189개**를 준비했다. 연계 KPI·시간대 OD·지도 데이터도 WIZ와 Solar에서 저장값만 조회한다. [화면 개편 및 검증](GOAL_ALIGNED_REDESIGN.md). 아래162/135개는 이전 단계 기록이다.

> 최신 확장: vulnerability 액션을 추가하여27조합×6액션=162개가 준비됐다. `/api/vulnerability`·`/api/improvement-ranking`·WIZ·Solar도 저장값만 조회한다. 아래135개와55개 테스트·속도 기록은 앞 단계의 역사적 실행 결과이며 이번 측정과 구분한다. [최종 공식·가중치·실행 결과](TRANSIT_VULNERABILITY_FINAL.md).

# 배포용 핵심 지표 사전 집계 — 2026-11-16

## 실행·조회 분리
WIZ의 overview / research(TOP3·숨은 연결·불균형 후보) / network / centrality / dashboard_extra는 이제 precomputed.read로만 조회한다. 기존 FastAPI 분석 API, React, Solar의 실제 분석 함수는 보존한다. 새 GET /api/precomputed/{city}/{action}도 같은 저장값을 반환한다.
data/processed/kpi_cache.sqlite의 기본키는 도시·시작일·종료일·action이며 데이터/분석 코드 버전을 함께 검증한다. 조회 연결은 SQLite mode=ro이고, 계산 함수 import나 계산 fallback이 없다. 미준비·오래된 버전은 HTTP409로 즉시 안내하며 다른 기간의 수치로 대체하지 않는다.

## 갱신 절차
정류장/대여소/OD/분석 코드 변경 후 갱신 배치에서 실행하고, 종료코드0 및 검증을 확인한 다음 배포한다. 이번 작업에서 실제 배포나 재시작은 하지 않았다.
```bash
cd bike-link-analysis
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/preprocess/precompute_city_kpis.py
# 사용자가 지정할 별도 기간도 배포 전 준비
PYTHONPATH=. python scripts/preprocess/precompute_city_kpis.py --city daejeon --start 2026-09-01 --end 2026-10-31 --report docs/transit/custom-kpi-build.json
```
기본 배치는 도시별 전체 관측 기간·마지막7/14/30일·대전 월별·서울/대전 공통 전체/7/14/30일을 준비한다. 임의의 모든 날짜 조합을 미리 계산하지 않는다. **준비하지 않은 사용자 지정 기간은 안내 상태이며 배치 준비가 필요하다.** 기존 수동 분석 API는 계속 사용할 수 있다.
자료/분석 코드가 바뀌지 않은 이미 준비된 키는 다시 계산하지 않는다. 생성 도중 자료 버전이 바뀌면 중단한다. 단일 배치 작업으로 운영한다. 원본/DB/캐시는 Git 제외 정책 유지, 배포 환경에서 같은 실제 자료로 명령을 실행해야 한다. 현재 파일 버전은 크기+mtime이므로 다른 환경으로 복사 후 재생성이 필요하다.

## 정확성·성능 검증
pytest는 정확한 기간/버전 키, 자료 변경 무효화, 미준비409, 조회 시 파일 생성 없음, 실제 분석 함수를 실패하도록 바꿔도 API가 저장값을 반환하는 것을 검증한다.
[실제 생성 기록](transit/precomputed-build-20261116.json)과 [조회 시간 측정](transit/precomputed-performance-20261116.json)을 별도로 남긴다. 생성 시간은 요청 응답 시간과 다르며, OS 파일 캐시를 강제로 지우지 않았다. 첫 프로세스 조회와 동일 프로세스 반복 조회를 구분한다. 실제 외부 배포 서버 성능을 측정했다고 표현하지 않는다.

## 한계
세종2025-10 자료는 좌표/실명 마스터가 없어 지도·연계거리 N/A다. 세종 자료는 서울·대전2026-10 공통 합계에 섞지 않는다.
사전 집계는 기존 후보 알고리즘 결과를 저장하며 운영 효과를 새로 추정하지 않는다. 큰 원본은 Git에 포함하지 않고 동일 자료와 배치 명령으로 재현한다.

## 이번 실행 결과
27개 도시·기간 조합 × 5액션 =135개 준비. 기존 데이터 분석 API의 TOP3/후보 결과를 그대로 저장했다. 전체2026-10의 불균형269개=서울207+대전62를 확인했다.
완료 후 WIZ HTTP 대전2026-10 research40.379ms, 전체61.700ms. 브라우저 도시 전환부터 KPI 표시까지 대전475.772ms/전체863.981ms. DB 첫 조회/반복은 성능JSON에 개별 기록한다.
집계 준비 도중 첫 WIZ 호출에서 대전 overview4843.333ms/research789.247ms가 관측되었고, 첫 브라우저 시도는30초 안에 연구 후보 표시를 확인하지 못했다. [준비 중 관측](transit/precomputed-performance-during-build-20261116.json)을 완료 후 결과와 구분한다. 강제 서버 재시작·OS 캐시 제거는 하지 않았으므로 콜드 부팅 보장이나 외부 배포 성능으로 주장하지 않는다.
완료 후 Chromium 재검증은 대전·전체·대여소 연계·이동 패턴·모바일을 통과했다. [브라우저 기록](transit/precomputed-browser-20261116.json). 페이지 오류0·가로 넘침 없음. 기존/신규 pytest55건·compileall·React/WIZ 빌드 통과, 외부 Solar 유료 호출 없음.
