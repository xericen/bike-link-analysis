"""Independent arithmetic, matching, holdout and input audit of saved results."""
import calendar
import json
from collections import Counter
from backend.research.recovery_evaluation import OUTPUT
from backend.research.method_validation import ROOT, sha

def audit(folder=OUTPUT):
    report=json.loads((folder/"results.json").read_text())
    rows=[]
    checks=0
    for city,c in report["cities"].items():
        assert json.loads((folder/(city+"-selection-lock.json")).read_text())==c["selection"]
        dev_ids={sid for f in c["development"] for sid in f["training_audit"]["hidden_ids"]}
        test_ids={sid for f in c["evaluation"] for sid in f["training_audit"]["hidden_ids"]}
        assert not dev_ids & test_ids
        for data in (c["development_data"],c["evaluation_data"]):
            year,month=map(int,data["start"][:7].split("-"))
            assert data["observed_days"]==calendar.monthrange(year,month)[1]
            assert sum(data["daily_trips"].values())==data["trips"]
        for phase in ("development","evaluation"):
            for fold in c[phase]:
                hidden=fold["training_audit"]
                assert hidden["source_od_trips"]==hidden["retained_od_trips"]+hidden["removed_od_trips"]
                assert hidden["hidden_station_count_in_training"]==0
                assert set(fold["target_ids"])<=set(hidden["hidden_ids"])
                for name,v in fold["configs"].items():
                    ids={r["station_id"] for r in v["target_diagnostics"]}
                    assert ids==set(fold["target_ids"])
                    assert v["generation_possible"]==sum(r["stage"]!="no_candidate" for r in v["target_diagnostics"])
                    for k,metric in v["at_k"].items():
                        pairs=metric["pairs"]
                        assert metric["hits"]==len(pairs)
                        assert len({r["station_id"] for r in pairs})==len(pairs)
                        assert len({r["site_id"] for r in pairs})==len(pairs)
                        assert all(r["distance_m"]<=300 and r["station_id"] in ids for r in pairs)
                        assert abs(metric["recall"]-len(pairs)/fold["target_count"])<1e-12
                        assert len(pairs)<=min(int(k),v["candidate_count"],fold["target_count"])
                        checks+=1
                if phase=="evaluation":
                    v=fold["configs"][c["selection"]["selected"]]
                    hits={r["station_id"] for r in v["at_k"]["10"]["pairs"]}
                    counts=Counter()
                    details=[]
                    for r in v["target_diagnostics"]:
                        stage=("matched" if r["station_id"] in hits else
                               "near_top10_but_one_to_one_conflict" if r["stage"]=="top10_nearby" else r["stage"])
                        counts[stage]+=1
                        details.append({**r,"joint_match_stage":stage})
                    assert sum(counts.values())==fold["target_count"]
                    rows.append({"city":city,"fold":fold["name"],"selected":c["selection"]["selected"],
                                 "n":fold["target_count"],"counts":dict(counts),"stations":details})
    manifest=json.loads((folder/"inputs.json").read_text())
    # Full code/reference hashes; 9GB databases were SHA256'd at build start and size/mtime checked at build end.
    for rel,value in manifest.items():
        p=ROOT/rel;stat=p.stat()
        assert (stat.st_size,stat.st_mtime_ns)==(value["size"],value["mtime_ns"])
        if p.suffix!=".sqlite":
            assert sha(p)==value["sha256"]
    result={"passed":True,"matching_metric_checks":checks,
            "all_input_metadata_unchanged":True,"small_input_sha256_matches":True,
            "no_development_evaluation_hidden_id_overlap":True,
            "same_fold_targets_can_share_candidate_neighborhood":True,"failure_stages":rows}
    target=folder/"audit.json"
    if target.exists():raise FileExistsError(target)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k!="failure_stages"},ensure_ascii=False))
    return result

if __name__=="__main__":audit()
