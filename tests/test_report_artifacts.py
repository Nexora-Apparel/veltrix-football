import json
from urllib.parse import parse_qs, urlparse

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


def test_report_loader_reads_published_snapshot_from_raw_branch_without_forecast(monkeypatch):
    report = {"as_of_date": "2026-10-25", "predictions": [{"fixture_id": 1}]}
    requested = []

    def fake_urlopen(request, timeout):
        requested.append((request.full_url, timeout))
        return FakeResponse(json.dumps(report).encode())

    monkeypatch.setattr(report_artifacts, "urlopen", fake_urlopen)
    assert report_artifacts.load_latest_report() == report
    assert len(requested) == 1
    parsed_url = urlparse(requested[0][0])
    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "raw.githubusercontent.com"
    assert parsed_url.path == "/Nexora-Apparel/veltrix-football/command-data/public-data/daily_predictions.json"
    query = parse_qs(parsed_url.query)
    assert query.get("v", [""])[0].isdigit()
    assert requested[0][1] <= report_artifacts._REPORT_TIMEOUT_SECONDS
    assert not any("/actions/" in url for url, _ in requested)


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


def test_snapshot_loader_uses_short_contents_api_fallback_after_raw_failure(monkeypatch):
    from urllib.error import HTTPError

    report = {"as_of_date": "2026-11-03", "predictions": [{"fixture_id": 42}]}
    requested = []

    def fake_urlopen(request, timeout):
        requested.append((request.full_url, timeout))
        if len(requested) == 1:
            raise HTTPError(request.full_url, 503, "raw CDN unavailable", {}, None)
        return FakeResponse(json.dumps(report).encode())

    monkeypatch.setattr(report_artifacts, "urlopen", fake_urlopen)
    assert report_artifacts.load_latest_report() == report
    assert "raw.githubusercontent.com" in requested[0][0]
    assert "api.github.com" in requested[1][0]
    assert "ref=command-data" in requested[1][0]
    assert requested[1][1] == report_artifacts._API_FALLBACK_TIMEOUT_SECONDS


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


def test_model_validation_loader_accepts_only_published_research_diagnostic(monkeypatch):
    report = {
        "status": "RESEARCH_DIAGNOSTIC_ONLY",
        "dataset": {"valid_rows": 238854, "competition_count": 38},
        "historical_1x2": {"release_status": "NOT_CERTIFIED_MARKET_OUTPERFORMED_MODELS"},
    }
    requested = []

    def fake_urlopen(request, timeout):
        requested.append(request.full_url)
        return FakeResponse(json.dumps(report).encode())

    monkeypatch.setattr(report_artifacts, "urlopen", fake_urlopen)
    assert report_artifacts.load_model_validation_report() == report
    assert len(requested) == 1
    assert "raw.githubusercontent.com" in requested[0]
    assert requested[0].split("?")[0].endswith("/public-data/model_validation_report.json")


def test_model_validation_loader_rejects_unverified_snapshot(monkeypatch):
    invalid = {"status": "OK", "dataset": {"valid_rows": 100}}
    monkeypatch.setattr(
        report_artifacts,
        "urlopen",
        lambda request, timeout: FakeResponse(json.dumps(invalid).encode()),
    )
    assert report_artifacts.load_model_validation_report() is None
