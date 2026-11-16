"""Integrate supplied official snapshots. Keep an auditable archive of previous outputs."""
import argparse,csv,hashlib,json,math,shutil
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
from scripts.preprocess.normalize_transit import FIELDS,read_rows
from scripts.collect.collect_transit_stops import ROOT

CITY_NAMES={"서울특별시":"seoul","대전광역시":"daejeon","세종특별자치시":"sejong"}
EXPECTED_BUS={"seoul":17082,"daejeon":3259,"sejong":3035}
# Audit rectangles, not administrative polygons. Boundary-crossing BIS stops are retained.
AUDIT_BOXES={"seoul":(37.413,37.716,126.734,127.270),
 "daejeon":(36.17,36.50,127.24,127.57),"sejong":(36.40,36.76,127.12,127.42)}
def within_box(city,lat,lon):
    a,b,c,d=AUDIT_BOXES[city]
    return a<=lat<=b and c<=lon<=d
def normalize_uploads(bus_rows,rail_rows):
    rows=[];warnings=[];seen={};stats={"bus_raw_rows":len(bus_rows),"rail_raw_rows":len(rail_rows),"bus":Counter(),"rail_before":Counter(),"rail_after":Counter(),"rail_duplicates":[],"bbox_warnings":Counter()}
    def add(city,sid,name,kind,lat,lon,identity=None):
        lat,lon=float(lat),float(lon)
        if not(math.isfinite(lat) and math.isfinite(lon) and 33<=lat<=39 and 124<=lon<=132):
            raise ValueError("한국 범위 밖 또는 결측 좌표: "+sid)
        row=dict(city=city,stop_id=str(sid),name=str(name),type=kind,lat=lat,lon=lon)
        key=(city,kind,sid)
        if key in seen:
            if seen[key] != row:
                if kind != "지하철" or (seen[key]["lat"],seen[key]["lon"]) != (lat,lon):
                    raise ValueError("동일 복합키의 상충 좌표: "+sid)
                seen[key].update(row)
            stats["rail_duplicates"].append({"city":city,"stop_id":sid,"rule":"same operator/line/station and identical coordinates; latest per-row reference date/name retained"})
            return False
        seen[key]=row;rows.append(row)
        if not within_box(city,lat,lon):
            warnings.append({**row,"reason":"audit_bbox_outside","action":"retained; city is source 도시명/address, not bbox; inspect boundary-crossing route"})
            stats["bbox_warnings"][city]+=1
        return True
    for r in bus_rows:
        city=CITY_NAMES.get(r["도시명"])
        if not city:continue
        if add(city,r["정류장번호"],r["정류장명"],"버스",r["위도"],r["경도"]):stats["bus"][city]+=1
    for r in sorted(rail_rows,key=lambda x:str(x.get("데이터기준일자") or "")[:10]):
        city=next((v for k,v in CITY_NAMES.items() if str(r.get("역사도로명주소") or "").startswith(k)),None)
        if not city:continue
        stats["rail_before"][city]+=1
        # UTF-8 escaped components prevent ambiguous concatenation and cross-operator collisions.
        sid="rail:"+"|".join(quote(str(r[k]).strip(),safe="") for k in ["운영기관명","노선번호","역번호"])
        if add(city,sid,r["역사명"],"지하철",r["역위도"],r["역경도"]):stats["rail_after"][city]+=1
    stats["total_normalized"]=len(rows)
    return rows,stats,warnings

def replace_versioned(path,content,archive):
    path=Path(path);payload=content.encode() if isinstance(content,str) else content
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()==payload:return
        archive=Path(archive);archive.mkdir(parents=True,exist_ok=True)
        old=archive/(path.name+"."+hashlib.sha256(path.read_bytes()).hexdigest()[:12])
        if not old.exists():shutil.copy2(path,old)
    tmp=path.with_suffix(path.suffix+".incoming")
    tmp.write_bytes(payload);tmp.replace(path)

def integrate(bus,rail,output=None,report=None):
    import io
    bus,rail=Path(bus),Path(rail)
    rows,stats,warnings=normalize_uploads(read_rows(bus),read_rows(rail))
    if dict(stats["bus"])!=EXPECTED_BUS:raise ValueError("공식 업로드 행수 불일치: "+str(stats["bus"]))
    output=Path(output or ROOT/"data/processed/transit_stops.csv")
    archive=output.parent/"transit_archive"
    out=io.StringIO(newline="");w=csv.DictWriter(out,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    now=datetime.now(timezone.utc).isoformat()
    manifest={"schema":FIELDS,"integrated_at":now,"sources":[
      {"dataset_name":"국토교통부 전국 버스정류장 위치정보","source_url":"https://www.data.go.kr/data/15067528/fileData.do","downloaded_at":"2026-11-16","reference_date":"2026-11-09","sha256":hashlib.sha256(bus.read_bytes()).hexdigest(),"raw_rows":stats["bus_raw_rows"]},
      {"dataset_name":"전국 도시철도 역사정보 전체기관","source_url":"https://data.kric.go.kr/rips/M_01_01/detail.do?id=32","downloaded_at":"2026-11-16","reference_date":"file 20260630; per-row dates vary","sha256":hashlib.sha256(rail.read_bytes()).hexdigest(),"raw_rows":stats["rail_raw_rows"]}],
      "stops_sha256":hashlib.sha256(out.getvalue().encode()).hexdigest(),"stats":stats,"bbox_rule":AUDIT_BOXES,
      "bbox_policy":"warnings retained, source city classification preserved; not administrative clipping"}
    replace_versioned(output,out.getvalue(),archive)
    replace_versioned(output.parent/"transit_stops_manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2),archive)
    replace_versioned(output.parent/"transit_bbox_warnings.json",json.dumps(warnings,ensure_ascii=False,indent=2),archive)
    if report:
        target=Path(report);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--bus",required=True);p.add_argument("--rail",required=True)
    p.add_argument("--output");p.add_argument("--report");a=p.parse_args()
    print(json.dumps(integrate(a.bus,a.rail,a.output,a.report)["stats"],ensure_ascii=False))
