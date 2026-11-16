# 통합 정류장 출처·스키마·검증 — 2026-11-16

실제 확보한 GitHub 업로드 커밋18bfd1d의 원본을 사용했다. 다운로드 일자는2026-11-16이며, 원본 파일의 Git blob을 대조했다. 공식 페이지의 배포본과 이번 업로드 파일이 바이트 단위로 동일하다고 별도로 단정하지 않는다.

| 자료 | 공식 출처 | 기준일 | 원본 행 | 대상·정규화 행 |
|---|---|---|---:|---|
| 전국 버스 CSV | https://www.data.go.kr/data/15067528/fileData.do | 2026-11-09 | 227,102 | 서울17,082·대전3,259·세종3,035 |
| 전국 도시철도 XLSX | https://data.kric.go.kr/rips/M_01_01/detail.do?id=32 | 파일20260630, 행별 기준일 상이 | 1,099 | 주소 서울342→340·대전22→22·세종0 |

통합23,738행: 서울17,422·대전3,281·세종3,035. 세종 철도0은 이 파일의 주소 분류 결과이며 철도 접근성이 없다는 뜻이 아니다.

## 스키마와 식별
출력 data/processed/transit_stops.csv: city,stop_id,name,type,lat,lon (UTF-8).
city는 도시명 정확 일치 서울특별시→seoul, 대전광역시→daejeon, 세종특별자치시→sejong. 다른 도시를 근접 좌표만으로 끌어오지 않는다.
버스 정류장번호는 문자열로 보존한다. 철도는 운영기관명|노선번호|역번호의 각 요소를 UTF-8 escape하여 rail: 접두사의 충돌 없는 키로 만든다. 환승역의 서로 다른 노선은 임의로 합치지 않는다.
같은 복합키의 좌표가 같으면 행별 기준일 최신을 남긴다. 서울2건은 이수/총신대입구(이수) 별칭과 중랑역 중복이었다. 상충 좌표는 자동확정하지 않고 오류로 중단한다. [실제 제거 기록](transit/transit-integration-20261116.json).

## 경계 박스 검사
위도/경도 순서의 감사용 직사각형:
서울37.413~37.716/126.734~127.270, 대전36.17~36.50/127.24~127.57, 세종36.40~36.76/127.12~127.42.
행정경계 폴리곤이 아니라 이상치 검토용 근사 범위다. 서울576·대전199·세종725행이 밖에 있다. BIS 노선이 도시 밖까지 이어지는 경우가 있으므로 '잘못된 좌표'로 단정해 삭제하지 않고 도시명 분류를 보존했다. 모든 대상 좌표는 유한하며 한국 범위 내다. 경고는 data/processed/transit_bbox_warnings.json 및 [리뷰용 로그](transit/transit_bbox_warnings-20261116.json)에 남겼다.

## 거리·시간대 산정
haversine, 지구반경6371008.8m. 최근접 정류장 거리, 전체300/500m 수와 버스/지하철별300/500m 수. 좌표·수단 미확보는 null.
서울은 5분 슬롯 원본 중복키를 보존한 후 출발 관점만 시간대로 합친다. 대전은 실제 유효 Trip의 출발 시각·기점/종점 ID를 사용한다. 역300m 내 대여소가 양쪽에 있어도 OR 조건으로 한 번만 센다.
서울31일 분모4,245,954건/역 인접2,641,440건. 대전11개월 분모7,605,738건/역 인접2,143,709건, 2026-10만923,578건/262,419건. 이 비율은 실제 환승률이 아니다.
정류장 SHA256를 시간집계 메타에 기록하고 버전이 맞지 않으면 예전 비율을 표시하지 않는다. 기존 산출물은 transit_archive에 보관했다. [실행 기록](transit/linkage-integration-20261116.json) · [API 검증](transit/linkage-api-20261116.json).

## 화면·재현
WIZ와 React 대시보드에 정류장/최근접 연계 레이어를 추가했다. 역할 색상은 유지하고 정류장은 회청/네이비, 연계는 점선이다. 지표는 전체 정류장 기반이며 지도는 도시별 최대600개 표본으로 표시 성능을 제한한다.
대여소 분석에는 최근접m·300m 수·500m 버스/철도 수를 표시한다. 세종 대여소 좌표는 미확보라 거리N/A, 버스정류장 레이어만 실제 좌표로 표시한다.

```bash
python -m scripts.preprocess.integrate_transit_uploads --bus data/raw/transit-national-bus-20261109.csv --rail data/raw/transit-national-rail-20260630.xlsx --report docs/transit/transit-integration-20261116.json
python -m scripts.preprocess.build_transit_linkage --seoul-od data/raw/seoul-od-202610.zip --daejeon-trips data/processed/trips --report docs/transit/linkage-integration-20261116.json
```
API GET /api/transit-linkage?city=daejeon&date_start=2026-10-01&date_end=2026-10-31, 기존 스키마·기간 인자 유지.
