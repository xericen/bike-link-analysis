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

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seoul-od")
    args = p.parse_args()
    stations = []
    for city in ["seoul", "daejeon", "sejong"]:
        stations.extend(transit.linkage(city)["stations"])
    if stations:
        # Enrichment keeps all master rows for acquired cities. Other cities remain in original master.
        fields = list(dict.fromkeys(k for row in stations for k in row))
        clean = [{k: (json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in r.items()} for r in stations]
        write_new_csv(real_data.PROCESSED / "stations_transit.csv", clean, fields)
    if args.seoul_od:
        print(json.dumps(build_seoul_hourly(args.seoul_od, real_data.PROCESSED / "transit_hourly_seoul_verified.csv"), ensure_ascii=False))
