from collections import defaultdict
import networkx as nx


def build_graph(stations, od_records):
    graph = nx.DiGraph()
    for station in stations:
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


def centrality(stations, od_records):
    if not od_records:
        return {"available": False, "rankings": [], "components": None, "message": "이동 경로 데이터 미확보"}
    graph = build_graph(stations, od_records)
    if not graph.number_of_edges():
        return {"available": False, "rankings": [], "components": None, "message": "유효한 이동 경로 데이터 미확보"}
    rank = nx.pagerank(graph, weight="weight")
    # Betweenness uses inverse flow as distance, and sampling on large graphs.
    for _, _, attr in graph.edges(data=True):
        attr["distance"] = 1 / attr["weight"]
    samples = min(32, graph.number_of_nodes())
    between = nx.betweenness_centrality(graph, k=samples if samples < graph.number_of_nodes() else None,
                                         weight="distance", normalized=True, seed=42)
    weighted_out = dict(graph.out_degree(weight="weight"))
    weighted_in = dict(graph.in_degree(weight="weight"))
    rankings = sorted(({
        "station_id": node, "station_name": graph.nodes[node]["name"],
        "pagerank": round(rank[node], 7),
        "weighted_out_degree": int(weighted_out[node]), "weighted_in_degree": int(weighted_in[node]),
        "betweenness": round(between[node], 7),
    } for node in graph), key=lambda x: x["pagerank"], reverse=True)
    return {"available": True, "rankings": rankings,
            "components": nx.number_weakly_connected_components(graph),
            "betweenness_sample_nodes": samples,
            "message": "PageRank·가중 차수는 연결 구조 지표이며 실제 대여량과 다릅니다. 매개 중심성은 표본 근사입니다."}
