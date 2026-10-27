from fastapi.testclient import TestClient

from api.dashboard import app as dashboard_app
from api.dashboard_data import app as dashboard_data_app


def test_dashboard_root_returns_html():
    response = TestClient(dashboard_app).get("/")
    assert response.status_code == 200
    assert "VELTRIX FOOTBALL" in response.text
    assert "Command Centre" in response.text


def test_dashboard_data_alias_returns_json(monkeypatch):
    import api.telegram

    monkeypatch.setattr(api.telegram, "load_latest_report", lambda: {
        "as_of_date": "2026-10-27",
        "generated_at_utc": "2026-10-27T04:00:00+00:00",
        "predictions": [],
        "fixtures_received": 0,
        "fixtures_with_market_odds": 0,
    })
    response = TestClient(dashboard_data_app).get("/api/dashboard-data")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["as_of_date"] == "2026-10-27"
    assert payload["predictions"] == []
