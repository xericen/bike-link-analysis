from fastapi.testclient import TestClient

from backend.main import app
from backend.agents.solar import run_tool
from backend.services import transit_demand


def test_verified_december_comparison_is_available():
    result = transit_demand.read("daejeon", "2025-12-01", "2025-12-31")
    assert result["available"] is True
    assert result["matched_station_names"] == 22
    assert result["transit_total"] == 6_587_252
    assert result["stations"][0]["station_name"] == "유성온천역"


def test_other_period_is_not_substituted():
    result = transit_demand.read("seoul", "2025-11-01", "2025-11-30")
    assert result["available"] is False
    assert "2025년 12월" in result["message"]


def test_sejong_is_explicitly_unavailable():
    result = transit_demand.read("sejong", "2025-12-01", "2025-12-31")
    assert result["available"] is False
    assert "BRT" in result["message"]


def test_api_returns_comparison():
    response = TestClient(app).get("/api/regions/daejeon/transit-demand?date_start=2025-12-01&date_end=2025-12-31")
    assert response.status_code == 200
    assert response.json()["matched_station_names"] == 22


def test_solar_tool_returns_bounded_verified_rows():
    result = run_tool("get_transit_demand_comparison", {
        "region_id": "seoul", "top_n": 3,
        "date_range": {"date_start": "2025-12-01", "date_end": "2025-12-31"},
    })
    assert result["available"] is True
    assert result["returned_count"] == 3
    assert len(result["stations"]) == 3
    assert "실제 환승" in result["global_limitations"][0]
