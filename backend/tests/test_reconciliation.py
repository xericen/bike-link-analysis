from backend.analysis.network import centrality,PAGERANK_CONFIG
from backend.services.real_data import percentile
def test_full_precision_boundary_not_rounded_into_candidate():
 exact=452/4710;threshold=.09600433917917194
 assert exact<threshold
 assert round(exact,4)==.096
 assert round(exact,4)>=round(threshold,4)
 assert percentile([0,1,2,3],.25)==.75
def test_pagerank_reproducible_config_and_invalid_id_filter():
 stations=[{"station_id":x} for x in ["A","B","X"]]
 records=[{"origin_station_id":"A","destination_station_id":"B","trip_count":5},
 {"origin_station_id":"B","destination_station_id":"B","trip_count":2},
 {"origin_station_id":"A","destination_station_id":"X","trip_count":10}]
 a=centrality(stations,records);b=centrality(stations,records)
 assert a["rankings"]==b["rankings"]
 assert a["valid_graph_nodes"]==2 and a["valid_graph_edges"]==2
 assert a["valid_graph_trip_count"]==7
 assert a["pagerank_config"]["alpha"]==.85 and a["pagerank_config"]["tol"]==1e-6
 assert all(r["station_id"]!="X" for r in a["rankings"])
