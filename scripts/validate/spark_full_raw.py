"""Independent Spark raw ZIP normalization; immutable originals and production DBs."""
import argparse,hashlib,io,json,sqlite3,time,zipfile
from datetime import datetime,timezone
from pathlib import Path
from pyspark.sql import SparkSession,functions as F
from pyspark import StorageLevel
from scripts.preprocess.build_monthly_trends import source_members,sha
from backend.presentation.individual import scope
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/completion-20261123";WORK=Path("/tmp/bike-spark-full-raw-20261123")
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(".tmp");t.write_text(json.dumps(v,ensure_ascii=False,indent=2));t.replace(p)
def normalized(frame,city,start,end):
    columns=frame.columns
    frame=frame.select([F.trim(F.coalesce(F.col(c),F.lit(""))).alias(c) for c in columns])
    a,b=("대여시간","반납시간") if city=="sejong" else ("대여일시","반납일시")
    oc,dc={"seoul":("대여대여소ID","반납대여소ID"),"daejeon":("대여_대여소ID","반납_대여소ID"),"sejong":("시작 대여소","반납 대여소")}[city]
    dur="주행시간" if city=="sejong" else "이용시간(분)"
    x=frame.withColumn("_start",F.try_to_timestamp(F.col(a))).withColumn("_end",F.try_to_timestamp(F.col(b))).withColumn("_dur",F.expr("try_cast(`"+dur+"` as double)"))
    good=F.col("_start").isNotNull()&F.col("_end").isNotNull()&(F.col("_end")>=F.col("_start"))&(F.col("_dur").isNull()|F.isnan("_dur")|((F.col("_dur")>=0)&(F.abs(F.col("_dur"))!=float("inf"))))
    for c in (oc,dc):good=good&(~F.col(c).isin("","nan","None","null","\\N"))
    good=good&F.date_format("_start","yyyy-MM-dd").between(start,end)
    if city=="daejeon":good=good&(~F.col("대여_대여소명").contains("타슈관제센터"))&(~F.col("반납_대여소명").contains("타슈관제센터"))
    if city=="sejong":good=good&F.col("순번").isNotNull()&(F.col("순번")!="")
    valid=x.filter(good).withColumn("_month",F.date_format("_start","yyyy-MM"))
    if city=="sejong":
        # Conflicting duplicate IDs require investigation rather than nondeterministic choice.
        conflicts=valid.groupBy("_month","순번").agg(F.countDistinct(F.to_json(F.struct(*[F.col(c) for c in columns]))).alias("n")).filter("n>1").count()
        if conflicts:raise ValueError("conflicting Sejong source IDs: "+str(conflicts))
        dedup=valid.dropDuplicates(["_month","순번"])
    else:dedup=valid.dropDuplicates(columns)
    return valid,dedup.select(F.date_format("_start","yyyy-MM-dd").alias("date"),F.hour("_start").alias("hour"),
      F.date_format("_end","yyyy-MM-dd").alias("return_date"),F.hour("_end").alias("return_hour"),F.col(oc).alias("origin"),F.col(dc).alias("destination"))
def fingerprint_spark(frame,keys):
    text=F.concat_ws("\u001f",*[F.col(k).cast("string") for k in keys]);hashed=frame.withColumn("_hash",F.sha2(text,256))
    sums=[F.sum(F.conv(F.substring("_hash",i*16+1,16),16,10).cast("decimal(38,0)")).alias("h"+str(i)) for i in range(4)]
    r=hashed.agg(F.count("*").alias("rows"),F.sum("n").alias("trips"),*sums).first()
    return {"rows":r.rows,"trips":int(r.trips or 0),"sha256_limb_sums":[str(r["h"+str(i)] or 0) for i in range(4)]}
def fingerprint_sql(rows):
    total=0;count=0;sums=[0]*4
    for row in rows:
        h=hashlib.sha256("\u001f".join(str(x) for x in row).encode()).hexdigest()
        for i in range(4):sums[i]+=int(h[i*16:(i+1)*16],16)
        count+=1;total+=int(row[-1])
    return {"rows":count,"trips":total,"sha256_limb_sums":[str(x) for x in sums]}
