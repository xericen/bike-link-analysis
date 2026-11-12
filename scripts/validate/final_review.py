"""Recalculate final-review evidence using real normalized files only."""
import csv, json, sqlite3, time
from pathlib import Path
from backend.services import real_data as d, all_regions as a

OUT=Path("docs/final-validation")
OUT.mkdir(parents=True,exist_ok=True)
result={"run_date":"2026-11-12","kind":"actual normalized data","sql":{},"cases":{},"stability":{}}
def save():
    (OUT/"analysis.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
c=sqlite3.connect("file:"+str(d.database_path())+"?mode=ro",uri=True)
for rid in ("seoul","daejeon"):
    result["sql"][rid]={}
    for label,start,end in (("full",None,None),("common","2026-10-01","2026-10-31")):
        where="region_id=?";values=[rid]
        if start:where+=" AND date>=? AND date<=?";values += [start,end]
        row=c.execute("SELECT SUM(rental_count),COUNT(DISTINCT station_id),MIN(date),MAX(date),COUNT(DISTINCT date) FROM station_usage WHERE "+where+" AND rental_count>0",values).fetchone()
        result["sql"][rid][label]=dict(zip(("rentals","stations","start","end","observed_days"),row))
    save();print("SQL",rid,result["sql"][rid],flush=True)
assert result["sql"]["seoul"]["full"]["rentals"]==4245954
assert result["sql"]["daejeon"]["full"]["rentals"]==7605738
trip_count=0
for path in sorted((d.PROCESSED/"trips").glob("daejeon-*.csv")):
    with path.open(encoding="utf-8",newline="") as stream:
        trip_count+=sum(1 for _ in csv.DictReader(stream))
result["normalized_trip_csv_rows"]=trip_count
assert trip_count==7605738
result["unmatched_X"]=dict(zip(("trip_count","daily_od_rows"),c.execute("SELECT SUM(trip_count),COUNT(*) FROM od_daily WHERE region_id='seoul' AND (origin_station_id='X' OR destination_station_id='X')").fetchone()))
save()
for rid in ("seoul","daejeon"):
    t=time.perf_counter()
    value=d.cluster_stability(rid,"2026-10-31","2026-10-01")
    result["stability"][rid]=value
    save();print("stability",rid,round(time.perf_counter()-t,2),flush=True)
for sid in ("ST-1481","ST-3031","ST-2264"):
    t=time.perf_counter()
    validation=d.hidden_hub_validation("seoul",sid,"2026-10-31","2026-10-01")
    profile=next(p for p in d.profiles("seoul","2026-10-01","2026-10-31") if p["station_id"]==sid)
    flow=next(x for x in d.imbalance_result("seoul","2026-10-01","2026-10-31")["stations"] if x["station_id"]==sid)
    hourly=profile["hourly"]
    peak=hourly.index(max(hourly))
    result["cases"][sid]={"validation":validation,"profile":profile,
        "peak_hour":peak,"peak_share":max(hourly)/sum(hourly),"imbalance":flow}
    save();print("case",sid,round(time.perf_counter()-t,2),flush=True)
assert result["cases"]["ST-1481"]["validation"]["metrics"]["usage_rank"]==1640
assert result["cases"]["ST-1481"]["validation"]["metrics"]["pagerank_rank"]==280
assert result["cases"]["ST-3031"]["peak_hour"]==17
assert round(result["cases"]["ST-3031"]["peak_share"]*100,2)==40.91
assert result["cases"]["ST-2264"]["imbalance"]["net_outflow"]==-1582
unified=a.get("overview","2026-10-01","2026-10-31")
assert unified["total_rentals"]==sum(result["sql"][rid]["common"]["rentals"] for rid in ("seoul","daejeon"))==5169532
assert unified["station_count"]==sum(result["sql"][rid]["common"]["stations"] for rid in ("seoul","daejeon"))==4142
assert all(x["station_id"]!="X" for x in unified["map_stations"])
stations,edges=a.graph_data("2026-10-01","2026-10-31")
assert all(x.get("original_station_id")!="X" for x in stations)
assert all(x["origin_station_id"].split("::")[0]==x["destination_station_id"].split("::")[0] for x in edges)
assert all(not x["origin_station_id"].endswith("::X") and not x["destination_station_id"].endswith("::X") for x in edges)
network=a.get("network","2026-10-01","2026-10-31")
assert network["edge_count"]==len(edges)==600047
result["unified"]={k:unified[k] for k in ("total_rentals","station_count","period_start","period_end","annual_separate")}
result["unified"]["od_edge_count"]=len(edges)
result["checks_passed"]=True
for action in ("research","dashboard_extra","centrality"):
    t=time.perf_counter();a.get(action,"2026-10-01","2026-10-31")
    print("prepared",action,round(time.perf_counter()-t,2),flush=True)
save();print("VALIDATED",result["unified"],flush=True)
