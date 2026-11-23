"""Offline, independently testable MCLP / temporal uncertainty / typed claim scoring."""
import itertools, math, re, time
import numpy as np

def covered(selected, covers, weights):
    return float(sum(w for ids,w in zip(covers,weights) if set(selected).intersection(ids)))

def greedy(covers,weights,count,k):
    selected=[]
    for _ in range(min(k,count)):
        remaining=[j for j in range(count) if j not in selected]
        j=max(remaining,key=lambda j:(covered(selected+[j],covers,weights),-j))
        selected.append(j)
    return selected

def mclp(covers,weights,count,k,log_path,time_limit=45):
    import pulp
    if count<k or k<1 or len(covers)!=len(weights):raise ValueError("Invalid MCLP dimensions")
    if any(w<0 or not math.isfinite(w) for w in weights):raise ValueError("Nonnegative finite weights required")
    if any(any(j<0 or j>=count for j in ids) for ids in covers):raise ValueError("Invalid candidate index")
    model=pulp.LpProblem("BikeLinkMCLP",pulp.LpMaximize)
    x=pulp.LpVariable.dicts("site",range(count),cat="Binary")
    active=[i for i,(ids,w) in enumerate(zip(covers,weights)) if ids and w>0]
    y=pulp.LpVariable.dicts("covered",active,cat="Binary")
    scale=max(1.,max(weights,default=0))
    model+=pulp.lpSum((weights[i]/scale)*y[i] for i in active)
    model+=pulp.lpSum(x.values())==k
    for i in active:model+=y[i]<=pulp.lpSum(x[j] for j in covers[i])
    begun=time.perf_counter()
    model.solve(pulp.PULP_CBC_CMD(msg=False,timeLimit=time_limit,gapRel=0,threads=1,logPath=str(log_path),options=["randomSeed 42"]))
    text=log_path.read_text()
    selected=[j for j in range(count) if (x[j].value() or 0)>.5]
    # PuLP may label a time-limited feasible incumbent Optimal. Require CBC's actual proof.
    optimal="Result - Optimal solution found" in text or "Optimal solution found" in text
    feasible=len(selected)==k and model.sol_status in (pulp.LpSolutionOptimal,pulp.LpSolutionIntegerFeasible)
    bound=re.search(r"Upper bound:\s+([-+0-9.eE]+)",text)
    return {"selected":selected if feasible else [],"objective":covered(selected,covers,weights) if feasible else None,
            "status":pulp.LpStatus[model.status],"solution_status":pulp.LpSolution[model.sol_status],
            "proven_optimal":optimal and feasible,"upper_bound":float(bound.group(1))*scale if bound else (covered(selected,covers,weights) if optimal and feasible else None),
            "seconds":time.perf_counter()-begun,"time_limit":time_limit,"solver":"PuLP/CBC","gap_rel_requested":0}

def compare(covers,weights,count,k,log_path):
    solution=mclp(covers,weights,count,k,log_path)
    choices={"score":list(range(k)),"greedy":greedy(covers,weights,count,k),"mclp":solution["selected"]}
    optimum=solution["objective"] if solution["proven_optimal"] else None
    methods={name:{"indices":selected,"covered":covered(selected,covers,weights) if selected else None,
        "optimal_fraction":covered(selected,covers,weights)/optimum if selected and optimum else None} for name,selected in choices.items()}
    return {"k":k,"solver":solution,"methods":methods}

def block_ci(linked,total,replicates=2000,block=7,seed=42):
    linked=np.asarray(linked,dtype=float);total=np.asarray(total,dtype=float)
    if len(linked)!=len(total) or not len(total) or np.any(linked<0) or np.any(linked>total) or np.any(total<=0):
        raise ValueError("Paired nonempty daily counts required")
    rng=np.random.default_rng(seed);n=len(total);estimates=[]
    # Circular blocks preserve adjacent days and wrap the observed window; missing-day handling is disclosed by caller.
    for _ in range(replicates):
        starts=rng.integers(0,n,size=math.ceil(n/block))
        ix=((starts[:,None]+np.arange(block))%n).ravel()[:n]
        estimates.append(float(linked[ix].sum()/total[ix].sum()))
    lo,hi=np.quantile(estimates,[.025,.975])
    return {"estimate":float(linked.sum()/total.sum()),"lower":float(lo),"upper":float(hi),"level":.95,
            "block_days":block,"replicates":replicates,"seed":seed,"observed_days":n,
            "method":"circular moving-block bootstrap; ratio of resampled count sums"}

def typed_claims(claims,truth):
    """Truth is a field-keyed fact table; numeric coincidence elsewhere cannot validate a claim."""
    judged=[]
    for claim in claims:
        key=claim.get("field");fact=truth.get(key)
        valid=False
        if fact and claim.get("unit")==fact["unit"] and claim.get("period")==fact["period"]:
            a,b=claim.get("value"),fact["value"]
            valid=(type(a)==type(b) and a==b) if isinstance(b,str) else type(a) in (int,float) and math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6)
        judged.append({**claim,"supported":bool(valid)})
    n=len(judged)
    return {"claims":judged,"claim_count":n,"supported_count":sum(r["supported"] for r in judged),
        "grounded_claim_rate":sum(r["supported"] for r in judged)/n if n else None,
        "unsupported_count":sum(not r["supported"] for r in judged)}

def calendar_ci(dates,linked,total,replicates=2000,block=7,seed=42):
    """Month-stratified paired moving blocks. Never joins nonconsecutive dates."""
    from datetime import date
    dates=[date.fromisoformat(str(d)) for d in dates]
    linked=np.asarray(linked,dtype=float);total=np.asarray(total,dtype=float)
    if len(dates)!=len(total) or len(linked)!=len(total) or not dates or any(dates[i]>=dates[i+1] for i in range(len(dates)-1)):
        raise ValueError("Unique increasing dates required")
    if np.any(total<=0) or np.any(linked<0) or np.any(linked>total):raise ValueError("Invalid paired counts")
    strata={}
    for i,d in enumerate(dates):strata.setdefault((d.year,d.month),[]).append(i)
    groups=[]
    for ids in strata.values():
        width=min(block,len(ids))
        while width>0:
            starts=[j for j in range(len(ids)-width+1) if (dates[ids[j+width-1]]-dates[ids[j]]).days==width-1]
            if starts:break
            width-=1
        windows=np.array([ids[j:j+width] for j in starts])
        groups.append((windows,len(ids),width))
    rng=np.random.default_rng(seed);estimates=[]
    for _ in range(replicates):
        numerator=denominator=0.
        for windows,n,width in groups:
            ix=windows[rng.integers(0,len(windows),size=math.ceil(n/width))].ravel()[:n]
            numerator+=linked[ix].sum();denominator+=total[ix].sum()
        estimates.append(numerator/denominator)
    lo,hi=np.quantile(estimates,[.025,.975])
    return {"estimate":float(linked.sum()/total.sum()),"lower":float(lo),"upper":float(hi),"level":.95,
       "block_days":block,"actual_block_min":min(g[2] for g in groups),"replicates":replicates,"seed":seed,
       "observed_days":len(total),"month_strata":len(strata),
       "method":"month-stratified paired moving-block bootstrap; contiguous calendar windows; fixed observed-day counts per month"}
