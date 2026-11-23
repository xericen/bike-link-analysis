"""Reconcile the remaining raw-normalization output: anchor-linked/unknown endpoint hourly counts."""
import argparse,json,sqlite3,time
from pathlib import Path
import pandas as pd
from pyspark.sql import SparkSession,functions as F
from backend.analysis.transit import match_stations
from scripts.validate.spark_full_raw import ROOT,OUT,WORK,save,fingerprint_spark,fingerprint_sql
def run(cities=("seoul","daejeon","sejong")):
    master=pd.read_csv(ROOT/"data/processed/stations.csv")
    master=master.astype(object).where(pd.notna(master),None)
    anchors=pd.read_csv(ROOT/"data/processed/transit_anchors.csv")
    spark=(SparkSession.builder.master("local[2]").appName("BikeLinkRawAnchorReconcile").config("spark.ui.enabled","false")
      .config("spark.driver.memory","2g").config("spark.driver.extraJavaOptions","-XX:ActiveProcessorCount=2")
      .config("spark.sql.shuffle.partitions","4").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    try:
        for city in cities:
            begun=time.perf_counter();report=json.loads((OUT/("spark-raw-"+city+".json")).read_text())
            linked=match_stations(master[master.region_id==city].to_dict("records"),anchors[anchors.city==city].to_dict("records"))
            known=[r["station_id"] for r in linked if r["coordinate_valid"]]
            near=[r["station_id"] for r in linked if r["coordinate_valid"] and r["nearest_stop_distance_m"] is not None and r["nearest_stop_distance_m"]<=300]
            paths=[str(WORK/city/p.stem[len(city)+1:]/"normalized") for p in (OUT/"raw-pieces").glob(city+"-*.json")]
            if len(paths)!=report["members"]:raise ValueError("Piece manifest mismatch")
            df=spark.read.parquet(*paths)
            result=df.groupBy("date","hour").agg(F.count("*").alias("total"),
              F.sum((F.col("origin").isin(near)|F.col("destination").isin(near)).cast("long")).alias("linked"),
              F.sum((~F.col("origin").isin(known)|~F.col("destination").isin(known)).cast("long")).alias("unknown")).withColumn("n",F.col("total"))
            actual=fingerprint_spark(result,["date","hour","total","linked","unknown","n"])
            with sqlite3.connect((ROOT/"data/individual"/city/"analysis.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
                expected=fingerprint_sql(db.execute("SELECT date,hour,total_count,linked_count,unknown_endpoint_count,total_count FROM anchor_hours"))
            report["anchor_hours"]={"actual":actual,"expected":expected,"matches":actual==expected,"seconds":time.perf_counter()-begun,
              "rule":"same fixed common-master located IDs, anchor<=300m; linked = origin OR destination near anchor; unknown = either endpoint not located"}
            save(OUT/("spark-raw-"+city+".json"),report);print(city,actual==expected,actual["rows"],flush=True)
    finally:spark.stop()
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--cities",nargs="+",default=["seoul","daejeon","sejong"]);run(parser.parse_args().cities)
