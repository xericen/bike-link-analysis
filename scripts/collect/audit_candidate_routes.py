"""Audit nine candidates using public FOSSGIS OSRM foot/bike graphs, <=1 request/sec."""
import hashlib,json,math,time
from datetime import datetime,timezone
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[2];FOLDER=ROOT/"data/processed/research"
CACHE=ROOT/"data/raw/route-audit";CACHE.mkdir(parents=True,exist_ok=True)
SOURCE="https://routing.openstreetmap.de/about.html"
UA="BikeLinkAnalysis/1.0 (https://github.com/xericen/bike-link-analysis; university research)"
def metres(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,(a[0],a[1],b[0],b[1]))
    return 6371008.8*2*math.asin(min(1,math.sqrt(math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2)))
def input_signature(inputs):
    selected={city:{k:x[k] for k in ("period_start","period_end","anchors")} |
              {"candidates":x["new_top3"][:2]+x["ranking"][:1]} for city,x in inputs["cities"].items()}
    return hashlib.sha256(json.dumps(selected,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def run():
    inputs=json.loads((FOLDER/"decision-inputs.json").read_text());rows=[];last=0
    for city,data in inputs["cities"].items():
        candidates=[{**r,"kind":"신규 입지","candidate_id":r["site_id"]} for r in data["new_top3"][:2]]
        candidates += [{**r,"kind":"기존 취약","candidate_id":r["station_id"]} for r in data["ranking"][:1]]
        anchors=data["anchors"]
        for row in candidates:
            point=(row["latitude"],row["longitude"])
            target=min(anchors,key=lambda s:metres(point,(float(s["lat"]),float(s["lon"]))))
            dest=(float(target["lat"]),float(target["lon"]))
            result={"city":city,"period_start":data["period_start"],"period_end":data["period_end"],
                    "candidate_id":row["candidate_id"],"kind":row["kind"],"anchor_id":target["stop_id"],
                    "anchor_name":target["name"],"latitude":point[0],"longitude":point[1],
                    "straight_distance_m":metres(point,dest),"routes":{}}
            for mode,profile in [("foot","foot"),("bike","cycling")]:
                url=f"https://routing.openstreetmap.de/routed-{mode}/route/v1/{profile}/{point[1]},{point[0]};{dest[1]},{dest[0]}"
                params={"overview":"simplified","geometries":"geojson","steps":"false"}
                key=hashlib.sha256(url.encode()).hexdigest();path=CACHE/(key+".json")
                if not path.exists():
                    time.sleep(max(0,1.05-(time.monotonic()-last)))
                    try:
                        response=requests.get(url,params=params,headers={"User-Agent":UA},timeout=25);last=time.monotonic()
                        response.raise_for_status();body=response.json()
                        body["_retrieved_at"]=datetime.now(timezone.utc).isoformat()
                        path.write_text(json.dumps(body,ensure_ascii=False))
                    except (requests.RequestException,ValueError) as error:
                        result["routes"][mode]={"status":"unavailable","error_type":type(error).__name__};continue
                body=json.loads(path.read_text())
                if body.get("code")!="Ok" or not body.get("routes"):
                    result["routes"][mode]={"status":"no_route","provider_code":body.get("code")};continue
                route=body["routes"][0];snaps=[p["distance"] for p in body["waypoints"]]
                result["routes"][mode]={"status":"ok" if max(snaps)<=50 else "snap_uncertain",
                    "distance_m":route["distance"],"duration_s":route["duration"],"snap_distances_m":snaps,
                    "snapped_coordinates":[p["location"] for p in body["waypoints"]],
                    "detour_ratio":route["distance"]/result["straight_distance_m"] if result["straight_distance_m"] else None,
                    "geometry":route.get("geometry"),"retrieved_at":body.get("_retrieved_at"),"response_sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            rows.append(result);print(city,row["candidate_id"],{m:r["status"] for m,r in result["routes"].items()},flush=True)
    for city in inputs["cities"]:
        cohort=[r for r in rows if r["city"]==city]
        for rank,r in enumerate(sorted(cohort,key=lambda r:r["straight_distance_m"]),1):r["straight_rank"]=rank
        for mode in ("foot","bike"):
            valid=[r for r in cohort if r["routes"].get(mode,{}).get("status")=="ok"]
            for rank,r in enumerate(sorted(valid,key=lambda r:r["straight_distance_m"]),1):r["routes"][mode]["comparable_straight_rank"]=rank
            for rank,r in enumerate(sorted(valid,key=lambda r:r["routes"][mode]["distance_m"]),1):r["routes"][mode]["distance_rank"]=rank
    result={"input_signature":input_signature(inputs),"source":SOURCE,"attribution":"© OpenStreetMap contributors; FOSSGIS OSRM","candidate_count":len(rows),"rows":rows,
        "limitations":["각 도시3후보의 같은 최근접 직선 앵커까지의 경로 비교. 다른 앵커의 네트워크 최단 경로는 탐색하지 않음.",
          "현재 OSM 도로망 모델이며 과거 관측 시점·실제 현장 보행·자전거 통행 가능성의 보장은 아님.",
          "스냅50m 초과는 순위 비교에서 제외. 스냅 접속 구간의 통행 가능성은 미검증. 서로 다른 도시의 거리 순위는 합산하지 않음."]}
    (FOLDER/"route-audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":run()
