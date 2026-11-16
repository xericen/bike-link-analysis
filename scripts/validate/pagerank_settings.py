"""Reproduce settings and convergence sensitivity without recomputing sampled betweenness."""
import json
from pathlib import Path
import networkx as nx
from backend.services import real_data
from backend.analysis.network import build_graph,PAGERANK_CONFIG
if __name__=="__main__":
 records=real_data.aggregated_od("seoul","2026-10-01","2026-10-31")
 stations=[s for s in real_data.snapshot()["stations"] if s["region_id"]=="seoul" and s["station_id"].startswith("ST-") and s["latitude"] is not None]
 graph=build_graph(stations,records);results=[]
 for tol in [1e-6,1e-12]:
  scores=nx.pagerank(graph,alpha=.85,tol=tol,max_iter=100,weight="weight",nstart=dict.fromkeys(graph,1/len(graph)))
  ranking=sorted(graph,key=lambda sid:round(scores[sid],7),reverse=True)
  results.append({"tol":tol,"ST-1481_rank":ranking.index("ST-1481")+1,"top5":[{"station_id":sid,"score":scores[sid]} for sid in ranking[:5]]})
 report={"period_start":"2026-10-01","period_end":"2026-10-31","config":PAGERANK_CONFIG,
   "valid_nodes":len(graph),"valid_edges":graph.number_of_edges(),"valid_trip_count":sum(x["weight"] for _,_,x in graph.edges(data=True)),
   "all_od_pairs":len(records),"all_trip_count":sum(x["trip_count"] for x in records),"sensitivity":results}
 Path("docs/transit/pagerank-settings-20261116.json").write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
