"""Acquire the official 2025 BRT stop list; no key or invented stop labels."""
from scripts.collect.common import collect
SOURCE={"source_id":"sejong-brt-15118026","region_id":"sejong","dataset_name":"세종특별자치시 BRT노선별 정류장 현황20250717",
 "source_url":"https://www.data.go.kr/data/15118026/fileData.do","type":"portal_file",
 "uddi":"uddi:9ca52ea8-9c55-4dc1-bfd5-8a89db10068c","public_data_pk":"15118026","filename":"sejong-brt-20250717.csv"}
if __name__=="__main__":print(collect(SOURCE))
