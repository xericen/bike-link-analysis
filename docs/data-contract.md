# 공통 데이터 계약

`backend/models/normalized.py`의 Region, Station, Trip, StationUsage, DataSource를 따른다. 선택 필드는 `null`이고, 존재하지 않는 대여소·좌표·이용량·이동량을 생성하지 않는다. 서울 2026 OD 파일은 Trip이 아닌 집계이므로 `od_daily.csv`(`region_id,date,origin_station_id,destination_station_id,trip_count`)로 별도 보관한다.

정규화 파일:

- `stations.csv`: `region_id,station_id,station_name,latitude,longitude,capacity`
- `station_usage.csv`: `region_id,station_id,date,hour,rental_count,return_count`
- `od_daily.csv`: 위 OD 집계 스키마
- `trips/daejeon-YYYYMM.csv`: `region_id,origin_station_id,destination_station_id,started_at,ended_at,duration_minutes`. 대전 유효 Trip을 월별 파티션으로 저장하며 자전거번호·주소 등 원본 부가 필드는 제외한다. 루트 `trips.csv`는 과거 경로 호환용 헤더 파일이다.
- `yearly.csv`: `region_id,year,period_end,complete_year,rental_count`; 세종 연간 집계는 대여소 이용량과 합치지 않는다.
- `sources.json`, `quality.json`: 출처 상태와 지역별 품질·기간
- `analysis.sqlite`: `station_usage`와 `od_daily`의 API 조회용 인덱스 저장소. CSV가 기준 산출물이며 SQLite에는 같은 값을 적재한다.

업로드 API `POST /api/regions/{region_id}/upload`는 `multipart/form-data`의 `file`, `kind`(`stations|station_usage|od_daily|trips`), `dataset_name`을 받는다. 해당 정규화 CSV 컬럼이 필요하며 대여소를 먼저 업로드한다. UTF-8 BOM/UTF-8/CP949를 지원한다. 업로드의 `VERIFIED`는 **파일 스키마 검증**을 뜻하고 공식 출처 검증을 뜻하지 않는다.

비교 시 날짜를 동일하게 필터링하며, 관측일이 다른 결과는 동질 비교로 보지 않는다. 시간대·주말 비중이 없는 지역은 N/A다. 중심성은 OD가 있는 지역에만 존재한다. K-means 유형은 관측된 시간대 비중을 기술하고 출퇴근·여가 목적을 추론하지 않는다.

## 대중교통 연계 확장 계약 (2026-11-12)

- TransitStop: city,stop_id,name,type(지하철|버스),lat,lon. ID는 문자열, 좌표는 WGS84. 동일 city/type/ID의 상충 좌표·이름은 실패로 처리한다.
- stations_transit.csv: 기존 마스터를 보존한 별도 조인. nearest_stop_distance_m, nearest_bus/subway_distance_m, bus/subway_within_300m/500m, coordinate_valid 추가. 없는 수단은 null.
- transit_hourly_seoul_verified.csv: date,hour,total_count,linked_count,unknown_endpoint_count. 원본5분 슬롯 중복 제거 후 시간대 합산, 출발 관점 OR 조건으로 양끝 중복 없음.
- 취약도: max(0,d-500)/500 × 실제 대여량. 500m 초과·실제 수요>0만 후보. 잠재 면적/경험적 백분위 점수·시나리오 가정은 API에 공개한다.
- Spark od_daily·station_usage는 기존 SQLite와 동일 컬럼/정의. od_hourly 및 od_monthly_hourly는 별도 파티션CSV이며 date 또는 month+hour+OD를 키로 한다. 기존 SQLite를 자동교체하지 않는다.

도시별 원본 정의 차이는 유지한다. 지리적 근접을 실제 대중교통 환승으로 보지 않으며, 인구 미확보 값은 생성하지 않는다. [산정·검증](TRANSIT_LINKAGE.md) · [Spark 스키마·동등성](SPARK_TASHU_PIPELINE.md).
