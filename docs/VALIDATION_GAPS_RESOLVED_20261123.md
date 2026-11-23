# 부족 사항 후속 보완 — 2026-11-23

기존 데이터·전체기간 산출물·운영 후보 점수를 보존했다. 아래 보완은 방법의 평가 목적·해석·사용 흐름을 정리한 것이며, 재발견 성능 향상을 보장하거나 실패를 성공으로 바꾼 것이 아니다.

## 감사 항목별 처리

| 문제 | 처리 |
|---|---|
| 높은 이용 대여소 재발견과 교통 공백 설치 규칙의 목적 불일치 | 원래0/10 결과 보존. 앵커500m 밖·다른 대여소300m 밖의 관측 대여소를 별도 코호트로 정의하고 후속9조건 실행. 후보 생성 불가와 TOP10 순위 밖을 구분 |
| 격자 크기에 민감한 추천 | 기준 TOP10의 조건별 유지 횟수를 별도 표시. 동일 격자5조건의 ID 일치와 다른 격자2조건의300m 일대일 근접 대응을 구분. 버퍼만 바꾼 조건 제외. 기존 점수에 가산하지 않음 |
| React 개선 직접 URL404 | 현재 프로젝트의 Bike viewer route 코드 캐시만 source SHA에 따라 갱신. 다른 route·프로젝트·urlmap 캐시는 그대로 유지. 직접 접속·새로고침200 확인 |
| 새 검증 결과를 Solar가 읽지 못함 | get_method_validation 등록, 기간·역·대여소 인자 검증, 실제 소스·0복구·사분면·후속평가·반복 후보를 구조화 근거로 반환. 보고서 카드에 실제0과42를 유지 |
| 수요 매트릭스가 지도·상세와 단절 | 역 선택/표의 지도 버튼 → 실제500m 내 대여소 지도·선택 지표 → 공통12월 상세·AI 보고서 연결. 기존 합계와 주변 대여소 수·활동량 정확히 대조 |
| README/화면 기간 혼동 | 전체 비교·방법 검증은 공통2025-12, 개별 도시는 서울2025년/대전2024-08~2026-10/세종2020~2025년 구분. reference=2025-12 링크는 상세·AI까지12월 유지 |
| 설명 부족·영문 정책명 | 핵심 발견 요약, 실패 단계 설명, 조건 충족 코호트·반복 횟수의 의미 표시. web equal/demand/gap를 균등/주변 수요 우선/공백 우선으로 교체 |

## 평가 설계와 실제 결과

기존 실험을 본 뒤 설계한 **탐색적 후속평가**다. 독립된 새로운 기간에서 성능을 입증한 것으로 취급하지 않는다. 공간 조건은 새 실행 전에 코드로 고정했고, 좋은 결과가 나올 때까지 거리·표본·점수를 바꾸지 않았다.

공통2025년12월의 경계 내·유효좌표·실제 이용 대여소를 사용한다. 다른 대여소와의 거리는 자기 자신을 제외한다. 가린 ID를 위치 목록에서 빼고 출발/도착 중 한쪽이라도 가린 ID인 모든 OD를 제거한 뒤 남은 수요를 재집계한다. 가린 이용량은 학습 특징으로 복원하지 않는다.

| 도시 | 경계 내 이용 대여소 | 사전 공간 조건 충족 | 조건 충족 중 이용 상위10 | 무작위 표본71 | 무작위 표본72 |
|---|---:|---:|---:|---:|---:|
| 서울 | 2,746 | 291 | 0/10 | 0/10 | 0/10 |
| 대전 | 1,372 | 121 | 0/10 | 0/10 | 0/10 |
| 세종 | 725 | 29 | 1/10 | 3/10 | 1/10 |

여전히 서울·대전에서 실제 위치 재발견 성능을 입증하지 못했다. 후보 생성 공간 제약과 순위의 한계가 모두 남아 있다. 후속 코호트 결과가 원래 상위 이용 가림의 세 도시0/10을 대체하지 않는다.

반복 표시 예시:
- 서울 grid-961000-1952500: 같은 격자5/5, 변경 격자 근접1/2.
- 대전 grid-987000-1811500: 같은 격자5/5, 변경 격자 근접2/2.
- 세종 grid-981000-1830000: 같은 격자5/5, 변경 격자 근접2/2.

반복 횟수는 관측 조건 아래의 상대 안정성이다. 실제 설치 타당성·운영 효과를 확정하지 않는다.

## 지도·AI와 기간

