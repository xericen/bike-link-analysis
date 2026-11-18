"""Reproducible common-month trip normalization. Stage first, archive then activate."""
import argparse,csv,hashlib,io,json,math,os,shutil,sqlite3,zipfile
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from openpyxl import load_workbook
from backend.analysis.transit import match_stations
ROOT=Path(__file__).resolve().parents[2];RAW=ROOT/"data/raw";OUT=ROOT/"data/processed"
START="2025-12-01";END="2025-12-31";CITIES=("seoul","daejeon","sejong")
STAGE=OUT/"common_december_staging"
def clean(v):
    v=str(v or "").strip()
    return "" if v.lower() in ("nan","none","null") or v=="\\N" else v
def valid_time(v):
    return datetime.fromisoformat(clean(v))
def point(lat,lon):
    try:
        a,b=float(lat),float(lon)
        if math.isfinite(a) and math.isfinite(b) and 33<=a<=39 and 124<=b<=132:return a,b
    except (ValueError,TypeError):pass
    return None
def write_csv(path,rows,fields):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def member(city):
    p=RAW/{"seoul":"seoul-trips-2025.zip","daejeon":"15137219.zip","sejong":"sejong-details-15106191.zip"}[city]
    z=zipfile.ZipFile(p)
    key={"seoul":"_2512.csv","daejeon":"25년12월","sejong":"2025년 4분기"}[city]
    name=next(n for n in z.namelist() if key in n)
    return p,z,name
def normalize(city):
    path,z,name=member(city);stats=Counter();names={};numbers=defaultdict(set);gps=defaultdict(Counter)
    db=sqlite3.connect(STAGE/(city+".sqlite"));db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; CREATE TABLE events(id TEXT PRIMARY KEY,origin TEXT,dest TEXT,started TEXT,ended TEXT,duration REAL);")
    buffer=[]
    with z.open(name) as f:
      rows=csv.DictReader(io.TextIOWrapper(f,encoding="utf-8-sig" if city=="daejeon" else "cp949"))
      columns=rows.fieldnames
      for r in rows:
        stats["raw_rows"]+=1
        try:
            a=valid_time(r["대여시간" if city=="sejong" else "대여일시"])
            if not START<=a.date().isoformat()<=END:
                stats["outside_departure_period"]+=1;continue
            b=valid_time(r["반납시간" if city=="sejong" else "반납일시"])
            if b<a:raise ValueError("end before start")
            key="주행시간" if city=="sejong" else "이용시간(분)"
            duration=float(r[key]) if clean(r.get(key)) else None
            if duration is not None and (not math.isfinite(duration) or duration<0):raise ValueError("duration")
        except (ValueError,TypeError,KeyError):
            stats["invalid_time_or_duration"]+=1;continue
        if city=="seoul":
            origin,dest=clean(r.get("대여대여소ID")),clean(r.get("반납대여소ID"))
            labels=(clean(r.get("대여 대여소명")),clean(r.get("반납대여소명")))
        elif city=="daejeon":
            origin,dest=clean(r.get("대여_대여소ID")),clean(r.get("반납_대여소ID"))
            labels=(clean(r.get("대여_대여소명")),clean(r.get("반납_대여소명")))
        else:
            origin,dest=clean(r.get("시작 대여소")),clean(r.get("반납 대여소"));labels=("","")
        if not origin or not dest:
            stats["missing_endpoint_id"]+=1;continue
        if city=="daejeon" and any("타슈관제센터" in s for s in labels):
            stats["administrative_return"]+=1;continue
        if city=="sejong":
            eid=clean(r.get("순번"))
            stats["raw_transfer_"+(clean(r.get("환승 유무")) or "EMPTY")]+=1
        else:
            # Full raw-row digest deduplicates exact copies without storing demographics/bike IDs.
            eid=hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if not eid:
            stats["missing_source_id"]+=1;continue
        buffer.append((eid,origin,dest,a.isoformat(),b.isoformat(),duration))
        for idx,sid in enumerate((origin,dest)):
            if labels[idx]:names.setdefault(sid,labels[idx])
            if city=="seoul":
                num=clean(r.get("대여 대여소번호" if idx==0 else "반납대여소번호"))
                if num.isdigit():numbers[sid].add(str(int(num)))
            elif city=="daejeon":
                q=point(r.get(("대여" if idx==0 else "반납")+"_X좌표"),r.get(("대여" if idx==0 else "반납")+"_Y좌표"))
                if q:gps[sid][q]+=1
        if len(buffer)>=20000:
            before=db.total_changes;db.executemany("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)",buffer)
            stats["duplicate_rows"]+=len(buffer)-(db.total_changes-before);buffer.clear();db.commit()
    if buffer:
        before=db.total_changes;db.executemany("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)",buffer)
        stats["duplicate_rows"]+=len(buffer)-(db.total_changes-before)
    db.commit()
    stats["valid_trips"]=db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    days=[r[0] for r in db.execute("SELECT DISTINCT substr(started,1,10) FROM events ORDER BY 1")]
    if len(days)!=31 or days[0]!=START or days[-1]!=END:raise ValueError((city,"incomplete month",days))
    ids={r[0] for r in db.execute("SELECT origin FROM events UNION SELECT dest FROM events")}
    inventory={}
    old={r["station_id"]:r for r in csv.DictReader((OUT/"stations.csv").open()) if r["region_id"]==city}
    if city=="seoul":
        numeric={}
        book=load_workbook(RAW/"seoul-stations-202606.xlsx",read_only=True,data_only=True)
        for row in book.active.iter_rows(min_row=6,values_only=True):
            if row[0] is None:continue
            try:n=str(int(row[0]))
            except (TypeError,ValueError):continue
            numeric[n]={"name":str(row[1]),"point":point(row[4],row[5]),"installed":str(row[6])[:10]}
        book.close()
    if city=="sejong":
        sj={r["대여소 아이디"]:r for r in csv.DictReader((RAW/"sejong-stations-15091421.csv").open(encoding="utf-8-sig"))}
    for sid in sorted(ids):
        q=None;label=names.get(sid) or old.get(sid,{}).get("station_name") or sid
        if city=="seoul":
            ns=numbers[sid]
            item=numeric.get(next(iter(ns))) if len(ns)==1 else None
            if item and item["installed"]<=END:
                q=item["point"];label=names.get(sid) or item["name"];stats["number_master_linked"]+=bool(q)
            if q is None and sid in old and sid.startswith("ST-"):
                # Exact ST ID already verified against official master, never a name/number guess.
                q=point(old[sid].get("latitude"),old[sid].get("longitude"))
                stats["exact_st_master_fallback"]+=bool(q)
            if len(ns)>1:stats["ambiguous_station_number"]+=1
        elif city=="daejeon":
            if gps[sid]:q=sorted(gps[sid].items(),key=lambda x:(-x[1],x[0]))[0][0]
        else:
            item=sj.get(sid)
            if item and item["등록일"][:10]<=END:
                q=point(item["위도"],item["경도"]);label=item["대여소 이름"]
        inventory[sid]={"region_id":city,"station_id":sid,"station_name":label,"latitude":q[0] if q else None,"longitude":q[1] if q else None,"capacity":None}
    stats["station_ids"]=len(ids);stats["located_station_ids"]=sum(s["latitude"] is not None for s in inventory.values())
    stats["returns_after_month"]=db.execute("SELECT COUNT(*) FROM events WHERE substr(ended,1,10)>?",(END,)).fetchone()[0]
    db.close();z.close()
    print(json.dumps({"city":city,**stats}),flush=True)
    return list(inventory.values()),{"city":city,"archive":path.name,"member":name,"columns":columns,"days":days,**stats}
