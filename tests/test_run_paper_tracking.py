from __future__ import annotations

import json

from scripts.run_paper_tracking import _report_forecast_count, list_relevant_runs, load_cached_results_payload


class FakeResponse:
    def __init__(self, payload):
        self.content = json.dumps(payload).encode("utf-8")
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_cached_results_payload_includes_only_completed_matches_with_valid_ids(monkeypatch):
    payload = {
        "version": 1,
        "state": {"backfill_complete": True},
        "matches": [
            {
                "date": "2026-10-24", "home": "Alpha", "away": "Beta",
                "home_goals": 2, "away_goals": 1, "fixture_id": 123,
                "fixture_status": "FT",
            },
            {
                "date": "2026-10-24", "home": "Gamma", "away": "Delta",
                "home_goals": 0, "away_goals": 0, "fixture_id": None,
                "fixture_status": "FT",
            },
            {
                "date": "2026-10-24", "home": "Epsilon", "away": "Zeta",
                "home_goals": 1, "away_goals": 1, "fixture_id": 456,
                "fixture_status": "NS",
            },
        ],
    }
    monkeypatch.setattr(
        "scripts.run_paper_tracking.requests.get",
        lambda *args, **kwargs: FakeResponse(payload),
    )
    result, status = load_cached_results_payload("Nexora-Apparel/veltrix-football")
    assert status == "CACHE_AVAILABLE"
    assert result["response"] == [{
        "fixture": {"id": 123, "date": "2026-10-24", "status": {"short": "FT"}},
        "teams": {"home": {"name": "Alpha"}, "away": {"name": "Beta"}},
        "goals": {"home": 2, "away": 1},
    }]


def test_cached_results_payload_fails_closed_when_cache_is_unavailable(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("not available")

    monkeypatch.setattr("scripts.run_paper_tracking.requests.get", fail)
    result, status = load_cached_results_payload("Nexora-Apparel/veltrix-football")
    assert result == {"response": []}
    assert status == "CACHE_UNAVAILABLE"



def test_report_forecast_count_accepts_opaque_supplemental_ids():
    report = {
        "predictions": [
            {
                "fixture_id": "odds-event-abc123",
                "status": "EXPERIMENTAL_ONLY",
                "probabilities": {"H": 0.5, "D": 0.25, "A": 0.25},
            },
            {
                "fixture_id": None,
                "status": "EXPERIMENTAL_ONLY",
                "probabilities": {"H": 0.5, "D": 0.25, "A": 0.25},
            },
            {
                "fixture_id": "infer-event-xyz",
                "status": "UNSUPPORTED_COMPETITION",
                "probabilities": {},
            },
        ]
    }
    assert _report_forecast_count(report) == 1



def test_list_relevant_runs_includes_paper_recovery_workflow(monkeypatch):
    calls = []

    def fake_github_get(session, url):
        calls.append(url)
        if "paper-tracking-recovery.yml" in url:
            return {"workflow_runs": [{
                "id": 202, "created_at": "2026-10-31T14:00:00Z",
            }]}
        return {"workflow_runs": [{
            "id": 101, "created_at": "2026-10-30T08:00:00Z",
        }]}

    monkeypatch.setattr("scripts.run_paper_tracking.github_get", fake_github_get)
    runs = list_relevant_runs(object(), "owner/repo")
    assert [row["id"] for row in runs] == [202, 101]
    assert any("paper-tracking-recovery.yml" in url and "event=push" in url for url in calls)
    assert any("daily-fixture-predictions.yml" in url and "event=schedule" in url for url in calls)
