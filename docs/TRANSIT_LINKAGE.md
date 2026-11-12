# Phase 1 대중교통 연계 자료·산정 기준

검사일: 2026-11-12. 원본/기존 SQLite/대여소 마스터를 덮어쓰지 않고 별도 확장 파일로 조인한다.

## 공식 출처와 확보 상태
| 도시/수단 | 공식 출처 | 기준일 | 실제 확보 |
|---|---|---|---|
| 서울 버스 | [서울시 버스정류소 위치정보 OA-15067](https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do) | 2026-09-02 | XLSX 11,236행. 한강선착장 8행 제외, 버스 11,228행 |
| 서울 지하철 | [서울교통공사 1~8호선 좌표 OA-22534](https://data.seoul.go.kr/dataList/OA-22534/F/1/datasetView.do) | 2025-08-14 | CP949 CSV 276행, 모두 유효 |
| 대전/세종 버스 | [국토교통부 TAGO 버스정류소정보](https://www.data.go.kr/data/15098534/openapi.do) | 미확보 | DATA_GO_KR_API_KEY 미설정. 실제 수집기 오류 확인 |
| 서울 역사마스터 대안 | [OA-21232](https://data.seoul.go.kr/dataList/OA-21232/S/1/datasetView.do), [T Data](https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1036) | 미확보 | T Data 로그인 요구 확인. 인증 우회 없이 공개 OA-22534 사용 |

버스 파일 실제 컬럼: NODE_ID, ARS_ID, 정류소명, X좌표, Y좌표, 정류소타입. X=경도, Y=위도.
지하철 파일: 연번, 호선, 고유역번호(외부역코드), 역명, 위도, 경도, 작성일자.
호선별 외부 코드를 유지하며 같은 이름 환승역을 임의로 합치지 않는다. 버스 ARS-ID 대신 NODE_ID를 사용한다. 파일별 SHA256·출처·수집 시각은 원본 옆 .source.json에 기록한다. 다운로드 URI와 seq는 실제 공식 페이지에서 확인했다.

## 수집·로컬 fallback
프로젝트 bike-link-analysis 디렉토리에서:
```bash
python -m scripts.collect.collect_transit_stops --city seoul --type 버스
python -m scripts.collect.collect_transit_stops --city seoul --type 지하철
python -m scripts.collect.collect_transit_stops --city daejeon
python -m scripts.collect.collect_transit_stops --city sejong
```
TAGO는 포털 활용신청 승인 후 .env에 DATA_GO_KR_API_KEY(일반 인증키)를 설정한다. 도시코드는 getCtyCodeList 공식 응답으로 확인하고 getSttnNoList를 페이지 단위 호출한다. 인증키 포함 URL/오류는 로그에 출력하지 않는다. 이 API의 실제 성공 호출은 키가 없어 미검증이다.

수동 경로: 위 공식 페이지의 파일 내려받기 또는 전국버스정류소표준데이터 https://www.data.go.kr/data/15096280/standard.do 에서 해당 도시 CSV를 내려받는다. 파일이 없으면 생성하지 않는다. 표준 스키마 city,stop_id,name,type,lat,lon으로 컬럼을 명시적으로 변환하고 출처·기준일 sidecar를 기록한다. 위도/경도 없는 파일은 사용할 수 없다.
```bash
python -m scripts.collect.collect_transit_stops --city daejeon --local /absolute/official.csv --output data/raw/transit-daejeon-official.csv
python -m scripts.preprocess.normalize_transit --input seoul 버스 data/raw/transit-seoul-bus-20260902.xlsx --input seoul 지하철 data/raw/transit-seoul-subway-20250814.csv
python -m scripts.preprocess.build_transit_linkage --seoul-od data/raw/seoul-od-202610.zip
```
대전/세종 파일 확보 후 normalize_transit --input city type file을 함께 지정해 새 --output으로 먼저 검증한다. 기존 산출물이 다르면 덮어쓰기를 거부한다.

## 스키마·수식
- transit_stops.csv: city,stop_id,name,type(지하철|버스),lat,lon. WGS84 한국 범위 검사, ID·좌표 결측 제외, 동일 ID 상충은 실패.
- stations_transit.csv: 기존 대여소 필드 + nearest_stop_distance_m, nearest_bus/subway_distance_m, bus/subway_within_300m/500m, coordinate_valid. 원본 stations.csv 보존.
- 거리는 haversine, 평균 지구 반경 6,371,008.8m. 300/500m 경계 포함. 미확보 수단·위치 미확보 값은 null.
- transit_hourly_seoul_verified.csv: date,hour,total_count,linked_count,unknown_endpoint_count.
- 역 인접 이동 = 출발 또는 도착 중 하나라도 지하철 300m 내 대여소인 실제 이동. 양 끝 모두 인접해도 한 번만 센다.
- 시간대 역 연계 비율 = 해당 시간 linked_count / total_count. 분모에는 미매칭 OD도 포함하고 unknown_endpoint_count를 공개한다.
- 기존 od_daily는 시간을 제거했으므로 서울 월간 원본의 출발시간 관점만 다시 읽는다. 원래 기준_시간대는 5분 단위다. 중복키는 원래 날짜·5분 슬롯·기점·종점이며, 중복 제거 후 시간대로 합친다. 도착시간 관점을 더해 이중 계산하지 않는다.
- 청크 50,000행과 임시 SQLite 기본키를 사용한다. 첫 검산에서 시간 단위 중복키가 정상 5분 기록을 제거하는 문제를 발견해 수정했고, 회귀 테스트와 원래 4,245,954건 합계 검증을 추가했다. 초기 미검증 중간 파일 transit_hourly_seoul.csv는 사용하지 않는다.

## 해석 한계
직선거리이며 실제 보행망·출입구·장애물·환승 여부가 아니다. 지하철은 1~8호선 276행에 한정하므로 전체 수도권/9호선·코레일을 대변하지 않는다. 좌표 기준일과 2026-10 OD 관측일의 시점 차이가 있다. 대전·세종 정류장 미확보는 0개 정류장 또는 접근성 취약 확정을 뜻하지 않는다. 세종 연간값으로 역 연계 비율을 만들지 않는다.

## API
GET /api/transit-linkage?city=seoul&date_start=2026-10-01&date_end=2026-10-31
반환: 거리·수단별 개수·실제 대여/반납량을 조인한 대여소 목록, 시간별 역 인접 이동 비율·미매칭 이동 건수, 기간·출처·한계. 미확보 도시 available=false, 역 연계 비율 null. 잘못된 도시404, 역전 기간400.

## 실제 검증 결과
{"http_status": 200, "seoul_stops": 11504, "station_master_rows": 2762, "subway_300m_stations": 726, "bus_500m_stations": 2753, "period_start": "2026-10-01", "period_end": "2026-10-31", "trip_count": 4245954, "linked_count": 2220479, "linkage_share": 0.5229635083187429, "unknown_endpoint_count": 18535, "last_7days_trip_count": 890565, "sqlite_matched": true, "tests_passed": 28, "compileall": "passed", "react_build": "passed"}

기존 22개를 포함해 28개 테스트 통과. compileall·React 빌드 통과. API의 31일 합계와 기존 SQLite 4,245,954건 일치, 7일 필터 890,565건 일치. 서울 역 인접 이동은 2,220,479건(52.2964%)이며 실제 환승률이 아니다.
