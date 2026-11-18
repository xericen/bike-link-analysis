"""Prepared planning, full-stop coverage and distinct expansion/relocation evidence."""
import json,math,sqlite3
from pathlib import Path
from functools import lru_cache
from shapely.geometry import shape,Point
from shapely.ops import unary_union
from shapely import to_wkb
from backend.services import real_data,transit,precomputed,periods,city_anchors
from backend.analysis.vulnerability import _geometry
from backend.analysis.planning import PROJECT,vector,grid_sites,selection_scenarios,sensitivity,gap_grid

@lru_cache(maxsize=4)
def boundaries(city,stamp=None):
    path=real_data.PROCESSED/f"planning_boundary_{city}.json"
    if not path.exists():return None,[]
    features=json.loads(path.read_text())["features"]
    raw=json.loads((real_data.PROCESSED/"planning_population.json").read_text())
    cityname={"seoul":"서울특별시","daejeon":"대전광역시","sejong":"세종특별자치시"}[city]
    totals={}
    for row in raw:
        if row["시도명"]!=cityname:continue
        name=row["시군구명"].strip() or cityname
        # Portal rows are administrative-dong observations, never add city/district subtotals.
        if not row.get("읍면동명"):continue
        totals[name]=totals.get(name,0)+int(row["계"].replace(",",""))
    districts=[]
    for f in features:
        g=shape(f["geometry"]);name=f["properties"].get("title","")
        total=totals.get(name,totals.get(cityname) if city=="sejong" else None)
        districts.append({"name":name,"geometry":g,"population":total,
                          "population_density_km2":total/(g.area/1e6) if total is not None and g.area else None})
    return unary_union([d["geometry"] for d in districts]),districts

def boundary(city):
    p=real_data.PROCESSED/f"planning_boundary_{city}.json"
    return boundaries(city,p.stat().st_mtime_ns if p.exists() else None)[0]

def relocation(city,start,end,top=10):
    if not real_data.database_enabled():return {"available":False,"reason_code":"usage_missing","items":[]}
    where,args=real_data._where(city,start,end)
    with sqlite3.connect(real_data.database_path()) as c:
        rows=c.execute(f"SELECT station_id,hour,SUM(rental_count),SUM(return_count) FROM station_usage WHERE {where} AND hour IS NOT NULL GROUP BY station_id,hour",args).fetchall()
    lookup={s["station_id"]:s for s in transit.station_master(city)}
    aggregate={}
    for sid,h,r,b in rows:
        if b is None or sid not in lookup or sid=="X":continue
        item=aggregate.setdefault(sid,{"station_id":sid,"region_id":city,"station_name":lookup.get(sid,{}).get("station_name",""),"hourly":[],"rentals":0,"returns":0})
        item["rentals"]+=int(r);item["returns"]+=int(b)
        item["hourly"].append({"hour":h,"rentals":int(r),"returns":int(b),"net_outflow":int(r-b)})
    items=[]
    for item in aggregate.values():
        item["net_outflow"]=item["rentals"]-item["returns"]
        peak=max(item["hourly"],key=lambda h:abs(h["net_outflow"]))
        item.update(peak_hour=peak["hour"],peak_net_outflow=peak["net_outflow"],capacity=lookup.get(item["station_id"],{}).get("capacity"),
                    inventory_available=False,recommended_bike_count=None,decision="재배치 검토" if item["net_outflow"] else "관측 균형")
        items.append(item)
    items.sort(key=lambda r:(-abs(r["peak_net_outflow"]),r["station_id"]))
    return {"available":bool(items),"items":items[:top],"inventory_available":False,
            "message":"대여·반납 관측 기반 검토 대상. 재고·실제 부족·이동 수량은 미확보."}