def run():
    if (STAGE/"analysis.sqlite").exists():raise ValueError("Staging already exists; inspect before rebuilding")
    STAGE.mkdir(exist_ok=True);stations=[];reports=[]
    for city in CITIES:
        inventory,report=normalize(city);stations.extend(inventory);reports.append(report)
    c=sqlite3.connect(STAGE/"analysis.sqlite");c.executescript("PRAGMA journal_mode=OFF; CREATE TABLE station_usage(region_id TEXT,station_id TEXT,date TEXT,hour INTEGER,rental_count INTEGER,return_count INTEGER); CREATE TABLE od_daily(region_id TEXT,date TEXT,origin_station_id TEXT,destination_station_id TEXT,trip_count INTEGER);")
    anchor_rows=list(csv.DictReader((OUT/"transit_anchors.csv").open()))
    stop_rows=list(csv.DictReader((OUT/"transit_stops.csv").open()))
    proof={"anchors_sha256":hashlib.sha256((OUT/"transit_anchors.csv").read_bytes()).hexdigest()}
    for city in CITIES:
        c.execute("ATTACH DATABASE ? AS e",(str(STAGE/(city+".sqlite")),))
        c.execute("INSERT INTO od_daily SELECT ?,substr(started,1,10),origin,dest,COUNT(*) FROM e.events GROUP BY 2,3,4",(city,))
        c.execute("""INSERT INTO station_usage SELECT ?,sid,day,h,SUM(r),SUM(b) FROM (
          SELECT origin sid,substr(started,1,10) day,CAST(substr(started,12,2) AS INTEGER) h,COUNT(*) r,0 b FROM e.events GROUP BY 1,2,3
          UNION ALL SELECT dest,substr(ended,1,10),CAST(substr(ended,12,2) AS INTEGER),0,COUNT(*) FROM e.events WHERE substr(ended,1,10)<=? GROUP BY 1,2,3
        ) GROUP BY 2,3,4""",(city,END))
        c.commit()
        group=[s for s in stations if s["region_id"]==city]
        matched=match_stations(group,[r for r in anchor_rows if r["city"]==city])
        near={s["station_id"] for s in matched if s["coordinate_valid"] and s["nearest_stop_distance_m"]<=300}
        known={s["station_id"] for s in matched if s["coordinate_valid"]}
        totals=defaultdict(lambda:[0,0,0])
        for origin,dest,started in c.execute("SELECT origin,dest,started FROM e.events"):
            key=(started[:10],int(started[11:13]));v=totals[key];v[0]+=1;v[1]+=origin in near or dest in near;v[2]+=origin not in known or dest not in known
        rows=[{"date":d,"hour":h,"total_count":v[0],"linked_count":v[1],"unknown_endpoint_count":v[2]} for (d,h),v in sorted(totals.items())]
        fields=["date","hour","total_count","linked_count","unknown_endpoint_count"]
        for filename in [f"anchor_hourly_{city}.csv",f"transit_hourly_{city}.csv",f"transit_hourly_{city}_verified.csv"]:write_csv(STAGE/filename,rows,fields)
        proof[city]={"sha256":hashlib.sha256((STAGE/f"anchor_hourly_{city}.csv").read_bytes()).hexdigest(),"source":"verified December2025 individual trips; either endpoint within anchor300m","period_start":START,"period_end":END}
        c.execute("DETACH DATABASE e")
    c.executescript("CREATE INDEX idx_usage_region_date ON station_usage(region_id,date); CREATE INDEX idx_usage_region_station ON station_usage(region_id,station_id); CREATE INDEX idx_od_region_date ON od_daily(region_id,date); ANALYZE;");c.commit()
    for table in ("station_usage","od_daily"):
        cur=c.execute("SELECT * FROM "+table);fields=[x[0] for x in cur.description]
        write_csv(STAGE/(table+".csv"),(dict(zip(fields,r)) for r in cur),fields)
    c.close()
    write_csv(STAGE/"stations.csv",stations,["region_id","station_id","station_name","latitude","longitude","capacity"])
    (STAGE/"anchor_hourly_sources.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    old_sources=json.loads((OUT/"sources.json").read_text())
    sources=[r for r in old_sources if not any(t in r["source_id"] for t in ["seoul-od","daejeon-trips","sejong-trip"])]
    # Old source definitions remain in archived sources, not in current period provenance.
    for city in CITIES:
        report=next(r for r in reports if r["city"]==city)
        url={"seoul":"https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do","daejeon":"https://www.data.go.kr/data/15137219/fileData.do","sejong":"https://www.data.go.kr/data/15106191/fileData.do"}[city]
        sources.append({"source_id":city+"-trips-202512","region_id":city,"dataset_name":{"seoul":"서울 따릉이","daejeon":"대전 타슈","sejong":"세종 어울링"}[city]+" 개별 대여이력 2025년12월","source_url":url,"date_start":START,"date_end":END,"collected_at":datetime.now(timezone.utc).isoformat(),"verification_status":"VERIFIED","available_columns":report["columns"],"note":"출발일 기준 공통 기간. 월 이후 반납 이벤트는 기간 내 이용 합계에서 제외. 과거 좌표 동일성 미검증."})
    (STAGE/"sources.json").write_text(json.dumps(sources,ensure_ascii=False,indent=2))
    result={"period_start":START,"period_end":END,"cities":reports,"usage_definition":"December departure-cohort rentals; returns restricted to calendar month","coordinates_note":"서울2026-06 master + exact official ST fallback; 대전 selected-trip GPS; 세종2026-05 master. Historical station positions not fully verified."}
    (STAGE/"common_period_validation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    quality=json.loads((OUT/"quality.json").read_text())
    for report in reports:quality[report["city"]]={"common_period":report,"historical_coordinate_limit":True}
    (STAGE/"quality.json").write_text(json.dumps(quality,ensure_ascii=False,indent=2))
    print("Staged common month",flush=True)
def activate():
    report=json.loads((STAGE/"common_period_validation.json").read_text())
    if len(report["cities"])!=3 or any(len(c["days"])!=31 for c in report["cities"]):raise ValueError("Incomplete study")
    backup=OUT/"period_archive"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S");backup.mkdir(parents=True)
    files=[p for p in STAGE.iterdir() if p.name=="analysis.sqlite" or p.suffix in {".csv",".json"}]
    for p in files:
        target=OUT/p.name
        if target.exists():shutil.copy2(target,backup/p.name)
    for p in files:shutil.copy2(p,OUT/(p.name+".incoming"))
    for p in files:os.replace(OUT/(p.name+".incoming"),OUT/p.name)
    (ROOT/"docs/COMMON_PERIOD_202512_validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print("Activated; archive:",backup,flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--activate",action="store_true");a=p.parse_args()
    activate() if a.activate else run()
