# Bike Link Analysis — Stage 3 개발 기록

작업일: 2026-11-04 (UTC) · 리뷰 ID: qczzjjzymdxmludnqafyeaqoxazpuapi

## 구현

- 기존 React/TypeScript, FastAPI, 공공데이터 수집·정규화, 분석 알고리즘을 유지했다.
- 공통 헤더에 지역·분석 기간·갱신일을 배치하고 필터를 브라우저에 유지했다. Overview, Station Analysis, Network Analysis, Region Comparison, AI Agent, Data Status를 반응형 카드 레이아웃으로 정리했다.
- Overview: 실제 관측 KPI, 공식 대여소 지도, 날짜·시간대 차트, 전체 OD PageRank 상위 5개, 4개 지역 자료 상태. 핵심 거점 수는 판정 기준이 없어 N/A로 남겼다.
- Station Analysis: 검색 지연 처리, 군집 필터·이용량 정렬, 지도 저배율 묶음 표시·마커 선택, 대여·반납량, 시간대 패턴, 동일 색상 군집, 유사 대여소 상위 5개. 서울 위치 ID와 OD ID는 결합하지 않는다.
- Network Analysis: 전체 그래프 PageRank 상위 TOP 30/40/50 노드와 해당 노드 사이의 실제 OD 연결을 서버에서 선택한다. 화면은 이동량 상위 250개 간선만 그리며 이 범위를 표시한다. 방향·가중치·노드 hover/click, 중심성 4종 순위, 선택 대여소 정보를 제공한다. 전체 중심성과 제한된 시각화 범위를 구분한다.
- Region Comparison: 데이터 확보 카드, 지역별 시간대 비율·군집 분포·중심성. 서울 OD 집계와 대전 개별 Trip의 정의가 달라 총량 직접 비교 차트는 제공하지 않는다. N/A와 비교 한계를 표시한다.
- AI Agent: 추천 질문, 대화 기록, 도구 호출 근거, 로딩·오류·재시도, 지역별 확보 상태. Solar 키 미설정 시 입력을 비활성화하며 가상 답변을 생성하지 않는다.
- Data Status: 데이터셋 링크·상태·컬럼·기간·행 수·검증 수치·분석 가능 기능과 서울 미매칭 ID 전체 목록.
- 페이지를 동적 import로 분할해 초기 JS 청크를 약 273 KB로 줄였다. 데모는 별도 Demo Mode에 유지했다.

## 데이터 검증

- 서울: OD 대여소 ID 2,748개와 좌표가 있는 위치 목록 ID 2,789개 사이 일치 0개. 미매칭 2,748개는 지도 OD 수치에 연결하지 않는다.
- 대전: 선택된 실제 Trip 50,765행 중 동일 필드 조합 5행은 잠재 중복으로 표시한다. 반납 전 대여 시각, 잘못된 이용시간, 정규화 대여소에 없는 Trip ID는 각각 0건이다. 동일 필드 조합만으로 실제 중복임을 단정하지 않는다.
- 서울·대전의 관측일 2026-10-25·29에서 대여소 대여 합계와 OD 이동 합계가 날짜별로 일치한다.
- 분석은 불연속 2일 자료에 한정한다. 세종은 연간 총량, 부산은 운영 메타데이터만 확보되어 지도·OD·군집을 만들지 않는다.

## 실행·검증

- npm install, TypeScript/Vite 빌드, FastAPI 실행 및 주요 API 응답 확인.
- pytest 백엔드 테스트 6건 통과 (TOP N 네트워크 범위 검증 추가).
- Chromium/Playwright에서 데스크톱 주요 6개 화면과 모바일 Overview를 열고 지역 선택·대여소 클릭·TOP N 변경·비교·AI 키 미설정 상태를 확인했다. 페이지 JavaScript 오류는 없었다.
- 캡처: [서울 Overview](screenshots/stage3/overview-seoul.png), [대전 Overview](screenshots/stage3/overview-daejeon.png), [부산 Overview](screenshots/stage3/overview-busan.png), [대전 Station Analysis](screenshots/stage3/stations-daejeon.png), [대전 Network Analysis](screenshots/stage3/network-daejeon.png), [Region Comparison](screenshots/stage3/comparison.png), [Data Status](screenshots/stage3/data-status.png), [AI Agent 키 미설정](screenshots/stage3/agent-no-key.png), [모바일 Overview](screenshots/stage3/overview-mobile.png).
- Solar 실호출은 키가 없어 미검증. git push·배포 없음.

## 남은 작업

- 서울 위치 ID와 OD ID를 연결할 공식 대응키 확인.
- 대전 월별 전체 기간 처리 및 세종·부산의 대여소별 원본 확보.
- Solar 키를 이용한 실제 답변 검증. 사용자 접근 환경에서 지도 타일 제공과 실사용 성능 확인.
