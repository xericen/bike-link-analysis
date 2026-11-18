"""Extract fixed, period-labelled inputs for an offline decision evidence study."""
import json
from pathlib import Path
from backend.services import precomputed,real_data
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"data/processed/research"
PERIODS={"seoul":("2025-12-01","2025-12-31"),"daejeon":("2025-12-01","2025-12-31"),"sejong":("2025-12-01","2025-12-31")}
def run():
    OUT.mkdir(exist_ok=True)
    result={"revision":precomputed.revision(),"cities":{}}
    for city,(start,end) in PERIODS.items():
        values={a:precomputed.read(a,city,start,end) for a in ("planning","vulnerability","transit_linkage","research","dashboard_extra")}
        plan=values["planning"];link=values["transit_linkage"]
        result["cities"][city]={"city":city,"period_start":start,"period_end":end,
            "new_top3":plan["new_sites"][:3],"candidate_count":values["vulnerability"]["candidate_count"],
            "ranking":values["vulnerability"]["ranking"][:10],"scenario_pool":plan["scenario_pool"],
            "selection_states":[{k:v for k,v in s.items() if k!="added_geometry"} for s in plan["selection_states"]],
            "sensitivity":plan["sensitivity"],"population_basis":plan["population_basis"],
            "assumptions":plan["assumptions"],"stations":link["stations"],"anchors":link["map_stops"],
            "goal_metrics":link["goal_metrics"],"research":values["research"],
            "cluster_quality":{k:values["dashboard_extra"].get(k) for k in ("selected_k","silhouette","quality")}}
    (OUT/"decision-inputs.json").write_text(json.dumps(result,ensure_ascii=False))
    print("Extracted three explicitly labelled research periods",result["revision"])
    return result
if __name__=="__main__":run()
