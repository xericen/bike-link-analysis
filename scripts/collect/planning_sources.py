"""Collect verified planning inputs. No secret keys and no invented spatial population."""
import csv,hashlib,json,requests,io
from pathlib import Path
from datetime import datetime,timezone
from scripts.collect.common import collect
ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/"data/raw"; OUT=ROOT/"data/processed"
CITIES={"seoul":"서울특별시","daejeon":"대전광역시","sejong":"세종특별자치시"}

def download(url,name):
    target=RAW/name
    if not target.exists():
        response=requests.get(url,timeout=45);response.raise_for_status()
        target.write_bytes(response.content)
    return target

def standard(pk):
    path=RAW/f"facilities-{pk}.json"
    if path.exists():return json.loads(path.read_text())
    header=requests.get("https://www.data.go.kr/download/columList.json",params={"pk":pk,"ext":"CSV"},timeout=25).json()
    result=[]
    for page in range(1,(int(header["totalCount"])+9999)//10000+1):
        params={"publicDataPk":pk,"colNmList":header["tableVO"]["colNmList"],"svcTableNm":header["tableVO"]["svcTableNm"],
                "totalCount":header["totalCount"],"perPage":10000,"page":page}
        response=requests.get("https://www.data.go.kr/download/standard.json",params=params,timeout=45);response.raise_for_status()
        result.extend(response.json())
    if len(result)!=int(header["totalCount"]):raise RuntimeError("Incomplete standard dataset")
    names={c["columCode"]:c["columNm"] for c in header["columList"]}
    result=[{names.get(k,k):v for k,v in row.items()} for row in result]
    path.write_text(json.dumps(result,ensure_ascii=False))
    return result

def run():
    RAW.mkdir(parents=True,exist_ok=True)
    provenance=[]
    population=collect({"filename":"population-20261031.csv","source_id":"mois-population-202610","region_id":"all",
        "dataset_name":"행정안전부 행정동 주민등록 인구수","source_url":"https://www.data.go.kr/data/15097972/fileData.do",
        "uddi":"uddi:9301bbc2-e817-4db8-ac2d-dc4b5148dc07","public_data_pk":"15097972","type":"portal_file"})
    poptext=population.read_bytes()
    try: text=poptext.decode("utf-8-sig")
    except UnicodeDecodeError: text=poptext.decode("cp949")
    pop=list(csv.DictReader(io.StringIO(text)))
    selected=[r for r in pop if r["시도명"] in CITIES.values()]
    # Keep administrative population only; never distribute it as measured grid population.
    (OUT/"planning_population.json").write_text(json.dumps(selected,ensure_ascii=False))
    provenance.append({"kind":"population","url":"https://www.data.go.kr/data/15097972/fileData.do","period":"2026-10","sha256":hashlib.sha256(poptext).hexdigest()})
    facility_sources=[(pk,standard(pk)) for pk in ("15013109","15013117")]
    for city,name in CITIES.items():
        url=f"https://raw.githubusercontent.com/statgarten/maps/main/json/{name}_시군구_경계.json"
        path=download(url,f"boundary-{city}-sgis2020.json")
        (OUT/f"planning_boundary_{city}.json").write_bytes(path.read_bytes())
        provenance.append({"kind":"boundary","city":city,"url":url,"year":2020,"crs":"EPSG:5179","sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"upstream":"SGIS 2020 via statgarten/maps MIT"})
        features=[]
        for pk,rows in facility_sources:
            for i,row in enumerate(rows):
                if row.get("시도명")!=name and not str(row.get("소재지도로명주소","")).startswith(name):continue
                try:lat,lon=float(row["위도"]),float(row["경도"])
                except (ValueError,TypeError,KeyError):continue
                if not (33<lat<39 and 124<lon<132):continue
                features.append({"id":pk+"-"+str(i),"lat":lat,"lon":lon,
                    "type":"도서관" if pk=="15013109" else "공공개방시설","name":row.get("도서관명") or row.get("개방시설명","")})
        (OUT/f"planning_facilities_{city}.json").write_text(json.dumps(features,ensure_ascii=False))
        for pk,rows in facility_sources:
            path=RAW/f"facilities-{pk}.json"
            provenance.append({"kind":"facilities","city":city,"url":f"https://www.data.go.kr/data/{pk}/standard.do",
                "count":sum(f["id"].startswith(pk) for f in features),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                "scope":"도서관·공공개방시설 공개 좌표, 전체 생활시설 전수 자료 아님"})
    master=collect({"filename":"sejong-stations-15091421.csv","source_id":"sejong-stations-20260526","region_id":"sejong",
        "dataset_name":"세종도시교통공사 어울링 대여소현황","source_url":"https://www.data.go.kr/data/15091421/fileData.do",
        "uddi":"uddi:d49e0a94-016b-486e-8df9-b4fe818e8eba","public_data_pk":"15091421","type":"portal_file"})
    records=list(csv.DictReader(master.open(encoding="utf-8-sig")))
    lookup={r["대여소 아이디"]:r for r in records}
    stationpath=OUT/"stations.csv"
    backup=RAW/"stations-before-planning.csv"
    if not backup.exists():backup.write_bytes(stationpath.read_bytes())
    rows=list(csv.DictReader(stationpath.open(encoding="utf-8-sig")));matched=0
    for row in rows:
        if row["region_id"]!="sejong":continue
        item=lookup.get(row["station_id"])
        # Only IDs registered by the observed month are eligible; retain unmatched records.
        if item and item["등록일"][:10]<="2025-10-31":
            row.update(station_name=item["대여소 이름"],latitude=item["위도"],longitude=item["경도"]);matched+=1
    with stationpath.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    source={"source_id":"sejong-master-15091421","region_id":"sejong","dataset_name":"세종 어울링 대여소 위치 마스터","source_url":"https://www.data.go.kr/data/15091421/fileData.do","date_start":"2026-05-26","date_end":"2026-05-26","collected_at":datetime.now(timezone.utc).isoformat(),"verification_status":"VERIFIED","available_columns":list(records[0]),"note":"2025-10 등록 이내 ID만 연결. 좌표는2026-05 기준으로 과거 위치 변경 가능성이 있음."}
    sources=json.loads((OUT/"sources.json").read_text())
    previous=next((s for s in sources if s["source_id"]==source["source_id"]),None)
    if previous:source["collected_at"]=previous["collected_at"]
    sources=[s for s in sources if s["source_id"]!=source["source_id"]]+[source]
    (OUT/"sources.json").write_text(json.dumps(sources,ensure_ascii=False,indent=2))
    provenance.append({"kind":"sejong_master","url":source["source_url"],"matched_ids":matched,"master_rows":len(records),"sha256":hashlib.sha256(master.read_bytes()).hexdigest(),"coordinate_as_of":"2026-05-26","historical_location_verified":False})
    (OUT/"planning_sources.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2))
    print(json.dumps(provenance,ensure_ascii=False))
if __name__=="__main__":run()
