"""Deployment readiness and available periods; reads never create a database."""
import sqlite3
from backend.services import precomputed

def available_periods(city):
    try:
        with sqlite3.connect(precomputed.path().resolve().as_uri()+"?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT start,end FROM kpi WHERE city=? AND revision=? "
                "AND action IN (" + ",".join("?" for _ in precomputed.ACTIONS) + ") "
                "GROUP BY start,end HAVING COUNT(DISTINCT action)=? ORDER BY start,end",
                (city, precomputed.revision(), *precomputed.ACTIONS, len(precomputed.ACTIONS))).fetchall()
    except sqlite3.OperationalError:
        rows = []
    return [{"start": start, "end": end} for start,end in rows]

def verify(combos):
    checked = 0
    for city,start,end in combos:
        for action in precomputed.ACTIONS:
            precomputed.read(action,city,start,end)
            checked += 1
    return checked

def readiness():
    from backend.services import periods
    cities={}
    for city in ("seoul","daejeon","sejong"):
        try:
            start,end=periods.resolve(city)
            missing=[]
            for action in precomputed.ACTIONS:
                try:precomputed.read(action,city,start,end)
                except precomputed.HTTPException:missing.append(action)
            cities[city]={"ready":not missing,"date_start":start,"date_end":end,"missing_actions":missing}
        except (ValueError,OSError,sqlite3.Error):
            cities[city]={"ready":False,"reason_code":"source_unavailable"}
    return {"ready":all(c["ready"] for c in cities.values()),"revision":precomputed.revision(),"cities":cities}
