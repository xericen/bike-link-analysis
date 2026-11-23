"""Real 2025-09-30 published train-ID timetable, two-line representative journey model."""
import json,hashlib
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/visibility-20261123"
def seconds(x):
    if not isinstance(x,str):return None
    try:
        h,m,s=map(int,x.split(":"))
        if h<0 or not 0<=m<60 or not 0<=s<60:return None
        return h*3600+m*60+s
    except (ValueError,TypeError):return None
def legs(frame,line,origin,destination):
    f=frame[(frame.LINE==line)&(frame.WEEKTAG=="DAY")&(frame.GUBHANG=="0")]
    a=f[f.SI_ID==origin][["TRAIN_NO","INOUTTAG","EDT"]].dropna().drop_duplicates()
    b=f[f.SI_ID==destination][["TRAIN_NO","INOUTTAG","STT"]].dropna().drop_duplicates()
    pairs=a.merge(b,on=["TRAIN_NO","INOUTTAG"],how="inner")
    values=[]
    for train,direction,dep,arr in pairs.itertuples(index=False,name=None):
        d,e=seconds(dep),seconds(arr)
        if d is not None and e is not None and 0<e-d<=5400:
            values.append({"line":line,"train_id":train,"direction":direction,"origin_station_code":origin,
              "destination_station_code":destination,"departure_s":d,"arrival_s":e})
    return sorted(values,key=lambda x:(x["departure_s"],x["arrival_s"],x["train_id"]))
def solve(start_s,access_minutes,first,second,transfer_minutes=5,entry_minutes=2,exit_minutes=2):
    ready=start_s+(access_minutes+entry_minutes)*60
    options=[]
    for a in first:
        if a["departure_s"]<ready or a["departure_s"]>start_s+10800:continue
        transfer_ready=a["arrival_s"]+transfer_minutes*60
        for b in second:
            if b["departure_s"]<transfer_ready or b["arrival_s"]>start_s+10800:continue
            options.append((b["arrival_s"]+exit_minutes*60,a,b))
    if not options:return {"available":False,"reason":"조건 내 연결 가능한 실제 시간표 열차 조합 없음"}
    end,a,b=min(options,key=lambda x:(x[0],x[1]["departure_s"],x[2]["train_id"]))
    return {"available":True,"origin_departure_s":start_s,"arrival_s":end,"total_minutes":(end-start_s)/60,
      "access_minutes":access_minutes,"entry_minutes":entry_minutes,"exit_minutes":exit_minutes,
      "first_wait_minutes":(a["departure_s"]-ready)/60,"rail_minutes":((a["arrival_s"]-a["departure_s"])+(b["arrival_s"]-b["departure_s"]))/60,
      "transfer_walk_minutes":transfer_minutes,"transfer_wait_minutes":(b["departure_s"]-a["arrival_s"]-transfer_minutes*60)/60,
      "transfers":1,"legs":[a,b]}
def run():
    path=ROOT/"data/raw/visibility-20261123/seoul-timetable-20250930.csv"
    frame=pd.read_csv(path,dtype=str,encoding="utf-8-sig")
    required={"LINE","SI_ID","STATION_NM","WEEKTAG","INOUTTAG","TRAIN_NO","STT","EDT","GUBHANG"}
    if not required.issubset(frame.columns):raise ValueError("Unrecognized timetable schema")
    # Transfer station identities come from the official timetable, not geocoded name guesses.
    codes={}
    for name,line in [("답십리","5"),("장한평","5"),("종로3가","5"),("종로3가","1"),("서울역","1")]:
        values=frame[(frame.STATION_NM==name)&(frame.LINE==line)].SI_ID.dropna().unique()
        if len(values)!=1:raise ValueError("Ambiguous station identity: "+name+line)
        codes[name,line]=str(values[0])
    second=legs(frame,"1",codes["종로3가","1"],codes["서울역","1"])
    existing=json.loads((ROOT/"docs/conclusion-20261123/individual-seoul.json").read_text())
    examples=[]
    for candidate in existing["candidates"][:2]:
        route=candidate["route"];anchor=route["anchor_name"]
        if (anchor,"5") not in codes or route["status"]!="model_connected":continue
        first=legs(frame,"5",codes[anchor,"5"],codes["종로3가","5"])
        rows=[]
        for start in (8*3600,8*3600+900,18*3600):
            a=solve(start,route["before_minutes"],first,second)
            b=solve(start,route["after_minutes"],first,second)
            rows.append({"departure":f"{start//3600:02d}:{start//60%60:02d}","before":a,"after":b,
              "gain":a["total_minutes"]-b["total_minutes"] if a["available"] and b["available"] else None})
        sensitivity=[]
        for overhead in (0,2,5):
            for transfer in (3,5,8):
                a=solve(8*3600,route["before_minutes"],first,second,transfer)
                b=solve(8*3600,route["after_minutes"]-2+overhead,first,second,transfer)
                sensitivity.append({"pickup_return_minutes":overhead,"transfer_walk_minutes":transfer,"gain":a["total_minutes"]-b["total_minutes"] if a["available"] and b["available"] else None})
        examples.append({"site_id":candidate["site_id"],"original_rank":candidate["rank"],"anchor":anchor,
          "first_leg_services":len(first),"second_leg_services":len(second),"route_label":anchor+"(5호선) → 종로3가 환승 → 서울역(1호선)","pairs":rows,"sensitivity":sensitivity})
    result={"available":bool(examples),"city":"seoul","source_revision":existing["source_revision"],"reference_date":"2025-09-30",
      "source_url":"https://data.seoul.go.kr/dataList/OA-22522/L/1/datasetView.do","download_date":"2026-11-23",
      "raw_rows":len(frame),"weekday_rows":int((frame.WEEKTAG=="DAY").sum()),"missing_week_tag_rows":int(frame.WEEKTAG.isna().sum()),
      "sha256":hashlib.file_digest(path.open("rb"),"sha256").hexdigest(),"examples":examples,
      "scope_label":"2025-09-30 공개 시간표·현재 OSM의 대표 환승 모델.2025년12월 실제 운행 재현은 미검증.",
      "assumptions":{"pickup_return_minutes":2,"entry_minutes":2,"exit_minutes":2,"transfer_walk_minutes":5},
      "historical_december_validated":False,"actual_transfer_verified":False,"operational_update":False,
      "limitations":["공개 기준일과 실제 시행일·12월 중 변경을 확인하지 못했으므로12월 관측 결과로 합산하지 않음.",
      "환승은 종로3가5→1호선 한 경로이며 환승보행3/5/8분은 가정. 전체 망 최단경로나 실측 환승률이 아님.",
      "열차 ID·방향·호선·요일을 함께 연결하고 유효한 출발/도착 시간 쌍만 사용. 요일이 누락된109481행은 평일이라고 추정하지 않음.",
      "도보/자전거 접근은 현재 OSM, 과거 경로·역 진입·출구·현장 자전거 재고는 미검증."]}
    OUT.mkdir(exist_ok=True,parents=True);(OUT/"seoul-transfer-journeys.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print([(x["original_rank"],[(r["departure"],r["gain"]) for r in x["pairs"]]) for x in examples])
if __name__=="__main__":run()
