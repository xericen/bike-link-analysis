"""Publish verified read-only experiment bundle/figures, never operational scores."""
import csv,hashlib,json,shutil,statistics
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/advanced-research-20261123"
def run():
    path=OUT/"results.json";value=json.loads(path.read_text())
    bench=json.loads((OUT/"benchmark.json").read_text());evaluation=json.loads((OUT/"agent-evaluation.json").read_text())
    assert bench["all_checksums_match"] and len(bench["runs"])==36
    assert value["common_all_ci"]["total_trips"]==2487201
    for scope,cities in value["scopes"].items():
        for city,c in cities.items():
            assert c["location"]["available"] and len(c["location"]["comparisons"])==6
            assert all(row["solver"]["proven_optimal"] for row in c["location"]["comparisons"])
            ci=c["headline_ci"];assert ci["lower"]<=ci["upper"] and 0<=ci["estimate"]<=1
            if scope=="individual":
                model=c["explanation"]
                note="도시 관측일의 대여소별 행 부재는 0 가정. 과거 개폐소일·대여소별 누락은 구분 못함."
                if note not in model["limitations"]:model["limitations"].append(note)
                assert model["train_end"]<model["test_start"] and len(model["station_ids"])==50
                fig,axes=plt.subplots(1,3,figsize=(13,4))
                importance=model["permutation_importance"][:6][::-1]
                axes[0].barh([r["feature"] for r in importance],[r["mae_increase"] for r in importance])
                axes[0].set_title("Held-out permutation importance");axes[0].set_xlabel("MAE increase (rentals/day)")
                for ax,curve in zip(axes[1:],model["partial_dependence"]):
                    ax.plot([p["x"] for p in curve["points"]],[p["mean_model_output"] for p in curve["points"]],marker="o")
                    ax.set(xlabel=curve["feature"],ylabel="Mean model output (rentals/day)",title="Partial dependence (association)")
                fig.suptitle(city+" "+c["period_start"]+" to "+c["period_end"]+"; fixed-reference covariates")
                fig.tight_layout();fig.savefig(OUT/("model-"+city+".png"),dpi=150);plt.close(fig)
    summary=[]
    cases=evaluation["live"].get("cases",[])
    for condition in ("baseline","grounded"):
        rows=[c["evaluation"] for c in cases if c["condition"]==condition]
        def avg(key):
            found=[r[key] for r in rows if r.get(key) is not None]
            return statistics.mean(found) if found else None
        summary.append({"condition":condition,"responses":len(rows),"answer_coverage":avg("answer_coverage"),
          "citation_rate":avg("citation_rate"),"numeric_match_rate":avg("numeric_match_rate"),
          "schema_field_match_rate":avg("schema_field_match_rate"),"strict_field_grounding":avg("grounded_claim_rate"),
          "unverified_separation_rate":avg("unverified_separation_rate")})
    value["benchmark"]={k:bench[k] for k in ("available","summary","spark_version","pandas_version","master","startup_seconds","warmup_seconds","all_checksums_match","limitations","pipeline")}
    value["agent_evaluation"]={"available":True,"live_calls":len(evaluation["live"].get("calls",[])),
       "replayed_responses":len(evaluation["replay"]["cases"]),"summary":summary,"limitations":evaluation["limitations"],
       "controlled_counterexamples":evaluation["controlled_counterexamples"]}
    value["export_code_sha256"]=hashlib.file_digest(Path(__file__).open("rb"),"sha256").hexdigest()
    value["bundle_artifact_hashes"]={name:hashlib.file_digest((OUT/name).open("rb"),"sha256").hexdigest() for name in ("benchmark.json","agent-evaluation.json")}
    with (OUT/"comparisons.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.writer(f);writer.writerow(["scope","city","start","end","objective","k","method","covered_objective","area_m2","nearby_rentals_unique","optimal_fraction","proven_optimal","reduced_candidates"])
        for scope,cities in value["scopes"].items():
            for city,packet in cities.items():
                for row in packet["location"]["comparisons"]:
                    for method,v in row["methods"].items():writer.writerow([scope,city,packet["period_start"],packet["period_end"],row["objective"],row["k"],method,v["covered"],v["gap_area_m2"],v["nearby_rentals_unique"],v["optimal_fraction"],row["solver"]["proven_optimal"],packet["location"]["reduced_candidates"]])
    tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2));tmp.replace(path)
    for dest in (ROOT/"frontend/public/assets/bike-link/advanced"):
        dest.mkdir(parents=True,exist_ok=True)
        for name in ("benchmark.png","model-seoul.png","model-daejeon.png","model-sejong.png"):shutil.copy2(OUT/name,dest/name)
    print(json.dumps({"scopes":6,"optimizations":36,"benchmark_runs":len(bench["runs"]),"agent":summary},ensure_ascii=False,indent=2))
if __name__=="__main__":run()
