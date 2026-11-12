"""Local Spark batch; original ZIP or previously validated Trip CSVs, no production overwrite."""
import argparse
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

def session(master="local[*]"):
    from pyspark.sql import SparkSession
    return (SparkSession.builder.master(master).appName("BikeLink-Tashu")
        .config("spark.ui.enabled","false")
        .config("spark.driver.memory","2g")
        .config("spark.driver.extraJavaOptions","-XX:ActiveProcessorCount=4")
        .config("spark.sql.shuffle.partitions","32")
        .config("spark.default.parallelism","4")
        .config("spark.sql.files.maxPartitionBytes",64*1024*1024)
        .config("spark.sql.session.timeZone","Asia/Seoul")
        .getOrCreate())

def aggregates(frame):
    from pyspark.sql import functions as F
    # All timestamps are local Korean wall-clock times, no UTC shift.
    base = frame.withColumn("start",F.try_to_timestamp("started_at")).withColumn("end",F.try_to_timestamp("ended_at"))
    day = F.date_format("start","yyyy-MM-dd")
    daily = base.groupBy("region_id",day.alias("date"),"origin_station_id","destination_station_id").agg(F.count("*").alias("trip_count"))
    hourly = base.groupBy("region_id",day.alias("date"),F.hour("start").alias("hour"),
                         "origin_station_id","destination_station_id").agg(F.count("*").alias("trip_count"))
    monthly = base.groupBy("region_id",F.date_format("start","yyyy-MM").alias("month"),F.hour("start").alias("hour"),
                         "origin_station_id","destination_station_id").agg(F.count("*").alias("trip_count"))
    rental = base.groupBy("region_id",day.alias("date"),F.hour("start").alias("hour"),
                         F.col("origin_station_id").alias("station_id")).agg(F.count("*").alias("rental_count"))
    returns = base.filter(F.col("end").isNotNull()).groupBy("region_id",
             F.date_format("end","yyyy-MM-dd").alias("date"),F.hour("end").alias("hour"),
             F.col("destination_station_id").alias("station_id")).agg(F.count("*").alias("return_count"))
    usage = rental.join(returns,["region_id","date","hour","station_id"],"full").fillna(0,subset=["rental_count","return_count"])
    return {"od_daily":daily.select("region_id","date","origin_station_id","destination_station_id","trip_count"),
            "od_hourly":hourly,"od_monthly_hourly":monthly,
            "station_usage":usage.select("region_id","station_id","date","hour","rental_count","return_count")}

def run(output, inputs=None, raw_zip=None, master="local[*]"):
    from pyspark import StorageLevel
    from pyspark.sql import functions as F
    output=Path(output).resolve()
    if output.exists():
        raise ValueError("기존 출력 보존: 존재하지 않는 새 --output 디렉토리를 사용하세요.")
    if bool(inputs) == bool(raw_zip):
        raise ValueError("--input 또는 --raw-zip 중 하나를 지정하세요.")
    spark=session(master)
    spark.sparkContext.setLogLevel("WARN")
    stats={"spark_version":spark.version,"master":spark.sparkContext.master,"input_mode":"raw_zip" if raw_zip else "normalized_trips"}
    try:
      with tempfile.TemporaryDirectory(prefix="bike-spark-input-") as tmp:
        if raw_zip:
            # Charset repair follows the existing collector's policy; only temporary copies.
            from scripts.preprocess.normalize import detect_encoding
            paths=[]
            with zipfile.ZipFile(raw_zip) as archive:
                for i,name in enumerate(archive.namelist()):
                    if not name.lower().endswith(".csv"):
                        continue
                    with archive.open(name) as f: sample=f.read(65536)
                    try: enc=detect_encoding(sample)
                    except ValueError:
                        try: sample.splitlines()[0].decode("utf-8-sig"); enc="utf-8-sig"
                        except UnicodeDecodeError: enc="cp949"
                    target=Path(tmp)/f"month-{i:03}.csv"
                    with archive.open(name) as source, target.open("w",encoding="utf-8",newline="") as dest:
                        with io.TextIOWrapper(source,encoding=enc,errors="replace",newline="") as text:
                            shutil.copyfileobj(text,dest,length=1024*1024)
                    paths.append(str(target))
            raw=spark.read.options(header=True,encoding="UTF-8",mode="FAILFAST",escape='"').csv(paths)
            raw=raw.persist(StorageLevel.DISK_ONLY)
            stats["raw_rows"]=raw.count()
            dedup=raw.dropDuplicates().persist(StorageLevel.DISK_ONLY)
            stats["deduplicated_rows"]=dedup.count()
            stats["duplicate_rows"]=stats["raw_rows"]-stats["deduplicated_rows"]
            admin=F.coalesce(F.col("대여_대여소명").contains("타슈관제센터"),F.lit(False))|F.coalesce(F.col("반납_대여소명").contains("타슈관제센터"),F.lit(False))
            stats["admin_rows"]=dedup.filter(admin).count()
            df=dedup.filter(~admin).select(F.lit("daejeon").alias("region_id"),
                F.trim(F.col("대여_대여소ID")).alias("origin_station_id"),
                F.trim(F.col("반납_대여소ID")).alias("destination_station_id"),
                F.col("대여일시").alias("started_at"),F.col("반납일시").alias("ended_at"),
                F.col("이용시간(분)").alias("duration_minutes"))
        else:
            paths=[str(p.resolve()) for pattern in inputs for p in sorted(Path().glob(pattern))] if all(not Path(p).is_absolute() for p in inputs) else inputs
            if not paths: raise ValueError("입력 Trip CSV 없음")
            df=spark.read.options(header=True,encoding="UTF-8",mode="FAILFAST",escape='"').csv(paths)
            stats["input_rows"]=df.count()
        start=F.try_to_timestamp("started_at");end=F.try_to_timestamp("ended_at")
        duration=F.expr("try_cast(duration_minutes as double)")
        valid=(start.isNotNull() & (F.col("ended_at").isNull() | end.isNotNull()) &
               (end.isNull() | (end>=start)) & (duration.isNull() | (duration>=0)) &
               F.col("origin_station_id").isNotNull() & (F.col("origin_station_id")!="") &
               F.col("destination_station_id").isNotNull() & (F.col("destination_station_id")!=""))
        valid_df=df.filter(valid).persist(StorageLevel.DISK_ONLY)
        stats["valid_rows"]=valid_df.count()
        stats["other_excluded_rows"]=(stats.get("deduplicated_rows",stats.get("input_rows"))-stats.get("admin_rows",0)-stats["valid_rows"])
        output.mkdir(parents=True)
        for name,result in aggregates(valid_df).items():
            result.write.mode("errorifexists").option("header",True).csv(str(output/name))
        (output/"run.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
        return stats
    finally:
        spark.stop()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",action="append")
    p.add_argument("--raw-zip")
    p.add_argument("--output",required=True)
    p.add_argument("--master",default="local[*]")
    args=p.parse_args()
    print(json.dumps(run(args.output,args.input,args.raw_zip,args.master),ensure_ascii=False))
