"""Resumable per-member OD/hourly normalization. Original common DB is read-only."""
import argparse,csv,hashlib,json,os,shutil,sqlite3,zipfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scripts.preprocess.build_monthly_trends import source_members,sha
from backend.analysis.transit import match_stations
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"data/processed"
WORK=ROOT/"data/individual_build"
TARGET=ROOT/"data/individual"
URLS={"seoul":"https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do","daejeon":"https://www.data.go.kr/data/15137219/fileData.do","sejong":"https://www.data.go.kr/data/15106191/fileData.do"}

def collect(task):
    city,path_text,name,near_list,known_list,start,end=task
    path=Path(path_text)
    with zipfile.ZipFile(path) as z:
        token=json.dumps([sha(Path(__file__)),city,path.stat().st_size,z.getinfo(name).CRC,name,near_list,known_list,start,end])
        key=hashlib.sha256(token.encode()).hexdigest()
        folder=WORK/"pieces"/city;folder.mkdir(parents=True,exist_ok=True)
        dbpath=folder/(key+".sqlite");receipt=folder/(key+".json")
        if receipt.exists() and dbpath.exists():
            return {"db":str(dbpath),**json.loads(receipt.read_text())}
        temp=dbpath.with_suffix("."+str(os.getpid())+".tmp")
        c=sqlite3.connect(temp)
        c.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; CREATE TABLE usage(sid TEXT,date TEXT,h INTEGER,r INTEGER,b INTEGER); CREATE TABLE od(date TEXT,a TEXT,b TEXT,n INTEGER); CREATE TABLE hours(date TEXT,h INTEGER,n INTEGER,linked INTEGER,unknown_n INTEGER);")
        with z.open(name) as probe:header=probe.readline()
        try:header.decode("utf-8-sig");encoding="utf-8-sig"
        except UnicodeDecodeError:encoding="cp949"
        stats=Counter();seen={};labels={};near=set(near_list);known=set(known_list)
        print("process",city,name,flush=True)
        with z.open(name) as stream:
            for frame in pd.read_csv(stream,encoding=encoding,dtype=str,chunksize=150000,keep_default_na=False):
                stats["raw_rows"]+=len(frame)
                frame=frame.fillna("").astype(str).apply(lambda col:col.str.strip())
                sc,ec=("대여시간","반납시간") if city=="sejong" else ("대여일시","반납일시")
                a=pd.to_datetime(frame[sc],errors="coerce",format="mixed")
                b=pd.to_datetime(frame[ec],errors="coerce",format="mixed")
                dur=pd.to_numeric(frame["주행시간" if city=="sejong" else "이용시간(분)"],errors="coerce")
                oc,dc={"seoul":("대여대여소ID","반납대여소ID"),"daejeon":("대여_대여소ID","반납_대여소ID"),"sejong":("시작 대여소","반납 대여소")}[city]
                origin,dest=frame[oc],frame[dc]
                good=a.notna()&b.notna()&(b>=a)&(dur.isna()|((dur>=0)&np.isfinite(dur)))&origin.ne("")&dest.ne("")&~origin.isin(["nan","None","null","\\N"])&~dest.isin(["nan","None","null","\\N"])
                days=a.dt.strftime("%Y-%m-%d")
                good&=days.ge(start)&days.le(end)
                if city=="daejeon":
                    good&=~(frame["대여_대여소명"].str.contains("타슈관제센터")|frame["반납_대여소명"].str.contains("타슈관제센터"))
                if city=="sejong":good&=frame["순번"].ne("")
                raw_valid=np.flatnonzero(good.to_numpy());stats["excluded_rows"]+=len(frame)-len(raw_valid)
                if city=="sejong":keys=frame["순번"].to_numpy()
                else:
                    h1=pd.util.hash_pandas_object(frame,index=False).to_numpy()
                    h2=pd.util.hash_pandas_object(frame.iloc[:,::-1],index=False,hash_key="monthly-trend-v1").to_numpy()
                    keys=list(zip(h1.tolist(),h2.tolist()))
                months=a.dt.strftime("%Y-%m").to_numpy()
                keep=[]
                for i in raw_valid:
                    bucket=seen.setdefault(months[i],set())
                    if keys[i] in bucket:stats["duplicate_rows"]+=1;continue
                    bucket.add(keys[i]);keep.append(i)
                if not keep:continue
                f=frame.iloc[keep];started=a.iloc[keep];ended=b.iloc[keep]
                od=pd.DataFrame({"date":started.dt.strftime("%Y-%m-%d").to_numpy(),"a":f[oc].to_numpy(),"b":f[dc].to_numpy()})
                group=od.groupby(["date","a","b"],sort=False).size()
                c.executemany("INSERT INTO od VALUES(?,?,?,?)",((d,o,t,int(n)) for (d,o,t),n in group.items()))
                for side,times,column in [("r",started,oc),("b",ended,dc)]:
                    t=pd.DataFrame({"sid":f[column].to_numpy(),"date":times.dt.strftime("%Y-%m-%d").to_numpy(),"h":times.dt.hour.to_numpy()})
                    t=t[t.date.between(start,end)]
                    agg=t.groupby(["sid","date","h"],sort=False).size()
                    c.executemany("INSERT INTO usage VALUES(?,?,?,?,?)",((sid,d,int(h),int(n) if side=="r" else 0,int(n) if side=="b" else 0) for (sid,d,h),n in agg.items()))
                hourly=pd.DataFrame({"date":started.dt.strftime("%Y-%m-%d").to_numpy(),"h":started.dt.hour.to_numpy(),
                    "linked":(f[oc].isin(near)|f[dc].isin(near)).to_numpy().astype(int),
                    "unknown_n":(~f[oc].isin(known)|~f[dc].isin(known)).to_numpy().astype(int)})
                h=hourly.groupby(["date","h"],sort=False).agg(n=("linked","size"),linked=("linked","sum"),unknown_n=("unknown_n","sum")).reset_index()
                c.executemany("INSERT INTO hours VALUES(?,?,?,?,?)",((d,int(hr),int(n),int(l),int(u)) for d,hr,n,l,u in h.itertuples(index=False,name=None)))
                for col,label_col in [(oc,"대여 대여소명" if city=="seoul" else "대여_대여소명"),(dc,"반납대여소명" if city=="seoul" else "반납_대여소명")]:
                    if label_col in f:
                        for sid,label in f[[col,label_col]].drop_duplicates(col).itertuples(index=False,name=None):labels.setdefault(sid,label)
                stats["valid_trips"]+=len(keep);c.commit()
        c.execute("CREATE TABLE station_names(sid TEXT,name TEXT)")
        c.executemany("INSERT INTO station_names VALUES(?,?)",labels.items());c.commit()
        valid=c.execute("SELECT SUM(n) FROM od").fetchone()[0] or 0
        assert valid==stats["valid_trips"]
        c.close();os.replace(temp,dbpath)
        value={"city":city,"archive":path.name,"member":name,"encoding":encoding,"stats":dict(stats)}
        receipt.write_text(json.dumps(value,ensure_ascii=False))
        print("saved",city,name,valid,flush=True)
        return {"db":str(dbpath),**value}

