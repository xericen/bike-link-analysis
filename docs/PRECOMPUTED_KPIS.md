# 사전 집계 — 공통 2025년12월

현재 기본 분석 기간은 서울·대전·세종·전체 모두 **2025-12-01~31**이다. 각 도시의 월 전체·최근30일·14일·7일과 전체 도시의 같은 조합, 총 **16조합 × 8액션 = 128결과**를 준비한다.

8액션: overview, research, network, centrality, dashboard_extra, vulnerability, transit_linkage, planning.

## 원칙

- 세 도시는 개별 Trip을 같은 출발 기간으로 정규화한다. 전체에는 세종도 포함한다.
- 도시별 ID를 보존하고 통합 그래프에 도시 접두사를 붙인다. 도시 간 이동을 생성하지 않는다.
- API는 준비된 결과만 조회한다. 누락 시 다른 기간으로 대체하거나 요청 중 공간 계산을 하지 않는다.
- 결과 버전은 입력 내용 해시와 계산 코드로 판정한다. 입력이 바뀌면 재검증·재집계를 요구한다.
- 원본·이전 정규화 자료는 보관한다. 현재 기간 이전의 사전 집계 행이 DB에 남아도 다른 revision이므로 사용하지 않는다.
- 후보·면적·시간대·AI 근거 패키지도 같은 연구 기간으로 다시 만든다.
- 기준일이 다른 위치·정류장·인구·시설은 별도 보조 자료로 표시한다. 인구밀도를2025년 값으로 이름만 바꾸지 않는다.

## 재생성

저장소 루트, 기존 실행 환경과 공식 보조 자료가 필요하다.

```bash
export PYTHONPATH=.
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
python scripts/collect/collect_common_december.py
python scripts/preprocess/common_december.py
python scripts/preprocess/common_december.py --activate
python scripts/preprocess/precompute_city_kpis.py --workers 2 --report docs/transit/common-december-kpis-20261118.json
python scripts/validate/common_december_validation.py
python scripts/validate/anchor_presentation_audit.py
python scripts/validate/decision_inputs.py
python scripts/collect/audit_candidate_routes.py
# 필요할 때 동일 조건 비교 실험 갱신: 유료 모델 호출
python scripts/validate/solar_paired_evaluation.py
python scripts/validate/decision_evidence.py
python scripts/deploy/release.py --verify-only
```

common_december.py는 스테이징 중복 생성을 거부한다. 이미 검증된 스테이징이 있으면 그 결과를 확인하고 --activate 단계부터 사용한다. 재수집·재정규화가 필요한 경우 기존 스테이징을 별도 보관한 뒤 시작한다. 활성 자료는 data/processed/period_archive/ 아래에 보관하고 새 검증본으로 교체한다.

선택 기간만 준비하는 예:

```bash
PYTHONPATH=. python scripts/preprocess/precompute_city_kpis.py --city daejeon --start 2025-12-18 --end 2025-12-31 --report docs/transit/custom-kpi-build.json
```

## 배포 준비

정규화 데이터·사전 집계 DB·kpi_inputs.json·kpi_verified.json과 data/processed/research/ 근거 패키지를 같은 아티팩트에 포함한다. release.py의 준비 검사는 현재 revision의 모든 필수 액션과 근거 패키지를 확인한다. 이 명령에 별도 배포 명령을 전달하지 않은 이번 작업에서는 준비 검사만 실행했다.

## 실제 검증

- [128개 결과 생성 기록](transit/common-december-kpis-20261118.json)
- [31일 × 3도시 집계 대조](common-december-validation-20261118.json)
- [실제 브라우저·모바일](common-december-browser-20261118.json)
- [실제 전체 도시 Solar 맥락·도구 근거](common-december-solar-20261118.json)

이전2026-10/2025-10 검증 문서는 과거 기록이다. 현재 기본기간·결과와 혼용하지 않는다.
