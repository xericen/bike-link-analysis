from collections import defaultdict
import networkx as nx

PAGERANK_ALPHA = 0.85
PAGERANK_TOL = 1e-6
PAGERANK_MAX_ITER = 100
PAGERANK_WEIGHT = "weight"
PAGERANK_DISPLAY_DECIMALS = 7
PAGERANK_CONFIG = {"directed": True, "alpha":PAGERANK_ALPHA, "tol":PAGERANK_TOL,
 "max_iter":PAGERANK_MAX_ITER,"weight":PAGERANK_WEIGHT,"self_loops":True,
 "teleportation":"uniform","dangling":"uniform","initial_vector":"uniform",
 "ranking_precision_decimals":PAGERANK_DISPLAY_DECIMALS,
 "tie_breaker":"stable station input order after seven-decimal score rounding",
 "edge_filter":"both endpoints in supplied station master; exclude X; positive trip_count only"}


def build_graph(stations, od_records):
    graph = nx.DiGraph()
    for station in stations:
        if station["station_id"] == "X": continue
        graph.add_node(station["station_id"], name=station.get("station_name") or station["station_id"])
    valid = set(graph)
    for item in od_records:
        origin, destination = item["origin_station_id"], item["destination_station_id"]
        weight = int(item["trip_count"])
        if origin not in valid or destination not in valid or weight <= 0:
            continue
        if graph.has_edge(origin, destination):
            graph[origin][destination]["weight"] += weight
        else:
            graph.add_edge(origin, destination, weight=weight)
    return graph


def centrality(stations, od_records, include_betweenness=True):
    if not od_records:
        return {"available": False, "rankings": [], "components": None, "message": "이동 경로 데이터 미확보"}
    graph = build_graph(stations, od_records)
    if not graph.number_of_edges():
        return {"available": False, "rankings": [], "components": None, "message": "유효한 이동 경로 데이터 미확보"}
    rank = nx.pagerank(graph, alpha=PAGERANK_ALPHA, tol=PAGERANK_TOL,
                       max_iter=PAGERANK_MAX_ITER, weight=PAGERANK_WEIGHT,
                       nstart=dict.fromkeys(graph,1/graph.number_of_nodes()))
    # Betweenness uses inverse flow as distance, and sampling on large graphs. Period sensitivity
    # can skip this expensive approximation because it compares PageRank only.
    samples = min(32, graph.number_of_nodes()) if include_betweenness else 0
    if include_betweenness:
        for _, _, attr in graph.edges(data=True):
            attr["distance"] = 1 / attr["weight"]
        between = nx.betweenness_centrality(graph, k=samples if samples < graph.number_of_nodes() else None,
                                             weight="distance", normalized=True, seed=42)
    else:
        between = dict.fromkeys(graph, 0.0)
    weighted_out = dict(graph.out_degree(weight="weight"))
    weighted_in = dict(graph.in_degree(weight="weight"))
    rankings = sorted(({
        "station_id": node, "station_name": graph.nodes[node]["name"],
        "pagerank": round(rank[node], PAGERANK_DISPLAY_DECIMALS),
        "weighted_out_degree": int(weighted_out[node]), "weighted_in_degree": int(weighted_in[node]),
        "betweenness": round(between[node], 7),
    } for node in graph), key=lambda x: x["pagerank"], reverse=True)
    return {"available": True, "rankings": rankings, "pagerank_config":dict(PAGERANK_CONFIG),
            "valid_graph_nodes":graph.number_of_nodes(),"valid_graph_edges":graph.number_of_edges(),
            "valid_graph_trip_count":sum(d["weight"] for _,_,d in graph.edges(data=True)),
            "components": nx.number_weakly_connected_components(graph),
            "betweenness_sample_nodes": samples,
            "message": "PageRank·가중 차수는 연결 구조 지표이며 실제 대여량과 다릅니다. 매개 중심성은 표본 근사입니다."}
