"""Public portal download, obeying its CAPTCHA/access checks; optional local fallback."""
import argparse,json,zipfile
from scripts.collect.common import collect
SOURCE={"source_id":"sejong-trip-15106191","region_id":"sejong","dataset_name":"세종도시교통공사 공공자전거 어울링 이용현황 2020~2025",
 "source_url":"https://www.data.go.kr/data/15106191/fileData.do","type":"portal_file",
 "filename":"sejong-details-15106191.zip","uddi":"uddi:cf9de430-656e-4560-b189-9d5ed4ecd01f","public_data_pk":"15106191"}
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--local");a=p.parse_args()
 path=collect(SOURCE,a.local)
 print(path)
 with zipfile.ZipFile(path) as z:
  print(json.dumps([{"name":x.filename,"bytes":x.file_size} for x in z.infolist()],ensure_ascii=False))
