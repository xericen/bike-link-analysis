"""Synthetic fixture checks only; experiment outcomes are separate observed artifacts."""
import numpy as np
from scipy.sparse import csr_matrix
from backend.research import recovery_breadth as b, method_validation as m

def pool():
    xy=np.array([[0.,0.],[10.,0.],[1000.,0.]])
    return {"ids":np.array(["a","b","c"]),"xy":xy,"lon":xy[:,0],"lat":xy[:,1],
            "demand":np.array([100.,90.,80.]),"activity":np.array([100.,100.,50.]),
            "kde":np.array([100.,90.,80.]),"facility":np.array([1.,2.,1.]),
            "anchor":np.array([500.,600.,1000.]),"nearest":np.array([400.,400.,400.]),
            "cover":csr_matrix([[1.,1.,0.],[1.,1.,0.],[0.,0.,1.]]),
            "weights":np.array([10.,20.,25.])}

def test_coverage_counts_overlap_once_and_reaches_other_area():
    p=pool();chosen=b.choose(p,"cover500")
    assert [r["site_id"] for r in chosen]==["a","c"]
    covered=set()
    for sid in [r["site_id"] for r in chosen]:
        i=list(p["ids"]).index(sid)
        covered.update(p["cover"].indices[p["cover"].indptr[i]:p["cover"].indptr[i+1]])
    assert sum(p["weights"][i] for i in covered)==55

def test_diversity_avoids_near_duplicate_candidates():
    assert [r["site_id"] for r in b.choose(pool(),"kde300",2)]==["a","b"]
    assert [r["site_id"] for r in b.choose(pool(),"diverse600",2)]==["a","c"]

def test_spacing50_track_cannot_be_selected_as_expansion():
    assert all(k.split(":")[0] in ("legacy500","grid250","grid125") for k in b.STRICT)
    assert all("50" in k for k in b.DIAGNOSTIC)
    rows=[{"methods":{k:{"matches":{"10":{"recall":float(k==b.DIAGNOSTIC[0])}}} for k in b.CONFIGS}}]
    assert b.select(rows,b.STRICT)[0] in b.STRICT
    assert b.select(rows,b.DIAGNOSTIC)[0]==b.DIAGNOSTIC[0]

def test_declared_combinations_are_unique_and_subset_preserves_demand_vector():
    assert len(b.CONFIGS)==46 and len(set(b.CONFIGS))==46
    p=pool();s=b.subset(p,np.array([True,False,True]))
    assert list(s["ids"])==["a","c"] and len(s["weights"])==3
    assert s["cover"].shape==(2,3)

def test_hidden_demands_do_not_reappear_in_features():
    x,y=m.PROJECT(127,37.5)
    stations=[{"station_id":sid,"latitude":37.5,"longitude":127.,"coordinate_valid":True,
               "rental_count":count,"return_count":0} for sid,count in (("hidden",999),("kept",10))]
    od=[{"origin_station_id":"hidden","destination_station_id":"kept","trip_count":100},
        {"origin_station_id":"kept","destination_station_id":"kept","trip_count":7}]
    training,audit=m.retain_training(stations,od,["hidden"])
    anchors=[{"lat":37.5,"lon":127.}]
    f=b.features([[x+100,y]],["candidate"],training,[],anchors)
    assert f["demand"][0]==7
    assert f["activity"][0]==14
    assert audit["hidden_station_count_in_training"]==0
