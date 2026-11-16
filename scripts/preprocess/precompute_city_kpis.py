"""Offline KPI materialization. Run after data refresh and before deployment."""
import argparse,json,time
from datetime import date,timedelta
from backend.services import precomputed,periods

def combinations():
    combos=set()
    for city in ("seoul","daejeon","sejong","all"):
        b=periods.bounds(city)
        if not b["available"]:continue
        start,end=b["min"],b["max"]
        combos.add((city,start,end))
        for days in (7,14,30):
            combos.add((city,max(start,(date.fromisoformat(end)-timedelta(days=days-1)).isoformat()),end))
    # Calendar months are useful in the 11-month Daejeon history.
    import calendar
    b=periods.bounds("daejeon")
    if b["available"]:
        cur=date.fromisoformat(b["min"]).replace(day=1)
        end=date.fromisoformat(b["max"])
        while cur<=end:
            last=cur.replace(day=calendar.monthrange(cur.year,cur.month)[1])
            combos.add(("daejeon",max(b["min"],cur.isoformat()),min(b["max"],last.isoformat())))
            cur=(last+timedelta(days=1))
    return sorted(combos)

def _run(combos,force=False,actions=None,version=None):
    from backend.services.kpi_projection import build
    version=version or precomputed.revision()
    stats=[]
    for city,start,end in combos:
        periods.resolve(city,start,end)
        for action in (actions or precomputed.ACTIONS):
            began=time.perf_counter()
            try:
                if force:raise LookupError
                precomputed.read(action,city,start,end,expected_revision=version)
                status="unchanged"
            except (LookupError,precomputed.HTTPException):
                value=build(action,city,start,end)
                if precomputed.revision()!=version:
                    raise RuntimeError("Data/code changed during preparation; rerun before serving this revision.")
                precomputed.put(action,city,start,end,value,expected_revision=version)
                status="built"
            row={"city":city,"start":start,"end":end,"action":action,"status":status,"seconds":round(time.perf_counter()-began,4)}
            stats.append(row);print(json.dumps(row),flush=True)
    return {"revision":version,"entries":stats}

def _worker(task):
    combo,force,actions,version=task
    return _run([combo],force,actions,version)["entries"]

def run(combos,force=False,actions=None,workers=1):
    from backend.services.input_manifest import verify
    version=verify(precomputed.PROCESSED,create=True)
    if workers==1:return _run(combos,force,actions,version)
    if not 1<=workers<=4:raise ValueError("workers must be1~4")
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers) as pool:
        batches=list(pool.map(_worker,[(combo,force,actions,version) for combo in combos]))
    return {"revision":version,"entries":[row for batch in batches for row in batch]}

if __name__=="__main__":
    p=argparse.ArgumentParser(__doc__);p.add_argument("--city",choices=("seoul","daejeon","sejong","all"))
    p.add_argument("--start");p.add_argument("--end");p.add_argument("--force",action="store_true")
    p.add_argument("--report",default="docs/transit/precomputed-build-20261116.json")
    p.add_argument("--workers",type=int,choices=range(1,5),default=1)
    p.add_argument("--actions",nargs="+",choices=precomputed.ACTIONS,help="Prepare only selected actions; default is all")
    a=p.parse_args()
    if a.city and bool(a.start)!=bool(a.end):p.error("--start and --end must be supplied together")
    combos=[(a.city,*periods.resolve(a.city,a.start,a.end))] if a.city else combinations()
    report=run(combos,a.force,a.actions,a.workers)
    from pathlib import Path
    Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2))
