"""Frozen broad-search experiment; archived December exploration plus locked August check."""
import json,time
from datetime import datetime,timezone
from backend.research import recovery_breadth as b, recovery_evaluation as e, method_validation as m

def save(path,value):
    if path.exists():raise FileExistsError("Do not overwrite evidence: "+str(path))
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))

def manifest():
    prior=json.loads((e.OUTPUT/"inputs.json").read_text())
    inputs={}
    for rel,stamp in prior.items():
        path=m.ROOT/rel;stat=path.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(stamp["size"],stamp["mtime_ns"]):
            raise RuntimeError("Prior audited input changed: "+rel)
        if path.suffix!=".sqlite" and m.sha(path)!=stamp["sha256"]:
            raise RuntimeError("Prior source changed: "+rel)
        inputs[rel]=stamp
    for path in (m.ROOT/"backend/research/recovery_breadth.py",m.ROOT/"scripts/validate/build_recovery_breadth.py"):
        st=path.stat();inputs[str(path.relative_to(m.ROOT))]={"size":st.st_size,"mtime_ns":st.st_mtime_ns,"sha256":m.sha(path)}
    return inputs

def run():
    out=b.OUT
    protocol={"created_at":datetime.now(timezone.utc).isoformat(),
              "development":["2025-12-01","2025-12-21"],"exploration":["2025-12-01","2025-12-31"],
              "evaluation":["2025-08-01","2025-08-31"],"configs":b.CONFIGS,
              "selection":"December1-21 macro Recall@10 over popular/gap/spatial folds; strict and spacing50 tracks selected separately; tie order declared config list",
              "candidate_rules":{"strict_min_remaining_station_m":300,"diagnostic_min_remaining_station_m":50,
                                  "lattice_m":[125,250],"legacy_grid_m":500,"matching_radius_m":300,
                                  "top_k":[10,20],"candidate_inputs":"Remaining station demand, static anchors/facilities/boundary only; no hidden coordinate as candidate"},
              "purpose":"December already examined: all December outcomes exploratory. August is locked cross-month retrospective check, not future prediction; prior project descriptive use of August is acknowledged.",
              "limitations":["50m spacing is a recovery/coverage diagnostic, not compliant new-station installation.",
                             "Coverage500 counts remaining observed rental+return activity once, not unmet demand or causal installation effect.",
                             "Reference infrastructure snapshots are newer than observation month; historical location validity unverified.",
                             "Do not select a winning August method or replace existing production scores."]}
    save(out/"protocol.json",protocol)
    inputs=manifest();save(out/"inputs.json",inputs)
    original=json.loads(m.FILE.read_text())
    result={"protocol":protocol,"cities":{}}
    for city in m.CITIES:
        began=time.perf_counter()
        dev=e.load(city,*protocol["development"])
        specs=b.specifications(dev,"development")
        development=[]
        for spec in specs:
            print(city,"development",spec["name"],len(spec["targets"]),flush=True)
            development.append(b.fold(city,dev,spec))
        strict,strict_scores=b.select(development,b.STRICT)
        diagnostic,diagnostic_scores=b.select(development,b.DIAGNOSTIC)
        lock={"city":city,"strict":strict,"diagnostic":diagnostic,"strict_scores":strict_scores,
              "diagnostic_scores":diagnostic_scores,"locked_at":datetime.now(timezone.utc).isoformat()}
        save(out/(city+"-selection-lock.json"),lock)
        full=e.load(city,*protocol["exploration"])
        high=b.high_spec(full[1],full[0])
        target=next(r for r in original["cities"][city]["backtest"] if r["fold"]=="high_usage")
        lookup={s["station_id"]:s for s in full[1]}
        selected=[lookup[s["station_id"]] for s in target["targets"]]
        for observed,s in zip(target["targets"],selected):
            assert observed["rental_count"]==s["rental_count"],(city,"target demand mismatch")
            assert abs(observed["latitude"]-s["latitude"])<1e-8 and abs(observed["longitude"]-s["longitude"])<1e-8,(city,"location mismatch")
        assert full[-1]["trips"]==target["training_audit"]["source_od_trips"]
        full_specs=b.specifications(full,"development")
        full_specs[0]={"name":"original_popular10","targets":selected,"hidden_ids":[s["station_id"] for s in selected]}
        exploration=[]
        for spec in full_specs:
            print(city,"December exploration",spec["name"],len(spec["targets"]),flush=True)
            exploration.append(b.fold(city,full,spec))
        baseline=exploration[0]["methods"]["legacy500:original"]["matches"]["10"]["hits"]
        assert baseline==target["methods"]["full"]["hits"],(city,"original baseline drift")
        # Exclude any target previously used for development or full-December exploration.
        hidden={sid for f in specs+full_specs for sid in f["hidden_ids"]}
        block=next((f["block"] for f in specs if f["name"]=="spatial_block"),None)
        test=e.load(city,*protocol["evaluation"])
        test_specs=b.specifications(test,"evaluation",hidden,block)
        assert not hidden.intersection(sid for f in test_specs for sid in f["hidden_ids"])
        evaluation=[]
        keys=list(dict.fromkeys(["legacy500:original",strict,diagnostic]))
        for spec in test_specs:
            print(city,"August locked",spec["name"],"strict",strict,"diagnostic",diagnostic,flush=True)
            evaluation.append(b.fold(city,test,spec,keys))
        value={"development_info":dev[-1],"exploration_info":full[-1],"evaluation_info":test[-1],
               "development":development,"exploration":exploration,"evaluation":evaluation,
               "selection":lock,"seconds":time.perf_counter()-began}
        save(out/(city+".json"),value);result["cities"][city]=value
        print(city,"done",round(value["seconds"],2),flush=True)
    for rel,stamp in inputs.items():
        p=m.ROOT/rel;st=p.stat()
        assert (st.st_size,st.st_mtime_ns)==(stamp["size"],stamp["mtime_ns"]),("input changed",rel)
    result["input_metadata_unchanged"]=True
    save(out/"results.json",result)
    tables(result)
    return result

