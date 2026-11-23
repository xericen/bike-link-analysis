"""Offline monthly evidence. Writes a separate reference artifact; never activates a DB."""
import argparse, calendar, hashlib, io, json, re, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from backend.analysis.transit import match_stations
from backend.analysis.vulnerability import spatial_scenario, rank_candidates
from backend.services.planning import boundary
from shapely import to_wkb

ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/"data/raw"
OUT=ROOT/"data/reference/monthly_trends"
URLS={"seoul":"https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do","daejeon":"https://www.data.go.kr/data/15137219/fileData.do","sejong":"https://www.data.go.kr/data/15106191/fileData.do"}

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(4*1024*1024),b""):h.update(block)
    return h.hexdigest()

def source_members(city):
    paths={"seoul":["seoul-trips-2025.zip"],"daejeon":["15137219.zip","daejeon-history-20260331.zip"],"sejong":["sejong-details-15106191.zip"]}[city]
    selected={}
    for filename in paths:
        path=RAW/filename
        if not path.exists():continue
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.endswith(".csv"):continue
                if city=="daejeon":
                    m=re.search(r"(\d{2})년(\d{2})월",name)
                    key="-".join(m.groups()) if m else name
                else:key=name
                # Latest local archive wins overlaps; archives are never concatenated blindly.
                selected.setdefault(key,(path,name))
    return list(selected.values())

def prepare(city):
    master=pd.read_csv(ROOT/"data/processed/stations.csv").replace({np.nan:None})
    stations=master[master.region_id==city].to_dict("records")
    anchors=pd.read_csv(ROOT/"data/processed/transit_anchors.csv")
    selected=anchors[anchors.city==city].to_dict("records")
    linked=match_stations(stations,selected)
    located=[s for s in linked if s["coordinate_valid"] and s["nearest_stop_distance_m"] is not None]
    points=tuple(sorted(set((float(s["lat"]),float(s["lon"])) for s in selected)))
    inventory=tuple(sorted((s["station_id"],float(s["latitude"]),float(s["longitude"]),s["nearest_stop_distance_m"]) for s in located))
    clip=boundary(city)
    _,areas=spatial_scenario(points,inventory,to_wkb(clip) if clip is not None else None)
    return {s["station_id"]:s for s in located},areas

def accumulate(frame,city,months,seen,near=None,known=None):
    near=near or set();known=known or set()
    raw=len(frame)
    # All columns participate in two independent row fingerprints. Source IDs for Sejong.
    frame=frame.fillna("").astype(str).apply(lambda col:col.str.strip())
    start_col,end_col=("대여시간","반납시간") if city=="sejong" else ("대여일시","반납일시")
    starts=pd.to_datetime(frame[start_col],errors="coerce",format="mixed")
    ends=pd.to_datetime(frame[end_col],errors="coerce",format="mixed")
    duration=pd.to_numeric(frame["주행시간" if city=="sejong" else "이용시간(분)"],errors="coerce")
    origin_col,dest_col={"seoul":("대여대여소ID","반납대여소ID"),"daejeon":("대여_대여소ID","반납_대여소ID"),"sejong":("시작 대여소","반납 대여소")}[city]
    origin,dest=frame[origin_col],frame[dest_col]
    valid=starts.notna()&ends.notna()&(ends>=starts)&(duration.isna()|((duration>=0)&np.isfinite(duration)))&origin.ne("")&dest.ne("")&~origin.isin(["nan","None","null","\\N"])&~dest.isin(["nan","None","null","\\N"])
    if city=="daejeon":valid&=~(frame["대여_대여소명"].str.contains("타슈관제센터")|frame["반납_대여소명"].str.contains("타슈관제센터"))
    if city=="sejong":valid&=frame["순번"].ne("")
    months_key=starts.dt.strftime("%Y-%m")
    fingerprints=None
    if city!="sejong":
        a=pd.util.hash_pandas_object(frame,index=False).to_numpy()
        b=pd.util.hash_pandas_object(frame.iloc[:,::-1],index=False,hash_key="monthly-trend-v1").to_numpy()
        fingerprints=list(zip(a.tolist(),b.tolist()))
    valid_array=valid.to_numpy()
    source_ids=frame["순번"].to_numpy() if city=="sejong" else None
    for month in months_key.dropna().unique():
        idx=np.flatnonzero((months_key==month).to_numpy())
        rec=months.setdefault(month,{"raw_rows":0,"excluded_rows":0,"duplicate_rows":0,"rentals":Counter(),"returns":Counter(),"days":Counter(),"hours":Counter(),"transfer":Counter(),"linked_count":0,"unknown_count":0})
        rec["raw_rows"]+=len(idx)
        good=[]
        bucket=seen.setdefault(month,set())
        for i in idx:
            if not valid_array[i]:rec["excluded_rows"]+=1;continue
            key=source_ids[i] if city=="sejong" else fingerprints[i]
            if key in bucket:rec["duplicate_rows"]+=1;continue
            bucket.add(key);good.append(i)
        if not good:continue
        take=frame.iloc[good]
        rec["rentals"].update(take[origin_col].value_counts().to_dict())
        back=ends.iloc[good].dt.strftime("%Y-%m")==month
        rec["returns"].update(take.loc[back.to_numpy(),dest_col].value_counts().to_dict())
        rec["days"].update(starts.iloc[good].dt.strftime("%Y-%m-%d").value_counts().to_dict())
        rec["hours"].update(starts.iloc[good].dt.hour.value_counts().to_dict())
        rec["linked_count"]+=int((take[origin_col].isin(near)|take[dest_col].isin(near)).sum())
        rec["unknown_count"]+=int((~take[origin_col].isin(known)|~take[dest_col].isin(known)).sum())
        if city=="sejong":rec["transfer"].update(take["환승 유무"].value_counts().to_dict())
    return raw,int(starts.isna().sum())


