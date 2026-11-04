import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.agents import solar
from backend.services import imports, real_data
from scripts.collect import common
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
    yield
    real_data.snapshot.cache_clear()
    real_data.clusters.cache_clear()
    real_data.network.cache_clear()
    real_data.centrality_result.cache_clear()


def test_real_api_and_empty_states(fixture_data):
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}
    regions = client.get("/api/regions").json()["regions"]
    assert [r["region_id"] for r in regions] == ["seoul", "daejeon", "sejong", "busan"]
    seoul = client.get("/api/regions/seoul/overview").json()
    assert seoul["total_rentals"] == 88
    assert seoul["station_count"] == 3
    assert seoul["observed_dates"] == ["2026-10-25", "2026-10-29"]
    filtered = client.get("/api/regions/seoul/overview?date_start=2026-10-29&date_end=2026-10-29").json()
    assert filtered["total_rentals"] == 53
    assert client.get("/api/regions/daejeon/overview").json()["total_rentals"] is None
    assert client.get("/api/regions/sejong/overview").json()["annual_latest"]["rental_count"] == 100
    assert client.get("/api/regions/busan/network").json()["message"] == "이동 경로 데이터 미확보"
    assert client.get("/api/regions/busan/clusters").json()["available"] is False
    assert client.get("/api/regions/unknown/overview").status_code == 404
    assert client.get("/api/compare?date_start=2026-10-29&date_end=2026-10-25").status_code == 400
    assert client.get("/api/demo/overview").json()["metadata"]["is_real"] is False


def test_algorithms_on_fixture(fixture_data):
    client = TestClient(app)
    groups = client.get("/api/regions/seoul/clusters").json()
    assert groups["available"] and len(groups["clusters"]) == 3
    assert groups["selected_k"] == 2 and groups["diagnostics"][0]["silhouette"] <= 1
    network = client.get("/api/regions/seoul/network").json()
    assert network["available"] and network["edge_count"] == 3
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
    result = solar.run_tool("get_data_availability", {"region_id": "busan"})
    assert result["total_rentals"] is None and result["has_od"] is False
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    response = TestClient(app).post("/api/agent/chat", json={"message": "부산 데이터로 가능한 분석은?"})
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
