"""Build actual anchors and departure-hour OR linkage without changing source station IDs."""
import csv,json,shutil,zipfile,hashlib
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
from backend.services import real_data,transit,city_anchors
from backend.analysis.transit import hourly_linkage
from scripts.preprocess.normalize_sejong_details import normalize_member
from scripts.preprocess.integrate_transit_uploads import replace_versioned as _replace

def replace_versioned(path,content):
    return _replace(path,content,path.parent/"anchor_archive")
def write(path,rows,fields):
    import io
    out=io.StringIO();w=csv.DictWriter(out,fieldnames=fields);w.writeheader();w.writerows(rows)
    replace_versioned(path,out.getvalue().encode("utf-8"))
def run():
    out=real_data.PROCESSED;raw=out.parent/"raw"
    brt=list(csv.DictReader((raw/"sejong-brt-20250717.csv").open(encoding="cp949")))
    rows=[{k:r[k] for k in ("city","stop_id","name","type","lat","lon")} for r in transit.stops() if r["city"] in ("seoul","daejeon") and r["type"]=="지하철"]
    seen={};conflicts=[]
    for r in brt:
        key=(r["정류장고유번호"],float(r["위도"]),float(r["경도"]))
        sid="brt:"+r["정류장고유번호"]+":"+r["위도"]+":"+r["경도"]
        if key in seen:continue
        seen[key]=True
        rows.append({"city":"sejong","stop_id":sid,"name":r["정류장명"],"type":"버스","lat":r["위도"],"lon":r["경도"]})
    write(out/"transit_anchors.csv",rows,["city","stop_id","name","type","lat","lon"])
    source={"dataset_name":"세종특별자치시 BRT노선별 정류장 현황","source_url":"https://www.data.go.kr/data/15118026/fileData.do","reference_date":"2025-07-17","downloaded_at":datetime.now(timezone.utc).isoformat(),"raw_rows":len(brt),"unique_id_coordinate_rows":len(seen),"sha256":hashlib.sha256((raw/"sejong-brt-20250717.csv").read_bytes()).hexdigest(),"verification_status":"VERIFIED"}
    meta=real_data.read_json("transit_stops_manifest.json",{}).get("sources",[])+[source]
    replace_versioned(out/"transit_anchors_sources.json",json.dumps(meta,ensure_ascii=False,indent=2).encode())
    fields=["date","hour","total_count","linked_count","unknown_endpoint_count"]
    for city in ("seoul","daejeon"):
        # Same metro coordinates/300m OR rule as the previously raw-validated hourly files.
        src=out/f"transit_hourly_{city}_verified.csv"
        replace_versioned(out/f"anchor_hourly_{city}.csv",src.read_bytes())
    stations=city_anchors.linkage("sejong")["stations"]
    near={s["station_id"] for s in stations if s["coordinate_valid"] and s["nearest_anchor_distance_m"]<=300}
    known={s["station_id"] for s in stations if s["coordinate_valid"]}
    with zipfile.ZipFile(raw/"sejong-details-15106191.zip") as archive:
        member=next(n for n in archive.namelist() if "2025" in n and ("4분기" in n or "4Q" in n or "4q" in n))
        items,stats,encoding=normalize_member(archive,member,"2025-10-01","2025-10-31")
    counts=defaultdict(int)
    for _,a,b,started,ended,duration in items:counts[(started[:10],int(started[11:13]),a,b)]+=1
    hourly=hourly_linkage([{"date":day,"hour":h,"origin_station_id":a,"destination_station_id":b,"trip_count":n} for (day,h,a,b),n in counts.items()],near,known)
    write(out/"anchor_hourly_sejong.csv",hourly,fields)
    proof={"anchors_sha256":hashlib.sha256((out/"transit_anchors.csv").read_bytes()).hexdigest()}
    for city in ("seoul","daejeon","sejong"):
        proof[city]={"sha256":hashlib.sha256((out/f"anchor_hourly_{city}.csv").read_bytes()).hexdigest(),"source":"raw-selected Sejong2025-10 OR aggregation" if city=="sejong" else "previously raw-verified subway300m OR aggregation, same metro coordinates"}
    replace_versioned(out/"anchor_hourly_sources.json",json.dumps(proof,indent=2).encode())
    report={"source":source,"anchor_counts":{c:sum(r["city"]==c for r in rows) for c in ("seoul","daejeon","sejong")},
        "sejong_raw_period":["2025-10-01","2025-10-31"],"sejong_trips":sum(r["total_count"] for r in hourly),"sejong_linked":sum(r["linked_count"] for r in hourly),"known_station_ids":len(known),"within300_station_ids":len(near),"member":member}
    Path("docs/transit/city-anchors-input-20261117.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":run()
