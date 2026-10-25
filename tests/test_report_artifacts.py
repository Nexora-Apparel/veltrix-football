from app import report_artifacts


def setup_function():
    report_artifacts._cache.clear()


def test_report_loader_reads_existing_artifact_without_forecast_generation(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "Nexora-Apparel/veltrix-football")
    calls = []

    def fake_json(url, token):
        calls.append(url)
        if url.endswith("/actions/runs?branch=main&status=success&per_page=12"):
            return {"workflow_runs": [{"id": 123}]}
        return {"artifacts": [
            {"id": 7, "name": "veltrix-daily-predictions", "expired": False}
        ]}

    report = {"as_of_date": "2026-10-25", "predictions": [{"fixture_id": 1}]}
    monkeypatch.setattr(report_artifacts, "_request_json", fake_json)
    monkeypatch.setattr(report_artifacts, "_read_artifact", lambda repo, token, artifact_id: report)

    assert report_artifacts.load_latest_report() == report
    assert any("/actions/runs?" in url for url in calls)
    assert not any("dispatches" in url for url in calls)


def test_ledger_loader_requires_cumulative_model_metrics(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "Nexora-Apparel/veltrix-football")

    def fake_json(url, token):
        if "/actions/runs?" in url:
            return {"workflow_runs": [{"id": 456}]}
        return {"artifacts": [
            {"id": 8, "name": "veltrix-paper-ledger", "expired": False}
        ]}

    ledger = {"cumulative_metrics_by_model": {"elo": {"matches": 4}}}
    monkeypatch.setattr(report_artifacts, "_request_json", fake_json)
    monkeypatch.setattr(report_artifacts, "_read_artifact", lambda repo, token, artifact_id: ledger)

    assert report_artifacts.load_paper_ledger() == ledger


def test_artifact_loader_fails_closed_when_token_is_missing(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "Nexora-Apparel/veltrix-football")

    assert report_artifacts.load_latest_report() is None
    assert report_artifacts.load_paper_ledger() is None
