"""Normalize an explicitly selected period of real Sejong trips; source IDs are never guessed."""
import argparse,csv,io,json,sqlite3,zipfile,shutil
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from backend.services import real_data
from scripts.preprocess.integrate_transit_uploads import replace_versioned
from scripts.preprocess.normalize import detect_encoding

def normalize_member(archive,name,start,end):
    with archive.open(name) as f: sample=f.read(65536)
    enc=detect_encoding(sample)
    stats=Counter();items=[]
    with archive.open(name) as f:
      for chunk in pd.read_csv(f,dtype=str,encoding=enc,chunksize=50000):
        stats["member_raw_rows"]+=len(chunk)
        for r in chunk.to_dict("records"):
            try:a=datetime.fromisoformat(str(r["대여시간"]))
            except (ValueError,KeyError):stats["invalid_started_at"]+=1;continue
            if not start<=a.date().isoformat()<=end:continue
            stats["selected_raw_rows"]+=1
            try:
                b=datetime.fromisoformat(str(r["반납시간"]))
                origin,dest=str(r["시작 대여소"]).strip(),str(r["반납 대여소"]).strip()
                if origin in {"","nan"} or dest in {"","nan"}:raise ValueError()
                if b<a:raise ValueError()
                duration=float(r["주행시간"]) if pd.notna(r.get("주행시간")) else None
                if duration is not None and duration<0:raise ValueError()
            except (ValueError,TypeError,KeyError):
                stats["invalid_trip_rows"]+=1;continue
            # Keep original SJ_ / SJ- identifiers distinct; no undocumented crosswalk.
            items.append((str(r["순번"]),origin,dest,a.isoformat(),b.isoformat(),duration))
    return items,stats,enc
def integrate(zip_path,start,end,report):
    out=real_data.PROCESSED;archive_dir=out/"sejong_archive";archive_dir.mkdir(exist_ok=True)
    with sqlite3.connect(real_data.database_path()) as c:
        if c.execute("SELECT 1 FROM od_daily WHERE region_id='sejong' LIMIT 1").fetchone():
            raise ValueError("기존 세종 상세 자료를 덮어쓰지 않습니다. 새 스테이징 DB로 검증하세요.")
    aggregate=out/"sejong_staging.sqlite"
    if aggregate.exists():raise ValueError("기존 스테이징 보존: 경로 확인 필요")
    db=sqlite3.connect(aggregate);db.execute("CREATE TABLE events(id TEXT PRIMARY KEY,origin TEXT,dest TEXT,started TEXT,ended TEXT,duration REAL)")
    stats=Counter();files=[]
    with zipfile.ZipFile(zip_path) as archive:
      for name in archive.namelist():
        # File names are explicit quarter metadata; never infer observation records.
        year=int(start[:4]);quarter=(int(start[5:7])-1)//3+1
        if f"{year}년 {quarter}분기" not in name:continue
        items,counts,enc=normalize_member(archive,name,start,end);stats.update(counts)
        before=db.total_changes
        db.executemany("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?)",items)
        stats["duplicate_source_ids"]+=len(items)-(db.total_changes-before)
        files.append({"name":name,"encoding":enc,**counts})
    db.commit();stats["valid_trip_rows"]=db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    if not stats["valid_trip_rows"]:raise ValueError("선택 기간 유효 Trip 없음")
    ids={x[0] for x in db.execute("SELECT origin FROM events UNION SELECT dest FROM events")}
    temp=out/"analysis.sejong.incoming.sqlite"
    with sqlite3.connect(real_data.database_path()) as source,sqlite3.connect(temp) as target:
        source.backup(target)
    db.close()
    with sqlite3.connect(temp) as target:
        target.execute("ATTACH DATABASE ? AS sg",(str(aggregate),))
        target.execute("""INSERT INTO od_daily SELECT 'sejong',substr(started,1,10),origin,dest,COUNT(*)
            FROM sg.events GROUP BY 2,3,4""")
        target.execute("""INSERT INTO station_usage
          SELECT 'sejong',id,day,hour,SUM(rentals),SUM(returns) FROM (
            SELECT origin id,substr(started,1,10) day,CAST(substr(started,12,2) AS INTEGER) hour,COUNT(*) rentals,0 returns
              FROM sg.events GROUP BY 1,2,3
            UNION ALL SELECT dest,substr(ended,1,10),CAST(substr(ended,12,2) AS INTEGER),0,COUNT(*)
              FROM sg.events GROUP BY 1,2,3) GROUP BY 2,3,4""")
        target.commit()
        stats["od_rows"]=target.execute("SELECT COUNT(*) FROM od_daily WHERE region_id='sejong'").fetchone()[0]
    original=archive_dir/"analysis-before-sejong.sqlite"
    if not original.exists():shutil.copy2(real_data.database_path(),original)
    temp.replace(real_data.database_path())
    master=real_data.read_csv("stations.csv");fields=["region_id","station_id","station_name","latitude","longitude","capacity"]
    master.extend({"region_id":"sejong","station_id":sid,"station_name":None,"latitude":None,"longitude":None,"capacity":None} for sid in sorted(ids))
    buf=io.StringIO(newline="");w=csv.DictWriter(buf,fieldnames=fields);w.writeheader();w.writerows(master)
    replace_versioned(out/"stations.csv",buf.getvalue(),archive_dir)
    sources=real_data.read_json("sources.json",[])
    sources.append({"source_id":"sejong-trip-15106191","region_id":"sejong","dataset_name":"세종 어울링 개별 이용이력(선택 기간)",
      "source_url":"https://www.data.go.kr/data/15106191/fileData.do","date_start":start,"date_end":end,
      "collected_at":datetime.now(timezone.utc).isoformat(),"verification_status":"VERIFIED",
      "available_columns":["순번","시작 대여소","대여시간","반납 대여소","반납시간","주행시간"],
      "note":"원본 ZIP2020~2025 확보. 최초 서비스 연결은 명시한 기간만. 좌표/명칭 대응표 미확보."})
    replace_versioned(out/"sources.json",json.dumps(sources,ensure_ascii=False,indent=2),archive_dir)
    result={"source_url":sources[-1]["source_url"],"period_start":start,"period_end":end,"files":files,
       **stats,"station_ids":len(ids),"station_coordinates_available":False,
       "limitations":["정류장 원본의 SJ ID와 어울링 대여소 좌표 대응표 미확보. 지도와 거리 지표는 N/A.",
       "환승 유무 필드의 공식 산정 정의 미검증: 실제 환승률로 사용하지 않음.",
       "서울·대전2026-10과 세종2025-10을 동일 기간으로 합산하지 않음."]}
    Path(report).parent.mkdir(parents=True,exist_ok=True);Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--zip",required=True);p.add_argument("--start",required=True);p.add_argument("--end",required=True);p.add_argument("--report",required=True);a=p.parse_args()
 if a.start[:4]!=a.end[:4] or (int(a.start[5:7])-1)//3!=(int(a.end[5:7])-1)//3:raise ValueError("한 분기 안의 명시 기간만 선택하세요.")
 print(json.dumps(integrate(a.zip,a.start,a.end,a.report),ensure_ascii=False))
