# 방법 검증 구현·실행 기록 — 2026-11-23

## 구현 범위

검토 후 우선 권장한 ①정보 누출을 차단한 mask-and-recover ②파라미터 민감도 확장 ⑤동일월 대중교통 수요 사분면을 구현했다. 운영 후보 순위를 새 실험에 맞춰 수정하지 않았다. Louvain·K-means 재학습·추가 계절 비교·도로망 전수 분석·Solar 신규 도구/유료 호출은 이번 범위가 아니다.

- 공통 검증월: 2025-12-01~31.
- 각 도시8조건의 민감도: 총24조건.
- 각 도시6개 가림 실험: 총18조건. 무작위 비교는 fold당30회.
- 수요 매트릭스: 서울·대전, 300/500m 사분면 비교.
- 읽기 전용 GET /api/method-validation?city=all|seoul|daejeon|sejong.
- web: 개선 지역 찾기·자전거 이용 분석의 공통 접기 패널.
- React: 개선 지역 찾기의 같은 검증 접기 패널.
- 화면은 사용자가 결과를 펼칠 때 저장된 산출물을 조회한다. 기존 무거운 KPI 로딩에 추가 계산을 붙이지 않았다.

## 실제 결과

### 민감도

기준 TOP10과 반경300m 이내 일대일 위치 중첩:
- 앵커500→300m: 서울60%, 대전90%, 세종90%.
- 앵커500→800m: 서울70%, 대전80%, 세종100%.
- 격자500→250m: 서울40%, 대전30%, 세종10%.
- 격자500→750m: 서울0%, 대전10%, 세종40%.

격자 이산화가 후보 위치에 큰 영향을 준다. ‘어떤 설정에서도 대부분 유지’라고 결론 내릴 수 없다. 300m 대응 허용범위에서의 결과이며 범위 밖 후보가 실제로 완전히 다른 생활권임을 뜻하지 않는다. 버퍼500m는 순위를 바꾸는 인자가 아니므로 순위 유지 성과로 해석하지 않는다.

### 가림 후 재발견

- 이용량 상위10개소 가림: 서울0/10, 대전0/10, 세종0/10.
- 이용량 구간 표본: 서울·대전은3반복 모두0/10, 세종은1/10·0/10·0/10.
- 1km 구역 전수 가림: 서울0/22·0/19, 대전0/28·0/25, 세종1/46·1/43.

전체 방법이 기존 인기 대여소를 잘 회복한다고 주장할 근거를 얻지 못했다. 생성 가능한 후보가 없는 목표가 많고, 실제 수요 재발견보다 공백·최소 설치 간격·시설 조건으로 구성된 현재 후보 규칙의 적용 범위 차이가 드러났다. 이것이 공간 후보 전체가 무효라는 뜻은 아니며, 재발견 성능과 실제 설치 효과를 혼동하지 않는다.

숨긴 대여소와 관련된 OD 양 끝의 활동을 모두 제거하고 남은 수요를 재집계했다. 기존 원수요를 fallback하지 않았다. 순위는 같은 후보 풀의 단순 수요·시설/인구·무작위와 비교했다. 서로 겹치는 fold를 독립 표본으로 가정한 유의성·신뢰구간을 만들지 않았다.

### 대중교통 수요 매트릭스

| 도시 | 위치 연결 | 분류 대상 | 둘다높음 | 대중교통높음·자전거낮음 | 반대 | 둘다낮음 | 300/500m 분류 유지 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 서울 | 233 | 232 | 74 | 42 | 42 | 74 | 198/232 |
| 대전 | 22 | 22 | 8 | 3 | 3 | 8 | 20/22 |
| 세종 | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

서울 신내역의 원본 산출물 승하차 합계0을 실제 무수요로 단정하지 않고 분류를 보류했다. 이로 인해 중간 실행의233역·41곳에서 최종232역·42곳으로 중앙값 기반 분류가 바뀌었다. 원본 transit-demand 산출물과 기존 API는 변경하지 않았다. 세종은 같은 달 BRT 승하차 자료가 없어 대체 수치를 생성하지 않았다.

## 검증

- 기존130건+신규12건 포함 **142 passed**, 경고31건.
- Python compileall backend/scripts 성공.
- React TypeScript/Vite 빌드, web main 빌드 성공.
- 각 도시 기준 신규 후보 TOP10 ID·점수가 기존 운영 사전 집계와 일치(1e-12 허용오차).
- 기존 입력 revision e830d4d1d65fbd2f25d771678f3fc182779b7dabaffb1e7dca65777012cb9a59 유지.
- release --verify-only: 공통16조합128결과, 도시별 전체기간52액션씩, 2025년 월별12개월 확인. 배포 명령은 실행하지 않음.
- 실제 로컬 API: 유효4요청200, 미지원 도시404. 이번 최종 측정에서 유효 요청15~59ms. 준비된 프로세스·로컬 조회이며 외부 배포 콜드스타트 성능 아님.
- Chromium: React3도시 전환·지연 조회·서울232/대전22 산점도·세종 미확보 안내, WIZ전체3도시254개 실제 역점·도시별8조건 표 확인.
- 브라우저 페이지 오류0, 확인한 PC·모바일 화면 가로 넘침 없음.
- web 장기 실행 API 핸들러가 이전 Python 코드를 유지하는 환경이 확인되어, 신규 조회는 이미 있는 read-only FastAPI 브리지 /bike-link-ui/api/method-validation로 연결했다. 서버 전체 재시작·배포는 하지 않음.
- 원본·기존 KPI·도시별 전체기간 패킷 삭제·재집계·Git push 없음.

## 파일

- backend/research/__init__.py, method_validation.py, presentation.py: 격리된 오프라인 실험·엄격한 읽기.
- backend/main.py: 조회 엔드포인트.
- backend/tests/test_method_validation.py: 누출·일대일매칭·전체구역 가림·운영동등성·미확보·0보류·stale 차단·읽기전용 회귀.
- scripts/validate/build_method_validation.py: 실제3도시 배치와 표 생성.
- scripts/validate/plot_method_validation.py: 실제 역 수요 PNG·SVG.
- scripts/validate/method_validation_browser.py: 실제 화면 회귀.
- frontend/src/components/MethodValidation.tsx, pages/Improvements.tsx.
- web src/app/component.bike.link/view.ts, view.pug, 대응 integrations/prepared source export/manifest.
- data/reference/method_validation_202512.json: 입력 버전·실험 코드 해시·세부조건·결과·진단.
- README.md, METHOD_VALIDATION.md, METHOD_VALIDATION_RESULTS.md, METHOD_VALIDATION_API.json, 이 문서.
- docs/method-validation-20261123/: 실제 PC·모바일 캡처4장, 수요 그림PNG/SVG, browser.json.

방법·조건은 [METHOD_VALIDATION.md](METHOD_VALIDATION.md), 전체 실측 표는 [METHOD_VALIDATION_RESULTS.md](METHOD_VALIDATION_RESULTS.md)에 있다.
