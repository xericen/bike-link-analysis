# 공식 출처 및 데이터 기준 확인 — 2026-11-12

공식 페이지를 이번 작업에서 다시 조회했으며, 대용량 원본을 새로 다운로드하거나 기존 정규화 파일을 덮어쓰지 않았다. 아래 수집일/기간은 보유 파일의 출처 기록이다. 페이지 최신 메타데이터와 보유 파일 기준일을 혼동하지 않는다.

| 지역 | 보유 데이터셋 | 출처 | 수집일 | 보유 기간 | 확보 상태 |
|---|---|---|---|---|---|
| seoul | 서울시 공공자전거 따릉이 대여소 정보 | https://data.seoul.go.kr/dataList/OA-13252/F/1/datasetView.do | 2026-11-04T04:53:59.993091Z | 2026-06-30 ~ 2026-06-30 | VERIFIED |
| seoul | 서울시 공공자전거 따릉이 대여소별 대여/반납 승객수 정보 (2026년 10월) | https://data.seoul.go.kr/dataList/OA-21229/F/1/datasetView.do | 2026-11-09T01:37:07.685993Z | 2026-10-01 ~ 2026-10-31 | VERIFIED |
| daejeon | 대전광역시_공영자전거(타슈) 위치 현황 | https://www.data.go.kr/data/15062798/fileData.do | 2026-11-04T04:48:45.847643Z | 2026-06-24 ~ 2026-06-24 | VERIFIED |
| daejeon | 대전교통공사_대전시 공영자전거 타슈 대여이력 정보 | https://www.data.go.kr/data/15137219/fileData.do | 2026-11-04T05:01:11.341828Z | 2025-12-01 ~ 2026-10-31 | VERIFIED |
| sejong | 세종도시교통공사_공공자전거 어울링 연도별 이용건수 | https://www.data.go.kr/data/15134188/fileData.do | 2026-11-04T04:54:00.764456Z | 2017-01-01 ~ 2026-08-31 | VERIFIED |
| sejong | 세담터 어울링 수집 대여소정보 | https://www2.sejong.go.kr/bigdata/metaDataView.do?order_type=rcd | None | None ~ None | ACCESS_REQUIRED |
| seoul | 서울시 공공자전거 따릉이 이용현황 (OA-21229 대체 예정) | https://data.seoul.go.kr/dataList/OA-14994/F/1/datasetView.do | None | None ~ None | METADATA_ONLY |
| daejeon | 타슈 위치 현황 자동변환 OpenAPI | https://www.data.go.kr/data/15062798/fileData.do | None | None ~ None | ACCESS_REQUIRED |
| sejong | 어울링 연도별 이용건수 자동변환 OpenAPI | https://www.data.go.kr/data/15134188/fileData.do | None | None ~ None | ACCESS_REQUIRED |
| seoul | 서울시 따릉이대여소 마스터 정보 | https://data.seoul.go.kr/dataList/OA-21235/S/1/datasetView.do | 2026-11-09T01:56:36.503651+00:00 | None ~ None | VERIFIED |

## 이번 공식 페이지 확인

- [서울 OA-21229](https://data.seoul.go.kr/dataList/OA-21229/F/1/datasetView.do): 2026년 10월 ZIP 파일 목록(수정일 2026-11-08) 및 11월 일별 파일 제공 상태 확인. 이번 분석에는 이미 보유한 10월만 사용.
- [서울 OA-14994](https://data.seoul.go.kr/dataList/OA-14994/F/1/datasetView.do): 최신 목록은 2026년 1~6월 일별 대여건수 파일, 수정일 2026-07-15. 과거 일부 대여소별 자료도 있지만 현재 사용 중인 시간대별 ST-ID OD의 완전한 대체재로 검증하지 않았다. 기존 보유 파일은 대여일자·대여건수 2열로 기존 전환 제한 유지.
- [대전 타슈 이력 15137219](https://www.data.go.kr/data/15137219/fileData.do): 공식 제공기관 대전교통공사, CSV·연간 갱신·수정일 2026-11-02, 인코딩 EUC-KR/CP949 안내 확인. 실제 분석 기간은 보유 정규화 기록에서 재검산.
- [세종 연간 통계 15134188](https://www.data.go.kr/data/15134188/fileData.do): 연간 통계·2개 컬럼 확인. 공식 설명의 2025-06-30 기준과 기존 보유 출처 메타데이터의 2026-08-31 표기에는 차이가 있어 추가 확인이 필요하다. 2026년은 부분 연도임을 유지하고, 상세 OD가 확보됐다고 간주하지 않는다.
- 서울 마스터는 기존 검증된 OA-21235 보유 자료를 재사용했다. 현시점 마스터 좌표가 각 OD 관측일에도 같았는지에 대한 역사 좌표 검증은 미완료다.

부산은 분석 대상에서 제외하고 기존 조사 코드만 보존한다. 세종 상세 데이터는 여전히 미확보다.

## 보유 대체 파일의 실제 재검사

이번 작업에서 data/raw/seoul-oa14994-2026h1.csv를 다시 읽었다. CP949, 181행, 컬럼은 대여일자·대여건수다. 위 원천 목록의 METADATA_ONLY는 기존 수집 레지스트리에 남은 상태이며, 이 보유 파일의 스키마 확인과 구분한다. 이 파일은 시간·출발지·도착지·ST-ID·좌표가 없어 기존 OD 및 마스터를 대체할 수 없다. 원본과 기존 수집기는 변경하지 않았다.
