"""Read-only verification of transit-demand input joins and overlapping catchments."""
import json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from scripts.preprocess.build_transit_demand import ROOT, station_key, read_rail, find_file, haversine, city_comparison
def run():
    source=ROOT.parent/".reviewops-bike-publish"
    bigdata=next(p for p in source.iterdir() if p.is_dir() and station_key(p.name)=="빅데")
    anchors=pd.read_csv(ROOT/"data/processed/transit_anchors.csv")
    stations=pd.read_csv(ROOT/"data/processed/stations.csv")
    usage=pd.read_csv(ROOT/"data/processed/station_usage.csv")
    usage=usage[usage.date.between("2025-12-01","2025-12-31")]
    assert not stations.duplicated(["region_id","station_id"]).any()
    totals=usage.groupby("region_id").rental_count.sum().to_dict()
    assert totals=={"seoul":1954344,"daejeon":368491,"sejong":164366}
    bike=stations.merge(usage.groupby(["region_id","station_id"],as_index=False)[["rental_count","return_count"]].sum(),on=["region_id","station_id"],how="left").fillna({"rental_count":0,"return_count":0})
    artifact=json.loads((ROOT/"data/reference/transit_demand_202512.json").read_text())
    result={"rentals":totals,"cities":{}}
    for city,token in [("seoul","서울"),("daejeon","대전")]:
        rail,_=read_rail(find_file(bigdata,("2025",token,"승강차실적"),".xls"),2025)
        calc=city_comparison(city,rail,anchors,bike)
        saved=artifact["cities"][city]
        assert calc==saved, city+" artifact differs from raw recalculation"
        a=anchors[anchors.city==city].copy();a["key"]=a.name.map(station_key)
        keys=set(rail.station_name.map(station_key))
        b=bike[(bike.region_id==city)&bike.latitude.notna()&bike.longitude.notna()].copy()
        multiplicity=np.zeros(len(b),dtype=int)
        for row in calc["stations"]:
            multiplicity+=haversine(row["latitude"],row["longitude"],b.latitude.to_numpy(),b.longitude.to_numpy())<=500
        pairs=int(multiplicity.sum()); covered=int((multiplicity>0).sum())
        result["cities"][city]={
          "anchor_rows":len(a),"unique_anchor_names":a.key.nunique(),
          "anchor_names_without_rail":sorted(set(a.key)-keys),
          "rail_rows":len(rail),"rail_unique_names":calc["rail_unique_station_names"],
          "unmatched_rail_names":calc["unmatched_station_names"],
          "matched":calc["matched_station_names"],"correlations":calc["correlations"],
          "station_catchment_pairs":pairs,"unique_bike_stations_in_catchments":covered,
          "bike_stations_in_multiple_catchments":int((multiplicity>1).sum()),
          "summed_station_activity":sum(r["bike_activity_500m"] for r in calc["stations"]),
          "deduplicated_activity":int((b.loc[multiplicity>0,"rental_count"]+b.loc[multiplicity>0,"return_count"]).sum()),
          "examples":calc["stations"][:3]}
    return result
if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
