"""Broad offline recovery search. Hidden locations never enter candidate generation."""
import math
from collections import Counter
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.stats import rankdata
import shapely
from shapely.geometry import Point
from sklearn.neighbors import BallTree
from backend.research import method_validation as m, recovery_evaluation as prior

POOLS=("legacy500","grid250","grid125","diagnostic125_50","facility_mix_50")
METHODS=("rental1000","activity500","kde300","facilities500","balanced",
         "anchor_demand","diverse300","diverse600","cover500")
CONFIGS=["legacy500:original"]+[p+":"+s for p in POOLS for s in METHODS]
STRICT=[k for k in CONFIGS if k.split(":")[0] in ("legacy500","grid250","grid125")]
DIAGNOSTIC=[k for k in CONFIGS if k not in STRICT]
OUT=m.ROOT/"docs/recovery-breadth-20261123"

def features(xy, ids, training, facilities, anchors):
    xy=np.asarray(xy,dtype=float).reshape(-1,2)
    lon,lat=m.UNPROJECT(xy[:,0],xy[:,1])
    located=[s for s in training if s.get("coordinate_valid")]
    sxy=np.array([m.PROJECT(s["longitude"],s["latitude"]) for s in located])
    tree=cKDTree(sxy)
    rental=np.array([s.get("rental_count") or 0 for s in located],dtype=float)
    activity=rental+np.array([s.get("return_count") or 0 for s in located])
    near=tree.query_ball_point(xy,1000)
    lengths=np.array([len(v) for v in near])
    ri=np.repeat(np.arange(len(xy)),lengths)
    ci=np.array([j for v in near for j in v],dtype=int)
    dist=np.linalg.norm(xy[ri]-sxy[ci],axis=1)
    demand=np.bincount(ri,weights=rental[ci],minlength=len(xy))
    kde=np.bincount(ri,weights=rental[ci]*np.exp(-0.5*(dist/300)**2),minlength=len(xy))
    act=np.bincount(ri,weights=activity[ci]*(dist<=500),minlength=len(xy))
    cover=csr_matrix(((dist<=500).astype(float),(ri,ci)),shape=(len(xy),len(located)))
    cover.eliminate_zeros()
    ftree=cKDTree([m.PROJECT(f["lon"],f["lat"]) for f in facilities]) if facilities else None
    fc=ftree.query_ball_point(xy,500,return_length=True).astype(float) if ftree else np.zeros(len(xy))
    atree=cKDTree([m.PROJECT(float(a["lon"]),float(a["lat"])) for a in anchors])
    anchor_distance=atree.query(xy)[0]
    nearest=BallTree(np.radians([[s["latitude"],s["longitude"]] for s in located]),metric="haversine").query(
        np.radians(np.column_stack((lat,lon))),k=1)[0][:,0]*m.EARTH_M
    return {"xy":xy,"lon":lon,"lat":lat,"ids":np.asarray(ids),
            "demand":demand,"activity":act,"kde":kde,"facility":fc,
            "anchor":anchor_distance,"nearest":nearest,"cover":cover,"weights":activity}

def subset(pool,index):
    return {k:(v if k=="weights" else v[index]) for k,v in pool.items()}

