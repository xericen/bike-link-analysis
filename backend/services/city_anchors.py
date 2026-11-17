"""City-specific transit anchors. Only offline builders perform matching."""
import csv,json,hashlib
from functools import lru_cache
from backend.services import transit,real_data
from backend.analysis.transit import match_stations
LABELS={"seoul":"지하철역","daejeon":"지하철역","sejong":"BRT 정류장·노선상 터미널"}
def stops():
    p=real_data.PROCESSED/"transit_anchors.csv"
    return transit._read(str(p),p.stat().st_mtime_ns,p.stat().st_size) if p.exists() else []
@lru_cache(maxsize=12)
def _matched(city,stamp,master_stamp):
    return match_stations(transit.station_master(city),[s for s in stops() if s["city"]==city])
def linkage(city,start=None,end=None):
    original=transit.linkage(city,start,end)
    selected=[s for s in stops() if s["city"]==city]
    p=real_data.PROCESSED/"transit_anchors.csv";m=real_data.PROCESSED/"stations.csv"
    enriched=_matched(city,p.stat().st_mtime_ns,m.stat().st_mtime_ns) if p.exists() else []
    old={r["station_id"]:r for r in original["stations"]}
    rows=[]
    for s in enriched:
        r=dict(s);o=old.get(r["station_id"],{})
        r.update(rental_count=o.get("rental_count"),return_count=o.get("return_count"),
            nearest_all_stop_distance_m=o.get("nearest_stop_distance_m"),
            nearest_anchor_distance_m=r["nearest_stop_distance_m"])
        rows.append(r)
    hourly=real_data.PROCESSED/("anchor_hourly_"+city+".csv")
    hours={};dates=[]
    proof=real_data.read_json("anchor_hourly_sources.json",{})
    valid=bool(hourly.exists() and proof.get("anchors_sha256")==hashlib.sha256(p.read_bytes()).hexdigest() and proof.get(city,{}).get("sha256")==hashlib.sha256(hourly.read_bytes()).hexdigest())
    if valid:
        for row in transit._read(str(hourly),hourly.stat().st_mtime_ns,hourly.stat().st_size):
            if start and row["date"]<start or end and row["date"]>end:continue
            dates.append(row["date"])
            h=int(row["hour"]);v=hours.setdefault(h,{"hour":h,"total_count":0,"linked_count":0,"unknown_endpoint_count":0})
            for key in ("total_count","linked_count","unknown_endpoint_count"):v[key]+=int(row[key])
    for r in hours.values():r["linkage_share"]=r["linked_count"]/r["total_count"] if r["total_count"] else None
    return {**original,"stations":rows,"available":bool(selected),"stop_count":len(selected),
        "anchor_label":LABELS[city],"anchor_definition":"metro" if city!="sejong" else "official BRT route stop",
        "map_stops":[{**r,"lat":float(r["lat"]),"lon":float(r["lon"])} for r in selected],
        "hourly_station_linkage":sorted(hours.values(),key=lambda r:r["hour"]) or None,
        "hourly_period_start":min(dates) if dates else None,"hourly_period_end":max(dates) if dates else None,
        "hourly_snapshot_valid":valid,"hourly_scope":"city-specific anchors; source-hash verified",
        "sources":real_data.read_json("transit_anchors_sources.json",[]),
        "limitations":original["limitations"]+["앵커: 서울·대전은 확보된 지하철 위치, 세종은 공식 BRT 노선 정류장. 별도 버스 환승센터 전수 자료 미확보.",
        "세종 이력2025-10·BRT목록2025-07·대여소 좌표2026-05의 시점 차이. 실제 환승 여부는 입증하지 않습니다."],
        "map_display_note":"도시별 실제 앵커 전체 표시. 일반 버스 포함 정류장 거리는 보조 참고입니다."}
