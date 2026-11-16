"""Build transit-enriched master and true departure-hour OD linkage without changing originals."""
import argparse
import csv
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
import pandas as pd
from backend.services import real_data, transit
from scripts.preprocess.normalize_transit import write_new_csv
from scripts.preprocess.normalize import detect_encoding

def build_seoul_hourly(source, output):
    stations = transit.linkage("seoul")["stations"]
    known = {s["station_id"] for s in stations if s["coordinate_valid"]}
    near = {s["station_id"] for s in stations if s.get("subway_within_300m")}
    stats = {"raw_rows": 0, "departure_rows": 0, "duplicate_rows": 0, "invalid_rows": 0}
    with tempfile.TemporaryDirectory(prefix="bike-transit-") as tmp:
        connection = sqlite3.connect(str(Path(tmp) / "od.sqlite"))
        connection.executescript("""
            PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
            CREATE TABLE od(day TEXT,hour INTEGER,slot TEXT,origin TEXT,dest TEXT,n INTEGER,
                PRIMARY KEY(day,slot,origin,dest)) WITHOUT ROWID;
            CREATE TABLE stations(id TEXT PRIMARY KEY,near INTEGER);
        """)
        connection.executemany("INSERT INTO stations VALUES (?,?)", [(sid, int(sid in near)) for sid in known])
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                with archive.open(name) as f:
                    sample = f.read(65536)
                try:
                    enc = detect_encoding(sample)
                except ValueError:
                    try:
                        sample.splitlines()[0].decode("utf-8")
                        enc = "utf-8"
                    except UnicodeDecodeError:
                        enc = "cp949"
                with archive.open(name) as f:
                    for chunk in pd.read_csv(f, encoding=enc, encoding_errors="replace", dtype=str, chunksize=50000):
                        stats["raw_rows"] += len(chunk)
                        chosen = chunk[chunk["집계_기준"] == "출발시간"]
                        batch = []
                        for r in chosen.to_dict("records"):
                            try:
                                d = pd.Timestamp(str(r["기준_날짜"])).date().isoformat()
                                h, n = int(str(r["기준_시간대"])[:2]), int(r["전체_건수"])
                                a, b = str(r["시작_대여소_ID"]).strip(), str(r["종료_대여소_ID"]).strip()
                                if not 0 <= h <= 23 or n < 0 or a in {"nan", ""} or b in {"nan", ""}:
                                    raise ValueError()
                                batch.append((d,h,str(r["기준_시간대"]),a,b,n))
                            except (ValueError, TypeError):
                                stats["invalid_rows"] += 1
                        before = connection.total_changes
                        connection.executemany("INSERT OR IGNORE INTO od VALUES (?,?,?,?,?,?)", batch)
                        inserted = connection.total_changes - before
                        stats["duplicate_rows"] += len(batch) - inserted
                        stats["departure_rows"] += len(chosen)
                connection.commit()
        rows = [dict(zip(["date", "hour", "total_count", "linked_count", "unknown_endpoint_count"], r))
                for r in connection.execute("""
                    SELECT day,hour,SUM(n),
                      SUM(CASE WHEN a.near=1 OR b.near=1 THEN n ELSE 0 END),
                      SUM(CASE WHEN a.id IS NULL OR b.id IS NULL THEN n ELSE 0 END)
                    FROM od LEFT JOIN stations a ON origin=a.id LEFT JOIN stations b ON dest=b.id
                    GROUP BY day,hour ORDER BY day,hour
                """)]
        stats["trip_count"] = sum(r["total_count"] for r in rows)
        stats["linked_count"] = sum(r["linked_count"] for r in rows)
        stats["unknown_endpoint_count"] = sum(r["unknown_endpoint_count"] for r in rows)
        stats["hourly_rows"] = len(rows)
        connection.close()
    write_new_csv(output, rows, ["date", "hour", "total_count", "linked_count", "unknown_endpoint_count"])
    return stats


def build_daejeon_hourly(trips, output):
    from collections import Counter
    stations=transit.matched("daejeon")
    known={s["station_id"] for s in stations if s["coordinate_valid"]}
    near={s["station_id"] for s in stations if s.get("subway_within_300m")}
    totals=Counter();linked=Counter();unknown=Counter();n=0
    for path in sorted(Path(trips).glob("*.csv")):
        for chunk in pd.read_csv(path,dtype=str,chunksize=50000):
            n+=len(chunk)
            data=pd.DataFrame({"date":chunk.started_at.str[:10],"hour":chunk.started_at.str[11:13].astype(int),
                "linked":(chunk.origin_station_id.isin(near)|chunk.destination_station_id.isin(near)).astype(int),
                "unknown":(~chunk.origin_station_id.isin(known)|~chunk.destination_station_id.isin(known)).astype(int)})
            for (d,h),group in data.groupby(["date","hour"]):
                totals[d,int(h)]+=len(group);linked[d,int(h)]+=int(group.linked.sum());unknown[d,int(h)]+=int(group.unknown.sum())
    rows=[{"date":d,"hour":h,"total_count":v,"linked_count":linked[d,h],"unknown_endpoint_count":unknown[d,h]} for (d,h),v in sorted(totals.items())]
    write_new_csv(output,rows,["date","hour","total_count","linked_count","unknown_endpoint_count"])
    return {"trip_count":n,"linked_count":sum(linked.values()),"unknown_endpoint_count":sum(unknown.values()),"hourly_rows":len(rows)}
def build_current(seoul_zip=None,daejeon_trips=None):
    from scripts.preprocess.integrate_transit_uploads import replace_versioned
    import io
    archive=real_data.PROCESSED/"transit_archive"
    report={}
    for city,source,builder in [("seoul",seoul_zip,build_seoul_hourly),("daejeon",daejeon_trips,build_daejeon_hourly)]:
        if not source:continue
        with tempfile.TemporaryDirectory(prefix="bike-linkage-") as tmp:
            output=Path(tmp)/"hourly.csv"
            report[city]=builder(source,output)
            target=real_data.PROCESSED/f"transit_hourly_{city}_verified.csv"
            replace_versioned(target,output.read_bytes(),archive)
            replace_versioned(target.with_suffix(".meta.json"),json.dumps({"stops_sha256":transit.stops_digest(),
                "source":str(source),"stats":report[city]},ensure_ascii=False,indent=2),archive)
    stations=[row for city in ["seoul","daejeon","sejong"] for row in transit.matched(city)]
    if stations:
        buf=io.StringIO(newline="");fields=list(dict.fromkeys(k for r in stations for k in r))
        w=csv.DictWriter(buf,fieldnames=fields);w.writeheader();w.writerows(stations)
        replace_versioned(real_data.PROCESSED/"stations_transit.csv",buf.getvalue(),archive)
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--seoul-od");p.add_argument("--daejeon-trips");p.add_argument("--report")
    a=p.parse_args();result=build_current(a.seoul_od,a.daejeon_trips)
    if a.report:
        Path(a.report).parent.mkdir(parents=True,exist_ok=True)
        Path(a.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