def make_pools(boundary, training, facilities, districts, anchors, city):
    baseline=m.baseline_geometry(anchors,boundary,500)
    old,_=m.grid_candidates(boundary,baseline,training,facilities,districts,use_population=city!="sejong")
    xy=[m.PROJECT(r["longitude"],r["latitude"]) for r in old]
    legacy=features(xy,[r["site_id"] for r in old],training,facilities,anchors) if old else None
    x0,y0,x1,y1=boundary.bounds
    xs=np.arange(int(x0//125)*125+62.5,x1,125)
    ys=np.arange(int(y0//125)*125+62.5,y1,125)
    xx,yy=np.meshgrid(xs,ys,indexing="ij")
    raw=np.column_stack((xx.ravel(),yy.ravel()))
    inside=shapely.covers(boundary,shapely.points(raw))
    lattice=raw[inside]
    fxy=np.array([m.PROJECT(f["lon"],f["lat"]) for f in facilities],dtype=float).reshape(-1,2)
    if len(fxy):fxy=fxy[shapely.covers(boundary,shapely.points(fxy))]
    allxy=np.concatenate((lattice,fxy),axis=0)
    ids=[f"lattice125-{x}-{y}" for x,y in lattice]+[f"facility-{i}" for i in range(len(fxy))]
    dense=features(allxy,ids,training,facilities,anchors)
    supported=(dense["demand"]>0)|(dense["facility"]>0)
    n=len(lattice)
    lattice_mask=np.arange(len(allxy))<n
    # Nested deterministic sampling gives 250m and125m grids without hidden-coordinate alignment.
    coarse=lattice_mask.copy()
    coarse[:n]=((np.round((lattice[:,0]-xs[0])/125).astype(int)%2)==0)&((np.round((lattice[:,1]-ys[0])/125).astype(int)%2)==0)
    strict=supported&(dense["nearest"]>300)
    diagnostic=supported&(dense["nearest"]>50)
    return {"legacy500":legacy,
            "grid250":subset(dense,strict&coarse),
            "grid125":subset(dense,strict&lattice_mask),
            "diagnostic125_50":subset(dense,diagnostic&lattice_mask),
            "facility_mix_50":subset(dense,diagnostic)}, old

def percentile(values):
    return (rankdata(values,method="average")-0.5)/len(values) if len(values) else values

def choose(pool,method,k=20):
    if pool is None or not len(pool["ids"]):return []
    score={"rental1000":pool["demand"],"activity500":pool["activity"],"kde300":pool["kde"],
           "facilities500":pool["facility"]}
    score["balanced"]=(percentile(pool["kde"])+percentile(pool["facility"])+percentile(pool["anchor"]))/3
    score["anchor_demand"]=percentile(pool["kde"])*np.exp(-pool["anchor"]/1000)
    if method=="cover500":
        remaining=pool["weights"].copy()
        chosen=[]
        for _ in range(min(k,len(pool["ids"]))):
            gain=np.asarray(pool["cover"].dot(remaining)).ravel()
            if chosen:gain[chosen]=-1
            best=int(np.argmax(gain))
            if gain[best]<=0:break
            chosen.append(best)
            remaining[pool["cover"].indices[pool["cover"].indptr[best]:pool["cover"].indptr[best+1]]]=0
    else:
        value=score.get(method,pool["kde"])
        order=np.lexsort((pool["ids"],-value))
        if method in ("diverse300","diverse600"):
            distance=300 if method=="diverse300" else 600
            chosen=[]
            for i in order:
                if not chosen or np.linalg.norm(pool["xy"][chosen]-pool["xy"][i],axis=1).min()>=distance:
                    chosen.append(int(i))
                    if len(chosen)>=k:break
        else:chosen=order[:k].tolist()
    return [{"site_id":str(pool["ids"][i]),"station_id":str(pool["ids"][i]),
             "longitude":float(pool["lon"][i]),"latitude":float(pool["lat"][i])} for i in chosen]

def fold(city, inputs, spec, keys=CONFIGS):
    boundary,stations,facilities,districts,anchors,od,info=inputs
    training,audit=m.retain_training(stations,od,spec["hidden_ids"])
    assert audit["hidden_station_count_in_training"]==0
    pools,old=make_pools(boundary,training,facilities,districts,anchors,city)
    output={"name":spec["name"],"target_ids":[s["station_id"] for s in spec["targets"]],
            "targets":spec["targets"],"hidden_ids":spec["hidden_ids"],"target_count":len(spec["targets"]),
            "audit":audit,"block":spec.get("block"),"methods":{}}
    possible={}
    for key in keys:
        pool_name,method=key.split(":")
        pool=pools[pool_name]
        if pool_name not in possible:
            if pool is None or not len(pool["ids"]):possible[pool_name]=0
            else:
                tree=cKDTree(pool["xy"])
                possible[pool_name]=sum(bool(tree.query_ball_point(m.PROJECT(t["longitude"],t["latitude"]),300)) for t in spec["targets"])
        top=old[:20] if method=="original" else choose(pool,method)
        matches={str(k):m.geographic_matches(spec["targets"],top[:k]) for k in (10,20)}
        covered=set()
        if pool is not None:
            indices={str(sid):i for i,sid in enumerate(pool["ids"])}
            for row in top[:10]:
                i=indices[row["site_id"]]
                covered.update(pool["cover"].indices[pool["cover"].indptr[i]:pool["cover"].indptr[i+1]].tolist())
        output["methods"][key]={"candidate_count":len(pool["ids"]) if pool is not None else 0,
            "generation_possible":possible[pool_name],"matches":matches,"selected_count":min(10,len(top)),
            "top":top,"covered_remaining_activity_500m":float(sum(pool["weights"][i] for i in covered)) if pool is not None else 0,
            "classification":"spacing300_expansion" if key in STRICT else "spacing50_diagnostic_not_installation",
            "conditional_recall10":matches["10"]["hits"]/possible[pool_name] if possible[pool_name] else None}
    output["random_baselines"]={}
    for pool_name in sorted({k.split(":")[0] for k in keys}):
        pool=pools[pool_name]
        rng=np.random.default_rng(20261123)
        values=[]
        for _ in range(30):
            ix=rng.choice(len(pool["ids"]),min(10,len(pool["ids"])),replace=False) if pool is not None else []
            top=[{"site_id":str(pool["ids"][i]),"longitude":float(pool["lon"][i]),"latitude":float(pool["lat"][i])} for i in ix]
            values.append(m.geographic_matches(spec["targets"],top)["recall"])
        output["random_baselines"][pool_name]={"repetitions":30,"mean_recall10":float(np.mean(values)),"std_recall10":float(np.std(values))}
    return output

def high_spec(stations,boundary,excluded=(),name="high_usage"):
    hidden=set(excluded)
    rows=[s for s in stations if s["station_id"] not in hidden and s.get("coordinate_valid") and s["rental_count"]>0
          and boundary.covers(Point(*m.PROJECT(s["longitude"],s["latitude"])))]
    rows.sort(key=lambda s:(-s["rental_count"],s["station_id"]))
    return {"name":name,"targets":rows[:10],"hidden_ids":[s["station_id"] for s in rows[:10]]}

def specifications(inputs,stage,excluded=(),excluded_block=None):
    boundary,stations=inputs[:2]
    prior_folds,_=prior.folds(stations,boundary,stage,excluded,excluded_block)
    return [high_spec(stations,boundary,excluded)]+[f for f in prior_folds if f["name"]!="gap_random"]

def select(rows,keys):
    scores={k:float(np.mean([f["methods"][k]["matches"]["10"]["recall"] for f in rows])) for k in keys}
    return max(keys,key=lambda k:scores[k]),scores
