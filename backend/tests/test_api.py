import shutil
import csv
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.agents import solar
from backend.services import imports, real_data
from scripts.collect import common
from scripts.preprocess import normalize
from scripts.preprocess.normalize import encoding


@pytest.fixture
def fixture_data(tmp_path, monkeypatch):
    source = Path(__file__).parent / "fixtures"
    for path in source.iterdir():
        shutil.copy2(path, tmp_path / path.name)
    monkeypatch.setattr(real_data, "PROCESSED", tmp_path)
    monkeypatch.setattr(imports, "UPLOADS", tmp_path / "uploads")
    real_data.snapshot.cache_clear()
    real_data.clusters.cache_clear()
    real_data.network.cache_clear()
    real_data.centrality_result.cache_clear()
    real_data.cluster_stability.cache_clear()
    real_data.imbalance_result.cache_clear()
    real_data.hidden_hubs.cache_clear()
    real_data.hidden_hub_validation.cache_clear()
    real_data.station_role_history.cache_clear()
    real_data.role_candidates.cache_clear()
    yield
    real_data.snapshot.cache_clear()
    real_data.clusters.cache_clear()
    real_data.network.cache_clear()
    real_data.centrality_result.cache_clear()
    real_data.cluster_stability.cache_clear()
    real_data.imbalance_result.cache_clear()
    real_data.hidden_hubs.cache_clear()
    real_data.hidden_hub_validation.cache_clear()
    real_data.station_role_history.cache_clear()
    real_data.role_candidates.cache_clear()


def test_real_api_and_empty_states(fixture_data):
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}
    regions = client.get("/api/regions").json()["regions"]
    assert [r["region_id"] for r in regions] == ["seoul", "daejeon", "sejong"]
    seoul = client.get("/api/regions/seoul/overview").json()
    assert seoul["total_rentals"] == 88
    assert seoul["station_count"] == 3
    assert seoul["observed_dates"] == ["2026-10-25", "2026-10-29"]
    filtered = client.get("/api/regions/seoul/overview?date_start=2026-10-29&date_end=2026-10-29").json()
    assert filtered["total_rentals"] == 53
    assert client.get("/api/regions/daejeon/overview").json()["total_rentals"] is None
    assert client.get("/api/regions/sejong/overview").json()["annual_latest"]["rental_count"] == 100
    assert client.get("/api/regions/busan/network").status_code == 404
    assert client.get("/api/regions/unknown/overview").status_code == 404
    assert client.get("/api/compare?date_start=2026-10-29&date_end=2026-10-25").status_code == 400
    assert client.get("/api/demo/overview").json()["metadata"]["is_real"] is False


def test_algorithms_on_fixture(fixture_data):
    client = TestClient(app)
    groups = client.get("/api/regions/seoul/clusters").json()
    assert groups["available"] and len(groups["clusters"]) == 3
    assert groups["selected_k"] == 2 and groups["diagnostics"][0]["silhouette"] <= 1
    assert {x["feature_set"] for x in groups["feature_comparisons"]} == {"time_share", "volume_only", "combined"}
    assert "interpretation_allowed" in groups
    network = client.get("/api/regions/seoul/network").json()
    assert network["available"] and network["edge_count"] == 3
    assert network["visible_edge_count"] == 3 and len(network["nodes"]) == 3
    limited = real_data.network("seoul", node_limit=2)
    assert len(limited["nodes"]) == 2
    assert all(edge["origin_station_id"] in {n["station_id"] for n in limited["nodes"]}
               and edge["destination_station_id"] in {n["station_id"] for n in limited["nodes"]}
               for edge in limited["edges"])
    assert client.get("/api/regions/seoul/network?node_limit=999").status_code == 400
    assert next(x["trip_count"] for x in network["edges"] if x["origin_station_id"] == "A" and x["destination_station_id"] == "B") == 12
    ranks = client.get("/api/regions/seoul/centrality").json()
    assert ranks["available"] and len(ranks["rankings"]) == 3
    assert all("weighted_in_degree" in x and "betweenness" in x for x in ranks["rankings"])
    similar = client.get("/api/regions/seoul/similarity?station_id=A").json()
    assert similar["available"] and len(similar["similar"]) == 2
    assert all(0 <= x["score"] <= 1 for x in similar["similar"])
    assert client.get("/api/regions/seoul/similarity?station_id=missing").status_code == 404
    comparison = client.get("/api/compare").json()
    assert comparison["regions"][1]["total_rentals"] is None
    assert comparison["same_observed_dates"] is False  # Only one region has station usage.
    aligned = client.get("/api/compare?region_ids=seoul,daejeon&align_common=true").json()
    assert "common_period" in aligned
    stability = client.get("/api/regions/seoul/cluster-stability?date_end=2026-10-29").json()
    assert stability["available"] and [x["days"] for x in stability["windows"]] == [7, 14, 30]
    assert all(x["common_station_count"] == 3 for x in stability["comparisons"])
    imbalance = client.get("/api/regions/seoul/imbalance").json()
    assert imbalance["available"] and imbalance["total"] == 3
    assert all("net_outflow" in x and "persistence_ratio" in x and "daily_net_outflow" in x
               and "weekday" in x and "weekend" in x and "low_volume_warning" in x for x in imbalance["stations"])
    assert imbalance["definition"].startswith("순유출 = 대여 - 반납")
    assert "selection_rule" in imbalance and all("imbalance_candidate" in x for x in imbalance["stations"])
    hidden = client.get("/api/regions/seoul/hidden-hubs").json()
    assert hidden["available"] and hidden["candidates"]
    assert all("usage_rank" in x and "rank_gap" in x and "top_connections" in x for x in hidden["candidates"])
    assert hidden["selection_rule"]["basis"].startswith("이용량 중앙값")
    history = client.get("/api/regions/seoul/stations/A/role-history?date_end=2026-10-29").json()
    assert history["available"] and [x["days"] for x in history["windows"]] == [7, 14, 30]
    assert "weighted_degree_rank_change" in history["role_change"]
    validation = client.get("/api/regions/seoul/stations/A/hidden-hub-validation?date_end=2026-10-29").json()
    assert validation["available"] and [x["days"] for x in validation["windows"]] == [7, 14, 30]
    assert len(validation["metrics"]["top_connections"]) <= 10
    assert "usage_percentile" in validation["metrics"] and "sensitivity" in validation
    roles = client.get("/api/regions/seoul/role-candidates").json()
    assert roles["available"] and {"low_usage_high_connectivity", "persistent_imbalance", "persistent_outflow",
        "persistent_inflow", "time_concentrated", "role_changed"} == set(roles["types"])


