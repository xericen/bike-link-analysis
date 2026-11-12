"""Read-only SQLite reference comparison; Spark CSV partitions are streamed into a temporary DB."""
import argparse
import csv
import json
import sqlite3
import tempfile
from pathlib import Path

SCHEMAS={
 "od_daily": [("region_id","TEXT"),("date","TEXT"),("origin_station_id","TEXT"),("destination_station_id","TEXT"),("trip_count","INTEGER")],
 "station_usage":[("region_id","TEXT"),("station_id","TEXT"),("date","TEXT"),("hour","INTEGER"),("rental_count","INTEGER"),("return_count","INTEGER")],
 "od_hourly":[("region_id","TEXT"),("date","TEXT"),("hour","INTEGER"),("origin_station_id","TEXT"),("destination_station_id","TEXT"),("trip_count","INTEGER")],
 "od_monthly_hourly":[("region_id","TEXT"),("month","TEXT"),("hour","INTEGER"),("origin_station_id","TEXT"),("destination_station_id","TEXT"),("trip_count","INTEGER")],
}
def import_rows(connection,name,columns,paths):
    connection.execute("CREATE TABLE "+name+" ("+",".join(k+" "+t for k,t in columns)+")")
    n=0
    for path in paths:
      with Path(path).open(encoding="utf-8-sig",newline="") as f:
        batch=[]
        for row in csv.DictReader(f):
            batch.append(tuple(row[k] if row[k]!="" else None for k,_ in columns))
            if len(batch)>=50000:
                connection.executemany("INSERT INTO "+name+" VALUES ("+",".join("?" for _ in columns)+")",batch);n+=len(batch);batch=[]
        if batch:
            connection.executemany("INSERT INTO "+name+" VALUES ("+",".join("?" for _ in columns)+")",batch);n+=len(batch)
    connection.commit()
    return n

def difference(connection,a,b):
    return connection.execute("SELECT COUNT(*) FROM ("+a+" EXCEPT "+b+")").fetchone()[0]

def validate(output,reference,trips=None):
    output=Path(output)
    with tempfile.TemporaryDirectory(prefix="bike-spark-validate-") as temp:
      c=sqlite3.connect(str(Path(temp)/"comparison.sqlite"), uri=True)
      c.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=FILE; PRAGMA cache_size=-65536;")
      c.execute("ATTACH DATABASE ? AS original",(Path(reference).resolve().as_uri()+"?mode=ro",))
      rows={}
      for name,columns in SCHEMAS.items():
        rows[name]=import_rows(c,name,columns,sorted((output/name).glob("part-*.csv")))
      checks={}
      for name in ["od_daily","station_usage"]:
        fields=",".join(k for k,t in SCHEMAS[name])
        actual="SELECT "+fields+" FROM "+name
        expected="SELECT "+fields+" FROM original."+name+" WHERE region_id='daejeon'"
        checks[name]={"spark_minus_sqlite":difference(c,actual,expected),"sqlite_minus_spark":difference(c,expected,actual)}
      actual="SELECT region_id,substr(date,1,7),hour,origin_station_id,destination_station_id,SUM(trip_count) FROM od_hourly GROUP BY 1,2,3,4,5"
      expected="SELECT region_id,month,hour,origin_station_id,destination_station_id,trip_count FROM od_monthly_hourly"
      checks["monthly_from_hourly"]={"left_minus_right":difference(c,actual,expected),"right_minus_left":difference(c,expected,actual)}
      if trips:
        columns=[("region_id","TEXT"),("origin_station_id","TEXT"),("destination_station_id","TEXT"),("started_at","TEXT")]
        ref_rows=import_rows(c,"reference_trips",columns,sorted(Path(trips).glob("*.csv")))
        c.execute("""CREATE TABLE reference_hourly AS SELECT region_id,substr(started_at,1,10) date,
          CAST(substr(started_at,12,2) AS INTEGER) hour,origin_station_id,destination_station_id,COUNT(*) trip_count
          FROM reference_trips GROUP BY 1,2,3,4,5""")
        fields="region_id,date,hour,origin_station_id,destination_station_id,trip_count"
        actual="SELECT "+fields+" FROM od_hourly"
        expected="SELECT "+fields+" FROM reference_hourly"
        checks["hourly_from_python_sqlite_reference"]={"spark_minus_reference":difference(c,actual,expected),"reference_minus_spark":difference(c,expected,actual),"reference_trip_rows":ref_rows}
      total=c.execute("SELECT SUM(trip_count) FROM od_daily").fetchone()[0]
      period=c.execute("SELECT MIN(date),MAX(date) FROM od_daily").fetchone()
      passed=all(v==0 for check in checks.values() for k,v in check.items() if k!="reference_trip_rows")
      c.close()
    return {"passed":passed,"rows":rows,"trip_count":total,"date_start":period[0],"date_end":period[1],"checks":checks,
            "original_database_modified":False}
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--output",required=True)
 p.add_argument("--reference",default="data/processed/analysis.sqlite")
 p.add_argument("--reference-trips")
 p.add_argument("--report",required=True)
 a=p.parse_args()
 result=validate(a.output,a.reference,a.reference_trips)
 target=Path(a.report)
 if target.exists(): raise ValueError("기존 보고서 보존: 새 --report 경로 필요")
 target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(result,ensure_ascii=False))
 raise SystemExit(0 if result["passed"] else 1)
