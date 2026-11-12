# WIZ 화면 통합 소스

현재 WIZ 프로젝트의 빅데이터개론 전용 컴포넌트와 Leaflet 스타일을 보관한 스냅샷입니다. 저장소 루트의 React 프론트엔드는 별도로 실행할 수 있습니다. 이 디렉토리만으로 WIZ 서비스 전체가 실행되지는 않습니다.

## 필요한 환경

- WIZ Angular 프로젝트와 기존 `portal/season` 패키지의 `Service`.
- Angular 프로젝트의 `leaflet` 및 타입 선언 의존성.
- 저장소 루트 `backend/requirements.txt`의 Python 의존성과 로컬 `.env`, 실제 정규화 데이터.
- WIZ 프로젝트 루트의 `bike-link-analysis/`에 이 저장소 내용 배치. `api.py`가 `wiz.project.path("bike-link-analysis")`로 분석 코드를 찾습니다.

## 통합 방법

1. 이 디렉토리의 `src/app/component.bike.link/`와 `src/assets/bike-link/`를 대상 WIZ 프로젝트의 같은 상대 경로로 배치합니다. 기존 파일이 있으면 먼저 변경을 대조하세요.
2. 부모 화면에서 `wiz-component-bike-link`를 렌더링합니다. `embeddedRegion`, `embeddedTab` 입력과 `stationNavigate`, `navigate` 출력을 기존 화면의 탐색에 연결할 수 있습니다.
3. WIZ 절차에 따라 소스와 API를 빌드합니다. 이 저장소의 `frontend/`는 Vite/React 전용이므로 WIZ 컴포넌트를 빌드하지 않습니다.

공용 과목 페이지·로그인·사이드바·DB 설정·계정·과목 콘텐츠는 이 스냅샷에 포함하지 않았습니다. 이 파일들은 기존 프로젝트에 의존하며 개인정보와 다른 과목 변경을 보존하기 위해 내보내지 않았습니다.

검증 스크립트의 로컬 WIZ URL, 브라우저 실행 파일, `/tmp/bike-playwright` 경로는 기존 검증 환경 기준입니다. 다른 환경에서 실행하려면 해당 경로와 Playwright 설치를 준비해야 합니다. Solar 검증 스크립트는 유료 요청을 수행할 수 있습니다.