def test_local_upload_validation(fixture_data):
    client = TestClient(app)
    csv_bytes = b"region_id,station_id,station_name,latitude,longitude,capacity\ndaejeon,E,New,,,\n"
    result = client.post("/api/regions/daejeon/upload",
                         data={"kind": "stations", "dataset_name": "user test"},
                         files={"file": ("stations.csv", csv_bytes, "text/csv")})
    assert result.status_code == 200, result.text
    assert any(s["station_id"] == "E" for s in client.get("/api/regions/daejeon/stations").json()["stations"])
    bad = b"region_id,date,origin_station_id,destination_station_id,trip_count\ndaejeon,2026-10-25,E,Z,1\n"
    response = client.post("/api/regions/daejeon/upload",
                           data={"kind": "od_daily", "dataset_name": "bad"},
                           files={"file": ("od.csv", bad, "text/csv")})
    assert response.status_code == 400 and "존재하지 않는" in response.json()["detail"]


def test_encoding_and_duplicate_import(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "RAW", tmp_path / "raw")
    original = tmp_path / "source.csv"
    original.write_bytes("번호,대여소명\n1,타슈\n".encode("cp949"))
    assert encoding(original) == "cp949"
    source = {"source_id": "test", "region_id": "daejeon", "dataset_name": "fixture",
              "source_url": "https://www.data.go.kr/data/15062798/fileData.do", "filename": "copy.csv"}
    path = common.collect(source, str(original))
    first_hash = common.fingerprint(path)
    common.collect(source, str(original))
    assert common.fingerprint(path) == first_hash
    assert (tmp_path / "raw" / "manifest.json").exists()


def test_solar_uses_availability_and_missing_key(fixture_data, monkeypatch):
    result = solar.run_tool("get_data_availability", {"region_id": "sejong"})
    assert result["annual_latest"]["rental_count"] == 100 and result["has_od"] is False
    assert "error" in solar.run_tool("get_data_availability", {"region_id": "busan"})
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    response = TestClient(app).post("/api/agent/chat", json={"message": "세종 데이터로 가능한 분석은?"})
    assert response.status_code == 503


def test_openapi_collector_requires_key_and_uses_verified_path(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "RAW", tmp_path)
    source = {"source_id": "test-api", "region_id": "daejeon", "dataset_name": "fixture",
              "source_url": "https://www.data.go.kr/data/15062798/fileData.do",
              "api_path": "/15062798/v1/uddi:1b7e5971-a37d-4a80-ad0f-9aa12d1e2b87",
              "api_filename": "fixture-api.csv"}
    monkeypatch.delenv("DATA_GO_KR_API_KEY", raising=False)
    with pytest.raises(PermissionError):
        common.collect_openapi(source)
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "fixture-key")
    calls = []
    class FakeResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"data": [{"번호": "A", "대여소명": "테스트"}], "totalCount": 1}
    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, params):
            calls.append((url, params))
            return FakeResponse()
    monkeypatch.setattr(common.httpx, "Client", FakeClient)
    result = common.collect_openapi(source)
    assert result.exists() and "테스트" in result.read_text(encoding="utf-8")
    assert calls[0][0] == "https://api.odcloud.kr/api" + source["api_path"]
    assert calls[0][1]["serviceKey"] == "fixture-key"


