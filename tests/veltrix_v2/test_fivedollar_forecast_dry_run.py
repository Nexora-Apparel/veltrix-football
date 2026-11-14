import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from scripts.veltrix_v2.fivedollar_forecast_dry_run import (
    REQUEST_BUDGET,
    run_forecast_probe,
    validate_report,
)
from scripts.phase2_fivedollar_history_dry_run import EXPECTED_COMPETITIONS

UTC = timezone.utc
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _fixture(i, competition_id, kickoff, status):
    return {
        "id": 900000 + i,
        "league": {"id": int(competition_id), "name": EXPECTED_COMPETITIONS[competition_id]},
        "teams": {
            "home": {"id": 101, "name": "Alpha FC"},
            "away": {"id": 102, "name": "Beta FC"},
        },
        "kickoff_utc": kickoff.isoformat(),
        "kickoff_ts": int(kickoff.timestamp()),
        "status": status,
        "status_reason": None,
        "status_code": "full" if status == "finished" else "scheduled",
        "goals": {"home": 2 if i % 2 == 0 else 1, "away": 1 if i % 3 == 0 else 0}
            if status == "finished" else None,
    }


def _response(data, *, page=1, per_page=100, has_more=False):
    return json.dumps({
        "success": True, "data": data,
        "pagination": {"page": page, "per_page": per_page, "count": len(data), "has_more": has_more},
    }).encode()


def test_read_only_forecast_probe_fetches_free_data_and_calculates_one_locked_batch():
    calls = []
    history = [
        _fixture(i, "4160026622", NOW - timedelta(hours=120 + i * 18), "finished")
        for i in range(100)
    ]
    upcoming = [
        _fixture(1000, "4160026622", NOW + timedelta(hours=5), "scheduled"),
        _fixture(1001, "4160026622", NOW + timedelta(days=20), "scheduled"),
    ]

    def request(path, api_key):
        calls.append(path)
        headers = {"X-RateLimit-Remaining": str(100 - len(calls))}
        if path == "/status":
            return 200, json.dumps({
                "success": True,
                "data": {"plan": "community", "limits": {"rate_limit": 60, "burst_per_minute": 20}},
            }).encode(), headers
        if path == "/leagues":
            rows = [{"id": int(cid), "name": name} for cid, name in EXPECTED_COMPETITIONS.items()]
            return 200, _response(rows), headers
        parsed = urlparse(path)
        comp = parsed.path.split("/")[2]
        params = parse_qs(parsed.query)
        status = params["status"][0]
        assert "from_time" in params and "to_time" in params
        assert "start_time" not in params and "end_time" not in params
        rows = history if comp == "4160026622" and status == "finished" else (
            upcoming if comp == "4160026622" and status == "scheduled" else []
        )
        return 200, _response(rows), headers

    report = run_forecast_probe(
        "fake-test-key", now=NOW, request_fn=request, sleep=lambda _: None,
        clock=lambda: NOW,
    )
    validate_report(report)
    assert report["request_count"] == 16
    assert report["request_budget"] == REQUEST_BUDGET
    assert report["history_observation_count"] == 100
    assert report["scheduled_target_count"] == 1
    assert report["skipped_outside_window"] == 1
    assert report["skips"]["outside_window"] == 1
    assert report["forecast_count"] == 1
    assert report["status"] == "CALCULATED_NOT_PUBLISHED"
    assert report["publication_locked"] is True
    assert report["forecasts"][0]["home_team"] == "Alpha FC"
    assert report["forecasts"][0]["away_team"] == "Beta FC"
    assert report["forecasts"][0]["publishable"] is False
    assert report["side_effects"]["database_writes"] == 0
    assert report["side_effects"]["telegram_messages"] == 0
    assert all("raw" not in key.casefold() for key in report)


def test_probe_missing_secret_makes_no_requests_and_fails_closed():
    calls = []
    report = run_forecast_probe("", now=NOW, request_fn=lambda *args: calls.append(args),
                                sleep=lambda _: None, clock=lambda: NOW)
    validate_report(report)
    assert calls == []
    assert report["status"] == "CAPTURE_FAILED"
    assert report["failure_reason"] == "MISSING_SECRET"
    assert report["forecast_count"] == 0


def test_report_validator_rejects_any_publishable_forecast():
    report = run_forecast_probe("", now=NOW, request_fn=lambda *args: None,
                                sleep=lambda _: None, clock=lambda: NOW)
    report["forecasts"] = [{"publishable": True}]
    report.pop("report_sha256")
    from scripts.veltrix_v2.fivedollar_forecast_dry_run import _report_hash
    report["report_sha256"] = _report_hash(report)
    import pytest
    with pytest.raises(ValueError, match="FORECAST_PUBLICATION_FLAG_INVALID"):
        validate_report(report)
