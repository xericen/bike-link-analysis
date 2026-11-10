"""Download parameters observed in the official sites on 2026-11-04."""
SEOUL = [
    dict(source_id="seoul-stations-202606", region_id="seoul", dataset_name="서울시 공공자전거 따릉이 대여소 정보",
         source_url="https://data.seoul.go.kr/dataList/OA-13252/F/1/datasetView.do",
         filename="seoul-stations-202606.xlsx", type="seoul_file", inf_id="OA-13252", inf_seq="2", seq="24"),
    dict(source_id="seoul-od-202610", region_id="seoul", dataset_name="서울시 공공자전거 따릉이 대여소별 대여/반납 승객수 정보 (2026년 10월)",
         source_url="https://data.seoul.go.kr/dataList/OA-21229/F/1/datasetView.do",
         filename="seoul-od-202610.zip", type="seoul_file", inf_id="OA-21229", inf_seq="1", seq="2610"),
]
DAEJEON = [dict(source_id="daejeon-stations-20260624", region_id="daejeon",
    dataset_name="대전광역시_공영자전거(타슈) 위치 현황",
    source_url="https://www.data.go.kr/data/15062798/fileData.do",
    filename="15062798.csv", type="portal_file", public_data_pk="15062798",
    uddi="uddi:1b7e5971-a37d-4a80-ad0f-9aa12d1e2b87",
    api_path="/15062798/v1/uddi:1b7e5971-a37d-4a80-ad0f-9aa12d1e2b87",
    api_filename="15062798-api.csv"),
    dict(source_id="daejeon-trips-20261102", region_id="daejeon",
    dataset_name="대전교통공사_대전시 공영자전거 타슈 대여이력 정보",
    source_url="https://www.data.go.kr/data/15137219/fileData.do",
    filename="15137219.zip", type="portal_file", public_data_pk="15137219",
    uddi="uddi:fe731605-e557-4bff-8d8e-a6415631cbd6")]
SEJONG = [dict(source_id="sejong-yearly-20260831", region_id="sejong",
    dataset_name="세종도시교통공사_공공자전거 어울링 연도별 이용건수",
    source_url="https://www.data.go.kr/data/15134188/fileData.do",
    filename="15134188.csv", type="portal_file", public_data_pk="15134188",
    uddi="uddi:9ab74c31-6b18-4a9e-bc53-d60058a015c5",
    api_path="/15134188/v1/uddi:9ab74c31-6b18-4a9e-bc53-d60058a015c5",
    api_filename="15134188-api.csv")]