def run(cities):
    WORK.mkdir(exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    spark=(SparkSession.builder.master("local[2]").appName("BikeLinkFullRaw")
      .config("spark.ui.enabled","false").config("spark.driver.memory","2g")
      .config("spark.driver.extraJavaOptions","-XX:ActiveProcessorCount=2")
      .config("spark.local.dir",str(WORK/"spark-temp")).config("spark.sql.shuffle.partitions","4")
      .config("spark.sql.session.timeZone","Asia/Seoul").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    try:
      for city in cities:
        begun=time.perf_counter();s=scope(city);parts=[];receipts=[]
        for path,name in source_members(city):
          with zipfile.ZipFile(path) as archive:
            key=hashlib.sha256(json.dumps([city,path.name,archive.getinfo(name).CRC,name,s["start"],s["end"],sha(Path(__file__))]).encode()).hexdigest()[:20]
            base=WORK/city/key;receipt=OUT/"raw-pieces"/(city+"-"+key+".json")
            if receipt.exists() and (base/"normalized").exists():
                receipts.append(json.loads(receipt.read_text()));parts.append(str(base/"normalized"));continue
            base.mkdir(parents=True,exist_ok=True);temp=base/"input.csv"
            with archive.open(name) as probe:header=probe.readline()
            try:header.decode("utf-8-sig");encoding="utf-8-sig"
            except UnicodeDecodeError:encoding="cp949"
            with archive.open(name) as raw,temp.open("w",encoding="utf-8",newline="") as dest:
                import shutil
                with io.TextIOWrapper(raw,encoding=encoding,errors="strict",newline="") as src:shutil.copyfileobj(src,dest,1024*1024)
          raw=spark.read.options(header=True,encoding="UTF-8",mode="FAILFAST",escape='"',nullValue="\u0000",multiLine=True).csv(str(temp)).persist(StorageLevel.DISK_ONLY)
          valid,df=normalized(raw,city,s["start"],s["end"])
          raw_count=raw.count();valid_count=valid.count()
          df=df.persist(StorageLevel.DISK_ONLY);valid_unique=df.count()
          df.write.mode("errorifexists").parquet(str(base/"normalized"));df.unpersist();raw.unpersist();temp.unlink()
          value={"city":city,"archive":path.name,"member":name,"member_crc":archive.getinfo(name).CRC,"encoding":encoding,
             "raw_rows":raw_count,"excluded_rows":raw_count-valid_count,"duplicate_rows":valid_count-valid_unique,"valid_rows":valid_unique}
          save(receipt,value);receipts.append(value);parts.append(str(base/"normalized"));print(city,len(parts),valid_unique,flush=True)
        df=spark.read.parquet(*parts)
        with sqlite3.connect((ROOT/"data/individual"/city/"analysis.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
          od=df.groupBy("date","origin","destination").agg(F.count("*").alias("n"))
          actual_od=fingerprint_spark(od,["date","origin","destination","n"])
          expected_od=fingerprint_sql(db.execute("SELECT date,origin_station_id,destination_station_id,trip_count FROM od_daily WHERE region_id=?",(city,)))
          rental=df.select(F.col("origin").alias("sid"),"date","hour",F.lit(1).alias("r"),F.lit(0).alias("b"))
          returns=df.filter(F.col("return_date").between(s["start"],s["end"])).select(F.col("destination").alias("sid"),F.col("return_date").alias("date"),F.col("return_hour").alias("hour"),F.lit(0).alias("r"),F.lit(1).alias("b"))
          usage=rental.unionByName(returns).groupBy("sid","date","hour").agg(F.sum("r").alias("r"),F.sum("b").alias("b")).withColumn("n",F.col("r")+F.col("b"))
          actual_usage=fingerprint_spark(usage,["sid","date","hour","r","b","n"])
          expected_usage=fingerprint_sql(db.execute("SELECT station_id,date,hour,rental_count,return_count,rental_count+return_count FROM station_usage WHERE region_id=?",(city,)))
        report={"city":city,"source_revision":s["revision"],"period_start":s["start"],"period_end":s["end"],"spark_version":spark.version,
          "raw_rows":sum(r["raw_rows"] for r in receipts),"valid_rows":sum(r["valid_rows"] for r in receipts),"members":len(receipts),
          "excluded_rows":sum(r["excluded_rows"] for r in receipts),"duplicate_rows":sum(r["duplicate_rows"] for r in receipts),
          "od":{"actual":actual_od,"expected":expected_od,"matches":actual_od==expected_od},
          "station_usage":{"actual":actual_usage,"expected":expected_usage,"matches":actual_usage==expected_usage},
          "seconds_including_extraction":time.perf_counter()-begun,"built_at":datetime.now(timezone.utc).isoformat(),
          "method":"Raw ZIP -> charset conversion only in Python -> Spark trim/filter/deduplicate -> full daily OD and hourly rental/return aggregates; compare key-count SHA256 four unsigned64-bit limb sums plus row/count totals.",
          "limitations":["현재 고정 정규화 규칙의 재현이며 과거 좌표·실제 환승·설치 효과 검증이 아닙니다.","단일 서버 local[2], 분산 클러스터 확장성 증명 아님.","해시 다중집합 검사는 충돌 확률이 극히 낮은 무순서 정합성 검사이며 바이트 단위 파일 동일성 주장은 아닙니다."]}
        save(OUT/("spark-raw-"+city+".json"),report)
        print("FINISHED",city,report["od"]["matches"],report["station_usage"]["matches"],flush=True)
    finally:spark.stop()
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--cities",nargs="+",default=["seoul","daejeon","sejong"]);run(p.parse_args().cities)
