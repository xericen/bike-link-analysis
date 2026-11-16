"""Versioned transit snapshot, lightweight station enrichment, date-filtered true OD ratios."""
import csv,hashlib,json,sqlite3
from functools import lru_cache
from backend.services import real_data
from backend.analysis.transit import match_stations

def stops_path():return real_data.PROCESSED/"transit_stops.csv"
def stops_digest():
    p=stops_path()
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
@lru_cache(maxsize=8)
def _read(path,mtime,size):
    with open(path,encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def stops():
    p=stops_path()
    return _read(str(p),p.stat().st_mtime_ns,p.stat().st_size) if p.exists() else []
def station_master(city):
    rows=[s for s in real_data.snapshot()["stations"] if s["region_id"]==city]
    if city=="seoul" and any(s["station_id"].startswith("ST-") for s in rows):
        rows=[s for s in rows if s["station_id"].startswith("ST-")]
    return rows
@lru_cache(maxsize=16)
def _matched(city,path,stops_stamp,master_stamp):
    return match_stations(station_master(city),[s for s in stops() if s["city"]==city])
def matched(city):
    p=stops_path();m=real_data.PROCESSED/"stations.csv"
    if not p.exists():return []
    return _matched(city,str(real_data.PROCESSED),p.stat().st_mtime_ns,m.stat().st_mtime_ns if m.exists() else 0)
def linkage(city,date_start=None,date_end=None):
    selected=[s for s in stops() if s["city"]==city]
    manifest=real_data.read_json("transit_stops_manifest.json",{})
    meta={"city":city,"date_start":date_start,"date_end":date_end,"distance_unit":"m","radius_m":[300,500],
      "available":bool(selected),"source_document":"docs/transit_stops_sources.md",
      "sources":[{**s,"verification_status":"VERIFIED"} for s in manifest.get("sources",[])],
      "limitations":["정류장과 대여소의 직선거리이며 실제 보행·환승 여부가 아닙니다.",
        "정류장 수는 도시명/주소 분류 기준입니다. 경계 박스 밖 BIS 정류장은 별도 경고 후 보존했습니다.",
        "원본별·행별 기준일이 관측 기간과 다를 수 있으며 누락 노선의 가능성이 있습니다.",
        "역 연계 비율은 한쪽 이상이 역300m 내인 이동 비중이며 실제 환승률이 아닙니다. 미확보 값은 null입니다."]}
    if not selected:return {**meta,"stations":[],"hourly_station_linkage":None,"message":"정류장 자료 미확보"}
    rows=[dict(r) for r in matched(city)]
    if real_data.database_enabled():
        where,args=real_data._where(city,date_start,date_end)
        with sqlite3.connect(real_data.database_path()) as c:
            usage={sid:(int(a),int(b) if b is not None else None) for sid,a,b in c.execute(
                f"SELECT station_id,SUM(rental_count),SUM(return_count) FROM station_usage WHERE {where} GROUP BY station_id",args)}
        for r in rows:r["rental_count"],r["return_count"]=usage.get(r["station_id"],(None,None))
    else:
        profiles={s["station_id"]:s for s in real_data.profiles(city,date_start,date_end)}
        for r in rows:
            p=profiles.get(r["station_id"],{});r.update(rental_count=p.get("rental_count"),return_count=p.get("return_count"))
    path=real_data.PROCESSED/f"transit_hourly_{city}_verified.csv"
    stamp=real_data.read_json(f"transit_hourly_{city}_verified.meta.json",{})
    valid_snapshot=(stamp.get("stops_sha256")==stops_digest()) if manifest else (not stamp or stamp.get("stops_sha256")==stops_digest())
    hours={};dates=[]
    if valid_snapshot and path.exists() and any(s["type"]=="지하철" for s in selected):
        for row in _read(str(path),path.stat().st_mtime_ns,path.stat().st_size):
            if date_start and row["date"]<date_start or date_end and row["date"]>date_end:continue
            h=int(row["hour"]);dates.append(row["date"])
            item=hours.setdefault(h,{"hour":h,"total_count":0,"linked_count":0,"unknown_endpoint_count":0})
            for key in ["total_count","linked_count","unknown_endpoint_count"]:item[key]+=int(row[key])
    lookup={s["stop_id"]:s for s in selected}
    for row in rows:
        distances=[(row.get(f"nearest_{p}_distance_m"),row.get(f"nearest_{p}_stop_id")) for p in ["bus","subway"]]
        distances=[(d,sid) for d,sid in distances if d is not None and sid in lookup]
        if distances:
            d,sid=min(distances);stop=lookup[sid]
            row.update(nearest_stop_id=sid,nearest_stop_name=stop["name"],nearest_stop_lat=float(stop["lat"]),nearest_stop_lon=float(stop["lon"]))
    for row in hours.values():row["linkage_share"]=row["linked_count"]/row["total_count"] if row["total_count"] else None
    return {**meta,"stations":rows,"stop_count":len(selected),"stop_types":sorted({s["type"] for s in selected}),
      "hourly_station_linkage":sorted(hours.values(),key=lambda x:x["hour"]) or None,
      "hourly_period_start":min(dates) if dates else None,"hourly_period_end":max(dates) if dates else None,
      "hourly_snapshot_valid":valid_snapshot,
      "map_stops":[{**s,"lat":float(s["lat"]),"lon":float(s["lon"])} for s in selected[::max(1,(len(selected)+599)//600)][:600]],
      "map_display_note":"정류장 지도는 도시별 최대600개 표본입니다. 거리 지표는 정규화한 전체 자료로 계산합니다."}