def tables(result):
    lines=["# 多方法 후보 재발견 실험","",
           "서비스 기준은2025년12월. 아래12월최고값은이미결과를본자료의탐색값이며정확도검증성공이아니다.",
           "300m간격유지와50m진단을분리한다.50m진단은신규설치추천이아니다.","",
           "|도시|기존12월|300m간격유지 탐색최고|방법|50m진단 탐색최고|방법|",
           "|---|---:|---:|---|---:|---|"]
    for city,c in result["cities"].items():
        f=c["exploration"][0]
        best=lambda keys:max(keys,key=lambda k:f["methods"][k]["matches"]["10"]["hits"])
        a,d=best(b.STRICT),best(b.DIAGNOSTIC)
        lines.append(f"|{city}|{f['methods']['legacy500:original']['matches']['10']['hits']}/10|{f['methods'][a]['matches']['10']['hits']}/10|{a}|{f['methods'][d]['matches']['10']['hits']}/10|{d}|")
    lines+=["","## 方法锁定后8月评估","",
            "8月在方法锁定后加载。排除了开发/12月探索使用过的隐藏ID，地域块距离开发块至少2km。是回顾性跨月检查，不是前瞻预测。","",
            "|도시|대상|N|기존방법|잠금300m방법|잠금50m진단|",
            "|---|---|---:|---:|---:|---:|"]
    for city,c in result["cities"].items():
        for f in c["evaluation"]:
            hits=lambda k:f["methods"][k]["matches"]["10"]["hits"]
            lines.append(f"|{city}|{f['name']}|{f['target_count']}|{hits('legacy500:original')}|{hits(c['selection']['strict'])}|{hits(c['selection']['diagnostic'])}|")
    lines+=["","## 全46种预设组合",
            "legacy500原始1种+5候选池×9种排序/组合选择。每池另有30次随机比较，未用随机成绩挑方法。",
            "rental1000=周围1km保留租赁总量，activity500=500m租赁+归还，kde300=核平滑租赁强度，facilities500=设施数。",
            "balanced=KDE/设施/锚点距离分位平均，anchor_demand=锚点邻近权重×KDE分位。",
            "diverse300/600=KDE排序并限制新候选间距，cover500=贪心最大化500m内未被此前选中候选计入的保留活动量。",
            "候选池为原规则500m格网、250m格点、125m多点、50m间距诊断125m格点、附加真实公共设施点的50m诊断。",
            "所有隐藏ID及其出发/到达OD都被移除。隐藏位置仅供最终300m一对一评价。未改变匹配半径来提高成绩。",
            "详细JSON保留所有组合/三类目标/生成可能数/一对一匹配/源OD剔除审计/随机比较。没有覆盖的需求不得当作已知零需求。",
            "安装可行性/真实换乘/再平衡效果仍未验证。观察位置恢复不等于证明应当在该处新设站点。"]
    (b.OUT/"RESULTS.md").write_text("\n".join(lines)+"\n")

if __name__=="__main__":run()
