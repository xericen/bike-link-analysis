"""Build additional diagnostics without replacing the original failed experiment."""
import json,os,time
from datetime import datetime,timezone
from backend.research import method_validation as m, validation_followup as f
from backend.research.presentation import read

def build():
    original=read("all")
    dependencies=f.dependencies()
    result={"schema":1,"revision":original["revision"],"period_start":m.START,"period_end":m.END,
            "built_at":datetime.now(timezone.utc).isoformat(),"dependencies":dependencies,"cities":{}}
    for c in original["cities"]:
        city=c["city"];t=time.perf_counter()
        boundary,stations,facilities,districts,anchors,od=m.load_city(city)
        result["cities"][city]={"recurrence":f.recurrence(c["sensitivity"]),
            "gap_backtest":f.gap_backtest(boundary,stations,facilities,districts,anchors,od,city),
            "matrix_neighborhoods":f.neighborhoods(c["demand_matrix"],stations,city)}
        print(city,"completed",round(time.perf_counter()-t,3),flush=True)
    if dependencies!=f.dependencies():raise RuntimeError("Inputs changed during followup")
    temp=f.FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False));os.replace(temp,f.FILE)
    return result
if __name__=="__main__":build()