def build(city,start,end):
    if city=="all":
        cities=[build(c,start,end) for c in ("seoul","daejeon","sejong")] # Exact common-period cohorts only.
        return {"city":"all","cities":cities,"available":any(c["available"] for c in cities),
                "coverage_features":[f for c in cities for f in c.get("coverage_features",[])],
                "new_sites":[r for c in cities for r in c.get("new_sites",[])],
                "scenario_pool":[],"selection_states":[],
                "comparison":{"date_start":start,"date_end":end,"excluded":[],"reason":"세 도시 공통 2025-12 관측 기간"}}
    linked=city_anchors.linkage(city,start,end);located=[s for s in linked["stations"] if s.get("coordinate_valid")]
    points=tuple(sorted(set((float(s["lat"]),float(s["lon"])) for s in city_anchors.stops() if s["city"]==city)))
    clip,districts=boundaries(city,(real_data.PROCESSED/f"planning_boundary_{city}.json").stat().st_mtime_ns if (real_data.PROCESSED/f"planning_boundary_{city}.json").exists() else None)
    if not located or not points or clip is None:
        reason="station_coordinates_missing" if not located else "transit_missing" if not points else "boundary_missing"
        return {"city":city,"available":False,"reason_code":reason,"new_sites":[],"coverage_features":[]}
    baseline=_geometry(points).intersection(clip)
    facilities_path=real_data.PROCESSED/f"planning_facilities_{city}.json"
    facilities=json.loads(facilities_path.read_text()) if facilities_path.exists() else []
    candidates=grid_sites(clip,baseline,linked["stations"],facilities,districts,use_population=city!="sejong")
    from backend.services.vulnerability import analyze
    old=analyze(city,start,end,top_n=20)
    # Boundary-clipped potential area for every observed station, including threshold sensitivity cohorts.
    assessed=[{**r,"potential_added_area_m2":Point(*PROJECT(r["longitude"],r["latitude"])).buffer(300,quad_segs=16).intersection(clip).difference(baseline).area} for r in located]
    sensitivity_rows=sensitivity(assessed)
    pool=[{**r,"kind":"신규 입지","region_id":city} for r in candidates[:3]]+[{**r,"site_id":r["station_id"],"kind":"기존 취약","region_id":city} for r in old["ranking"][:3]]
    locations=tuple((r["site_id"],r["latitude"],r["longitude"]) for r in pool)
    states=selection_scenarios(to_wkb(clip),to_wkb(baseline),locations)
    for r in candidates:r["region_id"]=city
    return {"city":city,"available":True,"date_start":start,"date_end":end,
            "coverage_features":[vector(baseline)],"gap_grid":gap_grid(clip,baseline),
            "anchor_label":city_anchors.LABELS[city],"boundary":vector(clip),
            "coverage_all_stop_count":len(points),"boundary_year":2020,"simplification_m":2,
            "new_sites":candidates[:20],"new_site_count":len(candidates),
            "facility_count":len(facilities),"population_basis":"세종은 동·읍면별 공간 대응이 없어 인구밀도 점수에서 제외" if city=="sejong" else "2026-10 구 주민등록 인구밀도. 실측 격자인구 아님.",
            "scenario_pool":pool,"selection_states":states,"sensitivity":sensitivity_rows,
            "rank_confidence":"insufficient_candidates" if old["candidate_count"]<5 else "relative_within_city",
            "relocation":relocation(city,start,end),
            "source_provenance":real_data.read_json("planning_sources.json",[]),
            "assumptions":["500m 격자, 기존 대여소300m 밖, 주변1000m 실제 대여 또는 시설500m 존재",
              "신규 입지 점수: 시설·주변대여·접근공백 동등가중, 서울·대전은 구 인구밀도 추가. 세종은 동일 시 밀도를 지역 차이로 쓰지 않음",
              "2020 경계·2026 인구/시설/위치자료의 시점 차이. 도로·토지·실제 설치 가능성 미검증",
              "선택 시나리오는 후보300m 추가 연결 가정이며 실제 환승·재배치 효과가 아님"]}

def prepared(city,start=None,end=None):
    start,end=periods.resolve(city,start,end)
    return precomputed.read("planning",city,start,end)

def scenario(city,start,end,selected):
    if city=="all":raise ValueError("시나리오는 한 도시를 선택하세요.")
    result=prepared(city,start,end)
    ids=sorted(set(selected))
    if len(ids)>6:raise ValueError("최대6개 후보를 선택하세요.")
    for state in result.get("selection_states",[]):
        if state["selected_ids"]==ids:return {**state,"city":city,"date_start":result.get("date_start"),"date_end":result.get("date_end")}
    raise ValueError("준비된 후보 목록에 없는 ID입니다.")