def collect_seoul_member(task):
    path_text,name,near_ids,known_ids=task
    path=Path(path_text)
    with zipfile.ZipFile(path) as z:
        info=z.getinfo(name)
        token=json.dumps(["seoul-monthly-v2",path.stat().st_size,info.CRC,name,near_ids,known_ids],ensure_ascii=False)
        cache=OUT/".checkpoints"/(hashlib.sha256(token.encode()).hexdigest()+".json")
        if cache.exists():
            print("checkpoint",name,flush=True)
            return json.loads(cache.read_text())
        months={};seen={};count=0;invalid=0
        print("process",name,flush=True)
        with z.open(name) as f:
            for frame in pd.read_csv(f,encoding="cp949",dtype=str,chunksize=150000,keep_default_na=False):
                n,bad=accumulate(frame,"seoul",months,seen,set(near_ids),set(known_ids));count+=n;invalid+=bad
        result={"months":months,"invalid_start":invalid,"source":{"archive":path.name,"member":name,"raw_rows":count,"encoding":"cp949","source_url":URLS["seoul"]}}
        cache.parent.mkdir(parents=True,exist_ok=True)
        temp=cache.with_suffix(".tmp")
        temp.write_text(json.dumps(result,ensure_ascii=False))
        temp.replace(cache)
        print("saved",name,count,flush=True)
        return result

