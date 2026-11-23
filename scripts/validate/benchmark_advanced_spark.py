"""Measured local pandas/Spark monthly OD aggregation, same real CSV rows and checksums."""
import csv,hashlib,json,os,platform,random,sqlite3,statistics,threading,time
from pathlib import Path
import pandas as pd
import psutil
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"docs/advanced-research-20261123"
WORK=ROOT/"data/advanced_benchmark"
SIZES=(50000,250000,1000000)
def canonical(rows):
    rows=sorted((str(m),str(a),str(b),int(n)) for m,a,b,n in rows)
    raw="\n".join("|".join(map(str,r)) for r in rows).encode()
    return {"groups":len(rows),"trips":sum(r[3] for r in rows),"sha256":hashlib.sha256(raw).hexdigest()}
def measured(fn,children=False):
    stop=threading.Event();samples=[];proc=psutil.Process()
    def monitor():
        while not stop.is_set():
            rss=proc.memory_info().rss
            if children:
                for p in proc.children(recursive=True):
                    try:rss+=p.memory_info().rss
                    except psutil.Error:pass
            samples.append(rss);stop.wait(.05)
    thread=threading.Thread(target=monitor);thread.start();t=time.perf_counter()
    try:value=fn();elapsed=time.perf_counter()-t
    finally:stop.set();thread.join()
    return value,elapsed,max(samples or [proc.memory_info().rss])
def export():
    WORK.mkdir(parents=True,exist_ok=True)
    source=ROOT/"data/individual/daejeon/analysis.sqlite"
    conn=sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True)
    for size in SIZES:
        path=WORK/(str(size)+".csv")
        if path.exists():continue
        rows=conn.execute("SELECT date,origin_station_id,destination_station_id,trip_count FROM od_daily ORDER BY rowid LIMIT ?",(size,))
        with path.open("w",newline="") as f:
            writer=csv.writer(f);writer.writerow(["date","origin","destination","trips"]);count=0
            for row in rows:writer.writerow(row);count+=1
        assert count==size
    conn.close()
def run():
    export();OUT.mkdir(parents=True,exist_ok=True)
    from pyspark.sql import SparkSession,functions as F,types as T
    started=time.perf_counter()
    spark=(SparkSession.builder.master("local[2]").appName("BikeLinkMeasuredBenchmark")
       .config("spark.ui.enabled","false").config("spark.driver.memory","2g")
       .config("spark.driver.extraJavaOptions","-XX:ActiveProcessorCount=2")
       .config("spark.sql.adaptive.enabled","false").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    startup=time.perf_counter()-started
    schema=T.StructType([T.StructField("date",T.StringType(),False),T.StructField("origin",T.StringType(),False),T.StructField("destination",T.StringType(),False),T.StructField("trips",T.LongType(),False)])
    def pandas_job(path):
        frame=pd.read_csv(path,dtype={"date":str,"origin":str,"destination":str,"trips":"int64"})
        frame["month"]=frame.date.str[:7]
        return frame.groupby(["month","origin","destination"],sort=False).trips.sum()
    def spark_job(path,parts):
        frame=spark.read.schema(schema).option("header",True).csv(str(path)).withColumn("month",F.substring("date",1,7))
        spark.conf.set("spark.sql.shuffle.partitions",str(parts))
        return frame.repartition(parts).groupBy("month","origin","destination").agg(F.sum("trips").alias("trips")).collect()
    # JVM classloading/action warmup separately recorded; no cache/persist and no inference from a lazy plan.
    begun=time.perf_counter();spark.range(1000).groupBy((F.col("id")%10).alias("key")).count().collect();warmup=time.perf_counter()-begun
    rows=[];truth={};inputs={}
    for size in SIZES:
        path=WORK/(str(size)+".csv")
        inputs[str(size)]={"sha256":hashlib.file_digest(path.open("rb"),"sha256").hexdigest(),"bytes":path.stat().st_size,"rows":size}
        for repeat in range(3):
            result,seconds,rss=measured(lambda:pandas_job(path))
            check=canonical([(m,a,b,v) for (m,a,b),v in result.items()])
            if size in truth:assert check==truth[size]
            truth[size]=check
            rows.append({"engine":"pandas","rows":size,"partitions":None,"repeat":repeat,"seconds":seconds,"peak_rss_bytes":rss,**check})
            for partitions in (1,2,4):
                result,seconds,rss=measured(lambda:spark_job(path,partitions),children=True)
                check=canonical([(r.month,r.origin,r.destination,r.trips) for r in result])
                assert check==truth[size],(size,partitions,check,truth[size])
                rows.append({"engine":"spark","rows":size,"partitions":partitions,"repeat":repeat,"seconds":seconds,"peak_rss_bytes":rss,**check})
            print("bench",size,repeat,flush=True)
            (OUT/"benchmark-progress.json").write_text(json.dumps(rows,indent=2))
    spark.stop()
    summary=[]
    for size in SIZES:
        for engine,partitions in [("pandas",None),("spark",1),("spark",2),("spark",4)]:
            group=[r for r in rows if r["rows"]==size and r["engine"]==engine and r["partitions"]==partitions]
            summary.append({"rows":size,"engine":engine,"partitions":partitions,"median_seconds":statistics.median(r["seconds"] for r in group),
              "min_seconds":min(r["seconds"] for r in group),"max_seconds":max(r["seconds"] for r in group),"max_peak_rss_bytes":max(r["peak_rss_bytes"] for r in group)})
    report={"available":True,"pipeline":"real daily OD CSV -> monthly OD SUM(trips), materialize result; checksum outside timer",
       "source":"daejeon individual full-history read-only DB, deterministic rowid prefixes; daily OD rows, not raw trip rows",
       "hardware":{"platform":platform.platform(),"logical_cpus":os.cpu_count(),"ram_bytes":psutil.virtual_memory().total},
       "spark_version":spark.version,"pandas_version":pd.__version__,"master":"local[2]","startup_seconds":startup,"warmup_seconds":warmup,
       "repeats":3,"inputs":inputs,"runs":rows,"summary":summary,"all_checksums_match":True,
       "limitations":["단일 서버의 부분 집계 단계: 전체 원본 정규화·분산 클러스터 성능을 주장하지 않음","OS 파일 캐시는 비우지 않음; JVM 시작/워밍업 별도, CSV 읽기·집계·결과 구체화 포함","pandas RSS는 Python, Spark RSS는 Python+Java 하위 프로세스. 모니터 간격50ms","파티션1/2/4 비교이며 CPU 노드 확장성은 미검증"]}
    (OUT/"benchmark.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    import matplotlib;matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7,4))
    for engine,parts in [("pandas",None),("spark",1),("spark",2),("spark",4)]:
        group=[r for r in summary if r["engine"]==engine and r["partitions"]==parts]
        ax.plot([r["rows"] for r in group],[r["median_seconds"] for r in group],marker="o",label=engine+(" p="+str(parts) if parts else ""))
    ax.set(xlabel="Actual input daily OD rows",ylabel="Median seconds (3 runs)",title="Local[2] aggregation scalability; equal-output verification")
    ax.legend();fig.tight_layout();fig.savefig(OUT/"benchmark.png",dpi=160);plt.close(fig)
    print("READY benchmark",flush=True)
if __name__=="__main__":run()
