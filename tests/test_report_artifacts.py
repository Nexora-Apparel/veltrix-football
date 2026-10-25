import io
import json

from app import report_artifacts


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.payload


def setup_function():
    report_artifacts._cache.clear()


def test_report_loader_reads_published_snapshot_without_github_api_or_forecast(monkeypatch):
    report = {"as_of_date": "2026-10-25", "predictions": [{"fixture_id": 1}]}
    requested = []

    def fake_urlopen(request, timeout):
        requested.append(request.full_url)
        return FakeResponse(json.dumps(report).encode())

    monkeypatch.setattr(report_artifacts, "urlopen", fake_urlopen)
    assert report_artifacts.load_latest_report() == report
    assert requested == [
        "https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/command-data/public-data/daily_predictions.json"
    ]
    assert not any("/actions/" in url or "dispatches" in url for url in requested)


def test_ledger_loader_accepts_only_paper_tracking_ledger(monkeypatch):
    ledger = {
        "product": "Veltrix Football",
        "model_status": "PAPER_TRACKING_ONLY",
        "cumulative_metrics_by_model": {"elo": {"matches": 4}},
    }
    monkeypatch.setattr(
        report_artifacts,
        "urlopen",
        lambda request, timeout: FakeResponse(json.dumps(ledger).encode()),
    )
    assert report_artifacts.load_paper_ledger() == ledger


def test_placeholder_report_is_not_treated_as_live_data(monkeypatch):
    placeholder = {"status": "NOT_YET_PUBLISHED", "predictions": []}
    monkeypatch.setattr(
        report_artifacts,
        "urlopen",
        lambda request, timeout: FakeResponse(json.dumps(placeholder).encode()),
    )
    assert report_artifacts.load_latest_report() is None


def test_missing_data_source_fails_closed(monkeypatch):
    def unavailable(request, timeout):
        raise OSError("network unavailable")

    monkeypatch.setattr(report_artifacts, "urlopen", unavailable)
    assert report_artifacts.load_latest_report() is None
    assert report_artifacts.load_paper_ledger() is None
