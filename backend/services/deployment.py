"""Deployment readiness and available periods; reads never create a database."""
import sqlite3
from backend.services import precomputed

def available_periods(city):
    try:
        with sqlite3.connect(precomputed.path().resolve().as_uri()+"?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT start,end FROM kpi WHERE city=? AND revision=? "
                "GROUP BY start,end HAVING COUNT(DISTINCT action)=? ORDER BY start,end",
                (city, precomputed.revision(), len(precomputed.ACTIONS))).fetchall()
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