def build_city(city):
    OUT.mkdir(parents=True,exist_ok=True)
    located,areas=prepare(city)
    near={k for k,s in located.items() if s["nearest_stop_distance_m"]<=300}
    months={};seen={};sources=[];invalid_start=0
    members=source_members(city)
    if city=="seoul":
        from concurrent.futures import ProcessPoolExecutor
        tasks=[(str(path),name,sorted(near),sorted(located)) for path,name in members]
        with ProcessPoolExecutor(max_workers=4) as pool:
            for chunk in pool.map(collect_seoul_member,tasks):
                invalid_start+=chunk["invalid_start"]
                sources.append(chunk["source"])
                for month,value in chunk["months"].items():
                    if month in months:raise ValueError("Overlapping Seoul source months; refusing to double count: "+month)
                    for key in ("rentals","returns","days","transfer"):value[key]=Counter(value[key])
                    value["hours"]=Counter({int(k):v for k,v in value["hours"].items()})
                    months[month]=value
    else:
        for path,name in members:
            print(city,name,flush=True)
            with zipfile.ZipFile(path) as z:
                with z.open(name) as probe:header=probe.readline()
                try:header.decode("utf-8-sig");encoding="utf-8-sig"
                except UnicodeDecodeError:encoding="cp949"
                count=0
                with z.open(name) as f:
                    for chunk in pd.read_csv(f,encoding=encoding,dtype=str,chunksize=150000,keep_default_na=False):
                        n,bad=accumulate(chunk,city,months,seen,near,set(located));count+=n;invalid_start+=bad
                sources.append({"archive":path.name,"member":name,"raw_rows":count,"encoding":encoding,"source_url":URLS[city]})
            if city!="sejong":seen.clear()
    results=[]
    for month,data in sorted(months.items()):
        days=sorted(data["days"]);y,m=map(int,month.split("-"))
        expected=[f"{month}-{d:02}" for d in range(1,calendar.monthrange(y,m)[1]+1)]
        missing=sorted(set(expected)-set(days))
        total=sum(data["rentals"].values())
        linked=data["linked_count"]
        unknown=data["unknown_count"]
        candidates=[]
        for sid,count in data["rentals"].items():
            station=located.get(sid)
            if not station or station["nearest_stop_distance_m"]<=500 or count<=0:continue
            distance=station["nearest_stop_distance_m"];deficit=(distance-500)/500
            candidates.append({"station_id":sid,"station_name":station.get("station_name") or sid,"rental_count":int(count),"return_count":int(data["returns"].get(sid,0)),"nearest_stop_distance_m":distance,"accessibility_deficit":deficit,"vulnerability":deficit*count,"potential_added_area_m2":areas[sid]})
        rank_candidates(candidates)
        returns=sum(data["returns"].values())
        results.append({"month":month,"period_start":expected[0],"period_end":expected[-1],"first_observation":days[0],"last_observation":days[-1],"observed_days":len(days),"expected_days":len(expected),"missing_dates":missing,"complete":not missing,
            "raw_rows":data["raw_rows"],"excluded_rows":data["excluded_rows"],"duplicate_rows":data["duplicate_rows"],"rental_count":total,"same_month_returns":returns,
            "daily_average":total/len(days) if days else None,"anchor_linked_trips":linked,"anchor_linked_ratio":linked/total if total else None,
            "unknown_endpoint_trips":unknown,"unknown_endpoint_ratio":unknown/total if total else None,"candidate_count":len(candidates),"top_candidates":candidates[:10],
            "transfer_raw_values":dict(data["transfer"]),"hourly_rentals":[int(data["hours"].get(h,0)) for h in range(24)],
            "absolute_station_net_flow":sum(abs(v-data["returns"].get(s,0)) for s,v in (data["rentals"]|Counter()).items())+sum(v for s,v in data["returns"].items() if s not in data["rentals"])})
    complete=[r for r in results if r["complete"]]
    repetitions=defaultdict(list)
    for row in complete:
        for c in row["top_candidates"]:repetitions[c["station_id"]].append({"month":row["month"],"rank":c["rank"]})
    repeated=sorted([{"station_id":sid,"station_name":located[sid]["station_name"],"top10_months":len(entries),"eligible_months":len(complete),"ranks":entries} for sid,entries in repetitions.items()],key=lambda r:(-r["top10_months"],r["station_id"]))[:10]
    raw_paths=sorted(set(p for p,_ in source_members(city)))
    hashes=[{"file":p.name,"sha256":sha(p),"bytes":p.stat().st_size} for p in raw_paths]
    result={"available":True,"region_id":city,"scope":"single_city_longitudinal","common_comparison":{"date_start":"2025-12-01","date_end":"2025-12-31","unchanged":True},
        "period_start":results[0]["first_observation"],"period_end":results[-1]["last_observation"],"months":results,"repeated_candidates":repeated,"unassigned_invalid_date_rows":invalid_start,
        "sources":sources,"source_files":hashes,"reference_master_sha256":sha(ROOT/"data/processed/stations.csv"),"reference_anchors_sha256":sha(ROOT/"data/processed/transit_anchors.csv"),
        "generated_at":datetime.now(timezone.utc).isoformat(),"limitations":[
        "각 도시의 별도 월별 관측자료이며 기간이 다른 도시의 총량·점수는 비교하지 않습니다. 공통 비교는 2025년 12월로 유지합니다.",
        "일평균은 관측된 날짜 수 기준이며 실제 운영일수 보정이 아닙니다. 자료 없는 날짜를 이용 0건으로 채우지 않습니다.",
        "지하철/BRT 주변 이용은 직선거리 300m 안 대여소에서 시작 또는 종료한 비중이며 실제 환승률이 아닙니다.",
        "공간 지표는 현재 서비스 위치·앵커 마스터로 정확한 ID만 연결한 고정 기준 재분석입니다. 과거 위치·설치·폐쇄 이력은 미검증이며 미연결 이력을 별도 표시합니다.",
        "개선 후보는 기존 500m 거리·대여 수요·잠재면적 공식을 그대로 재사용합니다. 신규 입지·PageRank·K-means의 월별 재계산이 아닙니다.",
        "후보 반복 횟수는 날짜가 모두 관측된 달의 상위10에 한정합니다. 관측일이 모두 있어도 수집 완전성·운영일수까지 보증하지 않습니다.",
        "기상·공휴일 영향과 실제 재고 부족·설치 효과는 추정하지 않았습니다. 반납은 같은 달 출발 이력 중 같은 달 반납만 포함합니다.",
        "서울·대전 중복은 전체 열의 이중64비트 행 지문, 세종은 월별 원본 순번으로 제외합니다. 지문 충돌의 이론적 가능성은 남습니다."
        ]}
    dec=next((r for r in results if r["month"]=="2025-12"),None)
    expected={"seoul":1954344,"daejeon":368491,"sejong":164366}[city]
    if not dec or dec["rental_count"]!=expected:raise ValueError((city,"December regression",dec and dec["rental_count"],expected))
    dest=OUT/(city+".json");tmp=dest.with_suffix(".tmp");tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False));tmp.replace(dest)
    print(city,"COMPLETE",len(results),sum(r["rental_count"] for r in results),flush=True)
    return result
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--city",choices=["seoul","daejeon","sejong"],required=True)
    a=p.parse_args();build_city(a.city)
