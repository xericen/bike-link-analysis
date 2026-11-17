"""Offline spatial planning primitives. Units are metres in EPSG:5179."""
import itertools
from functools import lru_cache
import numpy as np
from pyproj import Transformer
from shapely import from_wkb,to_wkb
from shapely.geometry import Point,box,mapping
from shapely.ops import unary_union,transform
from sklearn.neighbors import BallTree
from backend.analysis.transit import EARTH_M
PROJECT=Transformer.from_crs(4326,5179,always_xy=True).transform
UNPROJECT=Transformer.from_crs(5179,4326,always_xy=True).transform

def rank_stable(rows,weights):
    if not rows:return []
    def percentile(key,value):
        values=[r[key] for r in rows]
        return (sum(x<value for x in values)+.5*sum(x==value for x in values))/len(values)
    scores={r["station_id"]:sum(w*percentile(k,r[k]) for k,w in weights.items()) for r in rows}
    return sorted(rows,key=lambda r:(-scores[r["station_id"]],r["station_id"]))

def sensitivity(stations,thresholds=(300,500,800)):
    results=[]
    for distance in thresholds:
        rows=[{**s,"accessibility_deficit":(s["nearest_stop_distance_m"]-distance)/distance}
              for s in stations if s.get("nearest_stop_distance_m") is not None and s["nearest_stop_distance_m"]>distance and (s.get("rental_count") or 0)>0]
        for label,weights in [("균등",{"accessibility_deficit":1/3,"rental_count":1/3,"potential_added_area_m2":1/3}),
                              ("접근성 우선",{"accessibility_deficit":.5,"rental_count":.25,"potential_added_area_m2":.25}),
                              ("수요 우선",{"accessibility_deficit":.25,"rental_count":.5,"potential_added_area_m2":.25})]:
            ranked=rank_stable(rows,weights)
            results.append({"distance_m":distance,"policy":label,"weights":weights,"candidate_count":len(rows),
                            "top_ids":[r["station_id"] for r in ranked[:10]]})
    baseline=next(r for r in results if r["distance_m"]==500 and r["policy"]=="균등")["top_ids"]
    for row in results:
        other=row["top_ids"];common=set(baseline)&set(other);union=set(baseline)|set(other)
        row["top10_jaccard"]=len(common)/len(union) if union else None
        row["mean_rank_shift"]=sum(abs(baseline.index(i)-other.index(i)) for i in common)/len(common) if common else None
    return results

def vector(geometry,tolerance=2):
    simplified=geometry.simplify(tolerance,preserve_topology=True)
    return {"type":"Feature","properties":{"simplification_m":tolerance,"source_area_m2":geometry.area,
            "simplified_area_m2":simplified.area,"area_error_ratio":abs(simplified.area-geometry.area)/geometry.area if geometry.area else 0},
            "geometry":mapping(transform(UNPROJECT,simplified))}

def grid_sites(boundary,baseline,stations,facilities,districts,step=500,use_population=True):
    located=[r for r in stations if r.get("coordinate_valid")]
    if not located:return []
    tree=BallTree(np.radians([[r["latitude"],r["longitude"]] for r in located]),metric="haversine")
    facility_points=[(Point(*PROJECT(r["lon"],r["lat"])),r) for r in facilities]
    x0,y0,x1,y1=boundary.bounds
    candidates=[]
    for x in range(int(x0//step)*step,int(x1)+step,step):
        for y in range(int(y0//step)*step,int(y1)+step,step):
            cell=box(x,y,x+step,y+step).intersection(boundary)
            if cell.is_empty or cell.area<step*step*.25:continue
            centre=cell.representative_point();lon,lat=UNPROJECT(centre.x,centre.y)
            distances,indices=tree.query(np.radians([[lat,lon]]),k=1)
            nearest=float(distances[0][0]*EARTH_M)
            if nearest<=300:continue
            nearby=tree.query_radius(np.radians([[lat,lon]]),r=1000/EARTH_M)[0]
            demand=sum(located[int(i)].get("rental_count") or 0 for i in nearby)
            facilities_count=sum(p.distance(centre)<=500 for p,r in facility_points)
            if not demand and not facilities_count:continue
            district=next((d for d in districts if d["geometry"].covers(centre)),None)
            density=district.get("population_density_km2") if district else None
            if density is None and use_population:continue
            candidates.append({"site_id":f"grid-{x}-{y}","station_id":f"grid-{x}-{y}",
                "latitude":lat,"longitude":lon,"district":district["name"],"population_density_km2":density if use_population else None,
                "population_basis":"administrative district density; not measured grid population",
                "facilities_within_500m":facilities_count,"nearby_rentals_1000m":demand,
                "nearest_station_distance_m":nearest,"gap_ratio":cell.difference(baseline).area/cell.area,
                "potential_added_area_m2":centre.buffer(300,quad_segs=16).intersection(boundary).difference(baseline).area})
    if not candidates:return []
    keys=(("population_density_km2",) if use_population else ())+("facilities_within_500m","nearby_rentals_1000m","gap_ratio")
    for c in candidates:
        c["score_components"]={k:(sum(r[k]<c[k] for r in candidates)+.5*sum(r[k]==c[k] for r in candidates))/len(candidates) for k in keys}
        c["score"]=sum(c["score_components"].values())/len(keys)
    candidates.sort(key=lambda c:(-c["score"],c["site_id"]))
    for i,c in enumerate(candidates,1):c["rank"]=i
    return candidates

@lru_cache(maxsize=12)
def selection_scenarios(boundary_wkb,baseline_wkb,locations):
    boundary=from_wkb(boundary_wkb);baseline=from_wkb(baseline_wkb)
    buffers={sid:Point(*PROJECT(lon,lat)).buffer(300,quad_segs=16).intersection(boundary).difference(baseline)
             for sid,lat,lon in locations}
    states=[]
    for count in range(len(locations)+1):
        for ids in itertools.combinations(sorted(buffers),count):
            added=unary_union([buffers[i] for i in ids])
            gross=sum(buffers[i].area for i in ids)
            states.append({"selected_ids":list(ids),"baseline_area_m2":baseline.area,
                "added_area_m2":added.area,"overlap_area_m2":max(0,gross-added.area),
                "linked_area_m2":baseline.area+added.area,
                "increase_ratio":added.area/baseline.area if baseline.area else None,
                "added_geometry":vector(added)["geometry"]})
    return states


def gap_grid(boundary,baseline,step=500):
    features=[]
    x0,y0,x1,y1=boundary.bounds
    for x in range(int(x0//step)*step,int(x1)+step,step):
        for y in range(int(y0//step)*step,int(y1)+step,step):
            cell=box(x,y,x+step,y+step).intersection(boundary)
            if cell.is_empty:continue
            gap=cell.difference(baseline)
            if gap.is_empty or gap.area<=0:continue
            f=vector(gap);f["properties"].update(grid_size_m=step,gap_area_m2=gap.area,gap_ratio=gap.area/cell.area)
            features.append(f)
    return {"type":"FeatureCollection","features":features}
