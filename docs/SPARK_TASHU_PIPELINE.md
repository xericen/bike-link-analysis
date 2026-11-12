# Phase 3 PySpark 대전 배치

## 실행 환경
실제 실행 환경: Python 3.14.4, PySpark 4.1.4, OpenJDK 17.0.21. Java 17+와 PySpark는 선택형 배치 의존성이며 FastAPI 실행 경로에서 임포트하지 않는다.
공식 설치 안내: https://spark.apache.org/docs/4.1.0/api/python/getting_started/install.html
CSV 안내: https://spark.apache.org/docs/latest/sql-data-sources-csv.html

## 입력·정규화
--raw-zip data/raw/15137219.zip: 실제 공식 원본 11개 월간 CSV를 임시 UTF-8 파일로 청크 복사한다. 기존 정규화 인코딩 검출 정책(손상 라벨 바이트 치환 명시)을 재사용한다.
전체 원본 필드 기준 중복 제거 후 타슈관제센터 관리 기록, 역전 시각·음수 시간·ID 결측을 제외한다. 실제 기존 정규화 결과와 검산한다. 좌표 이상 기록은 거리 분석 제한이며 Trip 수에서 임의 제외하지 않는다.
--input 'data/processed/trips/*.csv': 이미 정규화한 유효 Trip을 재집계하는 경로. 개별 Trip의 단순 동일 필드만 보고 다시 제거하지 않는다.

## 출력 스키마
Spark CSV 파티션 디렉토리이며 모든 part 파일에 헤더가 있다. 기존 SQLite는 교체하지 않는다.
| 산출물 | 스키마 |
|---|---|
| od_daily | region_id,date,origin_station_id,destination_station_id,trip_count |
| station_usage | region_id,station_id,date,hour,rental_count,return_count |
| od_hourly | region_id,date,hour,origin_station_id,destination_station_id,trip_count |
| od_monthly_hourly | region_id,month,hour,origin_station_id,destination_station_id,trip_count |

출발 날짜/시간으로 OD·대여를 집계하고 반납은 실제 반납 날짜/시간에 집계한다. 자정을 넘은 Trip도 반납일이 다르다. 한국 로컬 시각이며 UTC로 임의 이동하지 않는다. 월별 집계는 출발 월 기준이다. 첫 두 산출물은 기존 SQLite와 컬럼·정의가 같다. 기존 od_daily에는 시간이 없으므로 시간 OD를 동일 기존 테이블이 있다고 주장하지 않고 별도 산출물로 제공한다.

## 재현 명령
프로젝트 bike-link-analysis 디렉토리에서:
```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
python -m pip install -r backend/requirements-spark.txt
python -m scripts.preprocess.spark_tashu --raw-zip data/raw/15137219.zip --output data/processed/spark-tashu-20261112
python -m scripts.validate.spark_tashu --output data/processed/spark-tashu-20261112 --reference data/processed/analysis.sqlite --reference-trips data/processed/trips --report docs/transit/spark-validation.json
python -m pytest backend/tests/test_spark_pipeline.py -q
```
출력·보고서가 있으면 덮어쓰지 않는다. 다시 실행할 때는 새 경로를 지정한다. 기본 local[*], JVM ActiveProcessorCount=4, heap2GB, shuffle32, 64MB 입력 분할, DISK_ONLY 중간 저장을 사용한다. 8GB 컨테이너에서 논리 CPU80개가 불필요한 동시 작업을 만들지 않게 제한했다. 대용량 collect/toPandas를 사용하지 않는다.

## 독립 검증 방식
검증기는 Spark 파티션 CSV를 별도 임시 SQLite에 50,000행씩 읽고 운영 DB는 mode=ro로 연결한다.
- od_daily·station_usage는 모든 컬럼의 EXCEPT 양방향 차집합이 0인지 확인한다. 총량만 같은 경우는 통과시키지 않는다.
- 월/시간 OD는 일/시간 OD를 다시 월로 합친 값과 양방향 비교한다.
- --reference-trips 지정 시 기존 정규화 Trip 760만 행을 Python CSV로 읽어 독립 SQLite 시간대 OD를 계산하고 Spark 시간대 OD와 양방향 비교한다.
- fixture 스모크는 같은 시간의 복수 Trip 합산과 자정 이후 반납일·시각 집계, 기존 산출물 덮어쓰기 거부를 확인한다. fixture는 실제 산출물과 별도 임시 경로에서만 실행한다.

## 현재 검증
스모크 포함 전체 pytest31건 통과. 원본 전체 실행과 일치성 검증 결과는 아래에 실제 완료 후 기록한다.

## 전체 원본 실행·검증 완료
{
  "passed": true,
  "rows": {
    "od_daily": 5350360,
    "station_usage": 4502831,
    "od_hourly": 6855588,
    "od_monthly_hourly": 4164960
  },
  "trip_count": 7605738,
  "date_start": "2025-12-01",
  "date_end": "2026-10-31",
  "checks": {
    "od_daily": {
      "spark_minus_sqlite": 0,
      "sqlite_minus_spark": 0
    },
    "station_usage": {
      "spark_minus_sqlite": 0,
      "sqlite_minus_spark": 0
    },
    "monthly_from_hourly": {
      "left_minus_right": 0,
      "right_minus_left": 0
    },
    "hourly_from_python_sqlite_reference": {
      "spark_minus_reference": 0,
      "reference_minus_spark": 0,
      "reference_trip_rows": 7605738
    }
  },
  "original_database_modified": false
}
원본 8,008,537행, 중복 24,932행, 관리 목적 377,867행 제외, 유효 7,605,738건. 기존 정규화의 원본/제외/유효 건수와 모두 일치했다. 일별 OD·대여/반납·시간대 OD·월별 시간대 OD의 양방향 차집합은 모두 0이다. 단순 총량 일치만 검사한 것이 아니다. 실행 정보는 [spark-run.json](transit/spark-run.json), 비교 결과는 [spark-validation.json](transit/spark-validation.json)에 보관한다.
원본 출처: [대전교통공사 타슈 대여이력](https://www.data.go.kr/data/15137219/fileData.do). 원본 ZIP과 운영 SQLite·React 분석 모듈은 교체하지 않았다.