def merge(city,pieces):
    folder=TARGET/city;folder.mkdir(parents=True,exist_ok=True)
    if (folder/"normalization.json").exists():
        print("already merged",city,flush=True);return
    # Copy only reference files; never copy or overwrite the common analysis/cache databases.
    excluded={"stations.csv","sources.json","quality.json","station_usage.csv","od_daily.csv","anchor_hourly_sources.json","kpi_inputs.json","kpi_verified.json"}
    for p in BASE.iterdir():
        if p.is_file() and p.suffix in {".csv",".json"} and p.name not in excluded and not p.name.startswith(("anchor_hourly_","transit_hourly_")):
            shutil.copy2(p,folder/p.name)
    c=sqlite3.connect(folder/"analysis.building.sqlite")
    c.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY; PRAGMA cache_size=-262144; CREATE TABLE usage_raw(sid TEXT,date TEXT,h INTEGER,r INTEGER,b INTEGER); CREATE TABLE od_raw(date TEXT,a TEXT,b TEXT,n INTEGER); CREATE TABLE hours_raw(date TEXT,h INTEGER,n INTEGER,linked INTEGER,unknown_n INTEGER); CREATE TABLE names_raw(sid TEXT,name TEXT);")
    for piece in pieces:
        c.execute("ATTACH DATABASE ? AS p",(piece["db"],))
        for target,table in [("usage_raw","usage"),("od_raw","od"),("hours_raw","hours"),("names_raw","station_names")]:
            c.execute("INSERT INTO "+target+" SELECT * FROM p."+table)
        c.commit();c.execute("DETACH DATABASE p")
    print("grouping",city,flush=True)
    c.execute("CREATE TABLE station_usage AS SELECT ? region_id,sid station_id,date,h hour,SUM(r) rental_count,SUM(b) return_count FROM usage_raw GROUP BY sid,date,h",(city,))
    c.execute("CREATE TABLE od_daily AS SELECT ? region_id,date,a origin_station_id,b destination_station_id,SUM(n) trip_count FROM od_raw GROUP BY date,a,b",(city,))
    c.execute("CREATE TABLE anchor_hours AS SELECT date,h hour,SUM(n) total_count,SUM(linked) linked_count,SUM(unknown_n) unknown_endpoint_count FROM hours_raw GROUP BY date,h")
    actual=dict(c.execute("SELECT substr(date,1,7),SUM(rental_count) FROM station_usage GROUP BY 1"))
    ref=json.loads((ROOT/"data/reference/monthly_trends"/(city+".json")).read_text())
    expected={m["month"]:m["rental_count"] for m in ref["months"]}
    assert actual==expected,(city,"monthly rental regression",actual,expected)
    assert sum(actual.values())==c.execute("SELECT SUM(trip_count) FROM od_daily").fetchone()[0]
    dates=[r[0] for r in c.execute("SELECT DISTINCT date FROM station_usage WHERE rental_count>0 ORDER BY date")]
    master=list(csv.DictReader((BASE/"stations.csv").open()))
    existing={r["station_id"]:r for r in master if r["region_id"]==city}
    names=dict(c.execute("SELECT sid,MAX(name) FROM names_raw GROUP BY sid"))
    for sid, in c.execute("SELECT DISTINCT station_id FROM station_usage"):
        existing.setdefault(sid,{"region_id":city,"station_id":sid,"station_name":names.get(sid) or sid,"latitude":"","longitude":"","capacity":""})
    with (folder/"stations.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["region_id","station_id","station_name","latitude","longitude","capacity"]);w.writeheader();w.writerows(existing.values())
    rows=c.execute("SELECT * FROM anchor_hours ORDER BY date,hour").fetchall()
    columns=["date","hour","total_count","linked_count","unknown_endpoint_count"]
    for filename in (f"anchor_hourly_{city}.csv",f"transit_hourly_{city}.csv",f"transit_hourly_{city}_verified.csv"):
        with (folder/filename).open("w",newline="") as f:w=csv.writer(f);w.writerow(columns);w.writerows(rows)
    proof={"anchors_sha256":sha(folder/"transit_anchors.csv"),city:{"sha256":sha(folder/f"anchor_hourly_{city}.csv"),"source":"verified individual full-period trips; fixed reference anchors; OR rule","period_start":dates[0],"period_end":dates[-1]}}
    (folder/"anchor_hourly_sources.json").write_text(json.dumps(proof))
    (folder/f"transit_hourly_{city}_verified.meta.json").write_text(json.dumps({"stops_sha256":sha(folder/"transit_stops.csv")}))
    c.executescript("CREATE INDEX idx_usage_date ON station_usage(region_id,date); CREATE INDEX idx_usage_station ON station_usage(region_id,station_id,date,hour); CREATE INDEX idx_od_date ON od_daily(region_id,date); DROP TABLE usage_raw; DROP TABLE od_raw; DROP TABLE hours_raw; DROP TABLE names_raw; ANALYZE;")
    c.commit();c.close();os.replace(folder/"analysis.building.sqlite",folder/"analysis.sqlite")
    source={"source_id":city+"-individual-full","region_id":city,"dataset_name":city+" 개별 이용이력 "+dates[0]+"~"+dates[-1],"source_url":URLS[city],"date_start":dates[0],"date_end":dates[-1],"collected_at":datetime.now(timezone.utc).isoformat(),"verification_status":"VERIFIED","note":"출발 코호트 기준. 고정 위치/시설/앵커 참조 자료의 과거 동일성 미검증. 원본 지문 중복 제외. 재고 수량 미추정."}
    (folder/"sources.json").write_text(json.dumps([source],ensure_ascii=False))
    result={"city":city,"start":dates[0],"end":dates[-1],"valid_trips":sum(actual.values()),"observed_days":len(dates),"monthly":actual,"member_count":len(pieces),"station_ids":len(existing),"located_ids":sum(bool(r["latitude"]) for r in existing.values()),"pieces":pieces,"original_monthly_matches":True}
    (folder/"quality.json").write_text(json.dumps({city:result},ensure_ascii=False))
    (folder/"normalization.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print("MERGED",city,sum(actual.values()),flush=True)

def run(workers):
    master=pd.read_csv(BASE/"stations.csv").replace({np.nan:None})
    anchors=pd.read_csv(BASE/"transit_anchors.csv")
    tasks=[]
    for city in ("seoul","daejeon","sejong"):
        linked=match_stations(master[master.region_id==city].to_dict("records"),anchors[anchors.city==city].to_dict("records"))
        known=sorted(s["station_id"] for s in linked if s["coordinate_valid"])
        near=sorted(s["station_id"] for s in linked if s["coordinate_valid"] and s["nearest_stop_distance_m"] is not None and s["nearest_stop_distance_m"]<=300)
        ref=json.loads((ROOT/"data/reference/monthly_trends"/(city+".json")).read_text())
        for path,name in source_members(city):tasks.append((city,str(path),name,near,known,ref["period_start"],ref["period_end"]))
    grouped={city:[] for city in ("seoul","daejeon","sejong")}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for value in pool.map(collect,tasks):grouped[value["city"]].append(value)
    for city,items in grouped.items():merge(city,items)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--workers",type=int,default=4);a=p.parse_args();run(a.workers)
