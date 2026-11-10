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