def test_solar_tool_arguments_and_report_are_grounded(fixture_data):
    bad = solar.run_tool("get_centrality_ranking", {"region_id": "seoul", "metric": "made_up"})
    assert "error" in bad
    bad_date = solar.run_tool("get_region_overview", {"region_id": "seoul",
                                                      "date_range": {"date_start": "2026-10-29", "date_end": "2026-10-25"}})
    assert "error" in bad_date
    ranking = solar.run_tool("get_centrality_ranking", {"region_id": "seoul", "metric": "pagerank", "top_n": 2})
    assert ranking["available"] and len(ranking["rankings"]) == 2
    assert ranking["metric"] == "pagerank"
    assert ranking["rankings"][0]["centrality_rank"] == 1
    assert ranking["rankings"][0]["usage_rank"] is not None
    detail = solar.run_tool("get_station_details", {"region_id": "seoul", "station_id": "A"})
    assert detail["available"] and detail["station"]["station_id"] == "A"
    unavailable = solar.run_tool("get_centrality_ranking", {"region_id": "sejong", "metric": "pagerank"})
    assert unavailable["available"] is False and unavailable["rankings"] == []
    evidence = [{"tool": "get_centrality_ranking", "arguments": {"region_id": "seoul", "metric": "pagerank"},
                 "result": ranking}]
    report = solar._report("fixture question", "해석", evidence)
    assert report["charts"][0]["points"][0]["value"] == ranking["rankings"][0]["pagerank"]
    assert report["evidence"] == evidence
    grounded = solar._numeric_grounding("A 주소 257, 대여 88건", [{"result": {"name": "A 주소 257", "rentals": 88}}])
    assert grounded["passed"] is True and grounded["matched_numeric_tokens"] == 2
    assert solar._numeric_grounding("대여 999건", [{"result": {"rentals": 88}}])["passed"] is False
    assert solar.run_tool("get_station_imbalance", {"region_id": "seoul", "top_n": 2})["returned_count"] == 2
    assert solar.run_tool("get_hidden_hubs", {"region_id": "seoul", "top_n": 2})["returned_count"] == 2
    assert solar.run_tool("get_hidden_hub_validation", {"region_id": "seoul", "station_id": "A"})["available"] is True
    assert solar.run_tool("get_cluster_stability", {"region_id": "seoul"})["available"] is True
    assert solar.run_tool("get_station_role_history", {"region_id": "seoul", "station_id": "A"})["available"] is True
    assert solar.run_tool("get_role_candidates", {"region_id": "seoul"})["available"] is True


def test_daejeon_normalizer_streams_all_months_and_excludes_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "OUT", tmp_path / "processed")
    archive_path = tmp_path / "daejeon.zip"
    columns = ["자전거번호", "대여일시", "대여_대여소ID", "대여_대여소명", "대여_X좌표", "대여_Y좌표",
               "반납일시", "반납_대여소ID", "반납_대여소명", "반납_X좌표", "반납_Y좌표", "이용시간(분)"]
    rows = [
        ["B1", "2026-01-01 08:00:00", "A", "시청", "36.35", "127.38", "2026-01-01 08:10:00", "B", "역", "36.36", "127.39", "10"],
        ["B2", "2026-01-02 08:00:00", "A", "시청", "36.35", "127.38", "2026-01-02 07:50:00", "B", "역", "36.36", "127.39", "10"],
        ["B3", "2026-02-01 09:00:00", "A", "타슈관제센터", "36.35", "127.38", "2026-02-01 09:10:00", "B", "역", "36.36", "127.39", "10"],
    ]
    with zipfile.ZipFile(archive_path, "w") as archive:
        for month, selected in (("26년01월", rows[:2]), ("26년02월", rows[2:])):
            csv_path = tmp_path / f"{month}.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream); writer.writerow(columns); writer.writerows(selected)
            archive.write(csv_path, f"대전 타슈({month}).csv")
    stations = {("daejeon", "A"): {"region_id": "daejeon", "station_id": "A", "station_name": "시청", "latitude": None, "longitude": None, "capacity": None}}
    result = normalize.daejeon_trips(archive_path, stations, defaultdict(lambda: [0, 0]), Counter(), Counter())
    assert result["monthly_files"] == 2 and result["raw_rows"] == 3
    assert result["valid_rows"] == 1 and result["excluded_rows"] == 2
    assert result["invalid_time_rows"] == 1 and result["admin_return_rows"] == 1
    assert len(list((tmp_path / "processed" / "trips").glob("*.csv"))) == 2
