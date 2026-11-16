"""Read-only deployment KPI store. Cache misses never execute analysis."""
import hashlib,json,sqlite3,zlib
from pathlib import Path
from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[2]
PROCESSED=ROOT/"data/processed"
ACTIONS=("overview","research","network","centrality","dashboard_extra","vulnerability","transit_linkage","planning")

def revision(processed=None):
    from backend.services.input_manifest import current
    return current(Path(processed or PROCESSED))

def path(processed=None):
    return Path(processed or PROCESSED)/"kpi_cache.sqlite"

def read(action,city,start,end,processed=None,expected_revision=None):
    if action not in ACTIONS:
        raise HTTPException(400,"지원하지 않는 사전 집계입니다.")
    db=path(processed)
    version=expected_revision or revision(processed)
    try:
        with sqlite3.connect(db.resolve().as_uri()+"?mode=ro",uri=True,timeout=2) as conn:
            row=conn.execute("SELECT payload,built_at FROM kpi WHERE city=? AND start=? AND end=? AND action=? AND revision=?",
                             (city,start or "",end or "",action,version)).fetchone()
    except sqlite3.OperationalError:
        row=None
    if row is None:
        raise HTTPException(409,"선택 도시·기간의 최신 사전 집계가 없습니다. 데이터 갱신 작업에서 precompute_city_kpis를 실행해야 합니다. 다른 기간의 수치로 대체하지 않습니다.")
    result=json.loads(zlib.decompress(row[0]))
    result["precomputed"]={"revision":version,"built_at":row[1],"date_start":start,"date_end":end,"read_only":True}
    return result

def put(action,city,start,end,payload,processed=None,expected_revision=None):
    from datetime import datetime,timezone
    db=path(processed);db.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS kpi(city TEXT,start TEXT,end TEXT,action TEXT,revision TEXT,payload BLOB,built_at TEXT,PRIMARY KEY(city,start,end,action))")
        conn.execute("INSERT OR REPLACE INTO kpi VALUES(?,?,?,?,?,?,?)",
            (city,start or "",end or "",action,expected_revision or revision(processed),
             zlib.compress(json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()),
             datetime.now(timezone.utc).isoformat()))