서울42개·대전3개 ‘대중교통 높음/자전거 낮음’ 역을 기존 실제 좌표로 연결했다. 각 역500m 내 대여소 수와 대여+반납 합계가 기존 사분면 원수치와 일치해야만 배치를 완료한다. 세종은 같은 월 BRT 승하차 자료가 없어 억지로 역별 후보를 만들지 않는다.

React에서 검증 지도를 선택하면 /stations?reference=2025-12&region=...&station=... 또는 같은 reference의 /agent로 이동한다. 12월 전용 배너·헤더·API 조건을 유지한다. 일반 메뉴로 이동하면 원래 개별 전체기간 분석으로 복귀한다.

WIZ는 지도 점/목록으로12월 대여·반납을 표시하고, 선택한 역·대여소와12월 context로 별도 AI 보고서를 요청한다. 전체기간 전역 선택을12월로 몰래 변경하지 않는다. 지도 마커는 실제 마우스 선택과 키보드 활성화를 지원한다.

## 실제 Solar 검증

실제 요청1회, HTTP200. 새 도구를 선택했고:
- 분석 기간2025-12-01~31 일치.
- 원래 이용 상위10곳 가림 복구0곳 유지.
- 서울 대중교통높음/자전거낮음42역 일치.
- 실제 소스 근거 반환.
- 한국어 답변에서 검증 성공으로 해석하지 않는다고 명시.

총23,510토큰(prompt23,407/completion103). 자유 서술 전체를 자동 보증하는 의미 검증은 아니며, 이번 답변의 두 수치는 실제 근거와 대조했다. 추가 유료 호출은 하지 않았다. 재실행은 명시적 --live가 있어야 가능하다.

## 검증 결과

- 기존142건+신규9건: **151 passed**, 경고31건.
- Python compileall backend/scripts 성공.
- React TypeScript/Vite 빌드·web main 빌드 성공.
- 검증보고서 API4도시 모드200. 실제 로컬 조회55~195ms(이번 프로세스 측정, 외부 배포 콜드스타트 아님).
- 강남 점검 역 API200, 존재하지 않는 역404.
- React dashboard/improvements/stations/network/agent 직접 URL 모두200.
- 실제 Chromium: 개선 URL 직접 진입·새로고침, 역 지도·대여소 선택,12월 상세·AI 조건 전달, web 전체3도시 요약·반복·후속평가·마커 선택 확인.
- PC·모바일 페이지 오류0, 확인한 화면의 가로 넘침 없음.
- 기존 공통16조합128결과, 각 도시 전체기간52액션씩, 월별12개월 release --verify-only 통과. 실제 배포 명령은 실행하지 않음.
- 원래 방법 보고서와 공통 입력 revision 유지. Git push·원본 삭제·배포 없음.

[API 결과](validation-followup-20261123/api.json) · [브라우저 결과](validation-followup-20261123/browser.json) · [실제 Solar 기록](validation-followup-20261123/solar.json)

## 실행

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m scripts.validate.build_validation_followup
python -m pytest backend/tests -q
python -m scripts.validate.validation_followup_browser
# 유료 검증은 별도 선택
python -m scripts.validate.validation_followup_live_solar --live
```

후속 산출물 data/reference/method_validation_followup_202512.json은 입력 revision, 기존 실험 코드·원래 보고서·후속 코드 SHA와 대조한다. 불일치 시 후속자료를 표시하지 않으며 원래 보고서를 덮어쓰지 않는다.

## 수정 파일

- backend/research/validation_followup.py, runtime.py, presentation.py.
- scripts/validate/build_validation_followup.py, validation_followup_browser.py, validation_followup_live_solar.py, method_validation_browser.py.
- backend/main.py, backend/agents/solar.py, backend/tests/test_validation_followup.py.
- backend/presentation/viewer_cache.py, web component.bike.viewer.health.
- web component.bike.link/view.ts·view.pug, integrations/prepared export.
- frontend/src/App.tsx, components/MethodValidation.tsx·ValidationReview.tsx.
- README.md, METHOD_VALIDATION.md 후속 링크, 이 문서·검증 JSON/캡처, 개발로그.

## 남은 한계

실제 환승·재고·용량·현장 설치 가능성·인과적 효과 자료는 추가로 필요하다. 세종 동일월 BRT 승하차량은 미확보다. 격자 변화에 민감하고 재발견 성능이 낮으므로 현재 방법을 검증된 신규 수요 예측 모델로 발표해서는 안 된다. 이는 구현 오류와 별개인 실제 분석 결과다.
