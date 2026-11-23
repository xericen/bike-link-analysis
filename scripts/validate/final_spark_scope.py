"""Full-history daily-OD aggregation in Spark; no raw normalization claim."""
import csv,hashlib,json,sqlite3,time
from pathlib import Path
from pyspark.sql import SparkSession,functions as F,types as T
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"docs/final-validation-20261123"
WORK=ROOT/"data/advanced_benchmark/final-scope"
def canonical(rows):
    return hashlib.sha256(json.dumps(sorted((str(a),int(b)) for a,b in rows),separators=(",",":")).encode()).hexdigest()
def run():
    WORK.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    spark=(SparkSession.builder.master("local[2]").appName("BikeLinkFullHistory")
      .config("spark.ui.enabled","false").config("spark.driver.memory","1g")
      .config("spark.driver.extraJavaOptions","-XX:ActiveProcessorCount=2").config("spark.sql.shuffle.partitions","2").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR");results=[]
    try:
        for city in ("seoul","daejeon","sejong"):
            db=ROOT/"data/individual"/city/"analysis.sqlite"
            with sqlite3.connect(db.resolve().as_uri()+"?mode=ro",uri=True) as conn:
                truth=conn.execute("SELECT substr(date,1,7),SUM(trip_count) FROM od_daily WHERE region_id=? GROUP BY 1",(city,)).fetchall()
                path=WORK/(city+".csv");count=0
                with path.open("w",newline="") as f:
                    writer=csv.writer(f);writer.writerow(["date","trips"])
                    for row in conn.execute("SELECT date,trip_count FROM od_daily WHERE region_id=?",(city,)):
                        writer.writerow(row);count+=1
            begun=time.perf_counter()
            frame=spark.read.schema("date STRING, trips LONG").option("header",True).csv(str(path))
            actual=[(r.month,r.trips) for r in frame.groupBy(F.substring("date",1,7).alias("month")).agg(F.sum("trips").alias("trips")).collect()]
            elapsed=time.perf_counter()-begun
            assert canonical(actual)==canonical(truth),(city,actual,truth)
            results.append({"city":city,"daily_od_rows":count,"months":len(truth),"trips":sum(int(r[1]) for r in truth),"seconds":elapsed,
              "input_sha256":hashlib.file_digest(path.open("rb"),"sha256").hexdigest(),"monthly_sha256":canonical(actual),"matches_sqlite":True})
            print(city,results[-1],flush=True)
            path.unlink() # temporary exported intermediate only, never a source or DB
        report={"pipeline":"Current full-history daily OD -> monthly SUM(trip_count)","master":"local[2]","spark_version":spark.version,
          "results":results,"all_match":True,"raw_normalization_in_spark":False,
          "limitations":["이번 실행은 현재 전체기간 정규화 후 집계 단계 재현입니다. 원본 정제 전체의 Spark 이관이나 분산 클러스터 성능 증거가 아닙니다.","단일 실행으로 엔진 간 속도 우열을 주장하지 않습니다. 기존36회 벤치마크를 별도로 보존합니다."]}
        (OUT/"spark.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    finally:spark.stop()
if __name__=="__main__":run()
