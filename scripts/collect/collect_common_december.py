"""Download the official Seoul annual archive for the common December 2025 study."""
from scripts.collect.common import collect,setup_logging
SOURCE={"source_id":"seoul-trips-2025","region_id":"seoul","dataset_name":"서울시 공공자전거 따릉이 대여이력 정보 2025",
"source_url":"https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do","filename":"seoul-trips-2025.zip",
"type":"seoul_file","inf_id":"OA-15182","inf_seq":"1","seq":"96"}
if __name__=="__main__":
    setup_logging()
    print(collect(SOURCE),flush=True)
