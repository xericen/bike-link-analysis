"""Same-OD prospective Daejeon journeys with public official timetables and explicit assumptions."""
import hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/completion-20261123";RAW=ROOT/"data/raw/completion-20261123"
BASE="https://www.djtc.kr/kor/"
def fetch(endpoint,params):
    RAW.mkdir(parents=True,exist_ok=True)
    request=requests.Request("GET",BASE+endpoint,params=params).prepare()
    p=RAW/(hashlib.sha256(request.url.encode()).hexdigest()+".json")
    if p.exists():return json.loads(p.read_text())
    r=requests.get(request.url,timeout=20);r.raise_for_status();body=r.json()
    value={"source_url":r.url,"retrieved_at":datetime.now(timezone.utc).isoformat(),"sha256":hashlib.sha256(r.content).hexdigest(),"data":body}
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2));return value
def departures(info):
    times=[]
    for r in info["data"]["cTimeList"]:
        raw=r["tm_list_down_d"].strip()
        if not raw:continue
        minutes=[]
        for token in raw.split():
            m=re.fullmatch(r"(\d{1,2})(?:\(([^)]+)\))?",token)
            if not m:raise ValueError("Unparsed departure annotation: "+token)
            if m[2] and m[2]!="반석":continue
            minutes.append(int(m[1]))
        h=int(r["tm_zone"])
        if any(m>=60 for m in minutes):raise ValueError("Invalid minute")
        times.extend((h*60+m)*60 for m in minutes)
    if not times:raise ValueError("Empty official schedule")
    return sorted(set(times))
def itinerary(departure_s,access_minutes,departures_s,ride_s,entry_minutes=2,exit_minutes=2):
    arrival=departure_s+(access_minutes+entry_minutes)*60
    train=next((t for t in departures_s if t>=arrival),None)
    if train is None:return {"available":False,"reason":"막차 이후 승차 가능한 열차 없음"}
    return {"available":True,"origin_departure_s":departure_s,"access_minutes":access_minutes,"station_entry_minutes":entry_minutes,
      "board_s":train,"wait_minutes":(train-arrival)/60,"rail_minutes":ride_s/60,
      "station_exit_minutes":exit_minutes,"transfers":0,"transfer_wait_minutes":0,
      "arrival_s":train+ride_s+exit_minutes*60,"total_minutes":(train+ride_s+exit_minutes*60-departure_s)/60}
def run():
    OUT.mkdir(exist_ok=True,parents=True)
    source=json.loads((ROOT/"docs/final-validation-20261123/daejeon.json").read_text())["routes"]["candidates"]
    examples=[]
    for rank in (2,3,4):
        candidate=next(r for r in source if r["original_rank"]==rank);route=candidate.get("best_checked_route")
        if not route:continue
        code=re.search(r"\|(\d{3})$",route["anchor_id"]).group(1);official="1"+code
        info=fetch("ajaxFindStationInfo.do",{"oper":"ajaxFindStationInfo","station_code":official})
        if info["data"]["stationInfo"]["station_name"].removesuffix("역")!=route["anchor_name"].removesuffix("역"):raise ValueError("Station identity mismatch")
        table=departures(info)
        dist=fetch("ajaxfindStationTimeDistInfo.do",{"oper":"ajaxfindStationTimeDistInfo","str_stn_no":official,"end_stn_no":"1122"})
        duration=dist["data"]["timeDist"]
        if not duration.get("min") or not duration.get("sec"):raise ValueError("Official travel duration unavailable")
        # Official UI normalizes seconds >60; retain raw source and apply the same arithmetic.
        ride_s=int(duration["min"])*60+int(duration["sec"])
        rows=[]
        for start in (8*3600,8*3600+15*60,18*3600):
            walk=itinerary(start,route["before_minutes"],table,ride_s)
            bike=itinerary(start,route["after_minutes"],table,ride_s)
            rows.append({"origin_departure":f"{start//3600:02d}:{start//60%60:02d}","transit_only":walk,"bike_plus_transit":bike,
              "total_gain_minutes":walk["total_minutes"]-bike["total_minutes"] if walk["available"] and bike["available"] else None})
        sensitivity=[]
        for pickup in (0,2,5):
            for entry in (1,3,5):
                before=itinerary(8*3600,route["before_minutes"],table,ride_s,entry,2)
                after=itinerary(8*3600,route["after_minutes"]-2+pickup,table,ride_s,entry,2)
                sensitivity.append({"pickup_return_minutes":pickup,"entry_minutes":entry,"gain_minutes":before["total_minutes"]-after["total_minutes"] if before["available"] and after["available"] else None})
        examples.append({"site_id":candidate["site_id"],"original_rank":rank,"city":"daejeon","anchor_name":route["anchor_name"],
          "destination":"반석역 지상 출구(역 내부 이동2분 가정)","direction":"반석행","day_type":"평일",
          "schedule_scope":"2026-11-23 수집한 현행 공식 공개 시간표. 2025년 운행 재현 아님.",
          "access_scope":"현재 OSM 접근 모델, 대여·반납2분 가정. 실측 아님.",
          "scheduled_departures":len(table),"rail_minutes":ride_s/60,"examples":rows,"sensitivity":sensitivity,
          "sources":[{k:v for k,v in d.items() if k!="data"} for d in (info,dist)]})
    result={"available":bool(examples),"historical_2025_validated":False,"route_scope":"대전1호선 단일노선 대표3후보→반석역 출구",
      "transfer_scope":"철도 간 환승이 없는 여정으로 환승 횟수/대기0. 자전거 대여·반납 및 역 진입은 명시한 가정. 다중노선 환승은 미검증.",
      "examples":examples,"operational_update":False,"limitations":["현행 시간표와 현재 도로망을 적용한 전향적 예시이며 과거 실제 이용 여정이나 실시간 지연 관측이 아닙니다.",
      "공식 구간별 예상 소요시간을 적용했습니다. 실제 열차별 지연·정차 편차는 미관측.",
      "직접 도보 접근과 자전거 연계 접근 모두 같은 원점·출발시각·도착역 출구를 사용합니다. 대중교통 전체 망의 최단경로는 아닙니다.",
      "큰 도보 우회가 나타나는 후보는 현장 검증 전 시간 절감 효과를 확정하지 않습니다."]}
    (OUT/"journeys.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print([(e["original_rank"],[(r["origin_departure"],r["total_gain_minutes"]) for r in e["examples"]]) for e in examples])
if __name__=="__main__":run()
