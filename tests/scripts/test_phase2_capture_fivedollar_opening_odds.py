import json
import sys

import pytest

from scripts.phase2_capture_fivedollar_opening_odds import (
    MAX_FIXTURES,
    _header_int,
    _validate_fixture_identity,
    _validate_quota_preflight,
    _capture_window,
    main,
)


def test_rate_limit_header_parser_is_case_insensitive_and_fail_closed():
    assert _header_int({"X-RateLimit-Remaining": "47"}, "x-ratelimit-remaining") == 47
    assert _header_int({"x-ratelimit-remaining": "0"}, "X-RateLimit-Remaining") == 0
    assert _header_int({"x-ratelimit-remaining": "unknown"}, "x-ratelimit-remaining") is None
    assert _header_int({}, "x-ratelimit-remaining") is None


def test_default_cli_is_dry_run_and_declares_noncommercial_guard(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["phase2_capture_fivedollar_opening_odds"])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "DRY_RUN_NO_NETWORK_NO_DATABASE"
    assert result["commercial_use_allowed"] is False
    assert result["automatic_retries"] is False
    assert result["paid_historical_tick_endpoint"] is False
    assert result["max_fixtures"] == MAX_FIXTURES == 25
    assert result["capture_mode"] == "historical"
    assert result["future_days"] == 0
    assert result["closing_odds_qualified"] is False
    assert result["clv_certified"] is False


@pytest.mark.parametrize("lookback,limit", [(0, 25), (91, 25), (90, 0), (90, 26)])
def test_capture_rejects_out_of_bounds_before_connecting(lookback, limit):
    from scripts.phase2_capture_fivedollar_opening_odds import capture

    with pytest.raises(ValueError, match="OPENING_ODDS_CAPTURE_BOUNDS_INVALID"):
        capture(
            dsn="",
            api_key="",
            lookback_days=lookback,
            max_fixtures=limit,
            output_dir="unused",
        )


def test_capture_windows_are_timezone_aware_and_mode_specific():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    start, end = _capture_window(mode="historical", lookback_days=30, future_days=0, now=now)
    assert start == now - timedelta(days=30)
    assert end == now

    start, end = _capture_window(mode="prospective", lookback_days=90, future_days=7, now=now)
    assert start == now
    assert end == now + timedelta(days=7)


@pytest.mark.parametrize(
    "mode,lookback,future,code",
    [
        ("historical", 0, 0, "OPENING_ODDS_CAPTURE_BOUNDS_INVALID"),
        ("historical", 91, 0, "OPENING_ODDS_CAPTURE_BOUNDS_INVALID"),
        ("historical", 90, 1, "OPENING_ODDS_CAPTURE_BOUNDS_INVALID"),
        ("prospective", 90, 0, "OPENING_ODDS_CAPTURE_BOUNDS_INVALID"),
        ("prospective", 90, 8, "OPENING_ODDS_CAPTURE_BOUNDS_INVALID"),
        ("unknown", 90, 0, "OPENING_ODDS_CAPTURE_MODE_INVALID"),
    ],
)
def test_capture_window_rejects_invalid_mode_or_bounds(mode, lookback, future, code):
    from datetime import datetime, timezone

    with pytest.raises(ValueError, match=code):
        _capture_window(
            mode=mode, lookback_days=lookback, future_days=future,
            now=datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc),
        )


def _fixture_response(*, fixture_id=100, home=11, away=22, league=33, kickoff="2026-11-10T18:00:00+00:00"):
    return json.dumps({
        "success": 1,
        "data": {
            "id": fixture_id,
            "league": {"id": league},
            "teams": {"home": {"id": home}, "away": {"id": away}},
            "kickoff_utc": kickoff,
        },
    }).encode()


def _target():
    from datetime import datetime, timezone
    return {
        "provider_fixture_id": "100",
        "provider_home_team_id": "11",
        "provider_away_team_id": "22",
        "provider_competition_id": "33",
        "kickoff_at": datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc),
    }


def test_fixture_identity_must_match_fixture_teams_competition_and_kickoff():
    _validate_fixture_identity(_fixture_response(), _target())


@pytest.mark.parametrize(
    "body,code",
    [
        (_fixture_response(fixture_id=101), "FIVEDOLLAR_ODDS_FIXTURE_ID_MISMATCH"),
        (_fixture_response(home=99), "FIVEDOLLAR_ODDS_HOME_TEAM_ID_MISMATCH"),
        (_fixture_response(away=99), "FIVEDOLLAR_ODDS_AWAY_TEAM_ID_MISMATCH"),
        (_fixture_response(league=99), "FIVEDOLLAR_ODDS_COMPETITION_ID_MISMATCH"),
        (_fixture_response(kickoff="2026-11-10T20:00:00+00:00"), "FIVEDOLLAR_ODDS_KICKOFF_MISMATCH"),
    ],
)
def test_fixture_identity_mismatch_fails_closed(body, code):
    with pytest.raises(ValueError, match=code):
        _validate_fixture_identity(body, _target())


def _status_body(*, plan="community", hourly=300, burst=20):
    return json.dumps({
        "success": 1,
        "data": {
            "plan": plan,
            "limits": {"rate_limit": hourly, "burst_per_minute": burst},
        },
    }, separators=(",", ":")).encode()


def test_quota_preflight_accepts_only_community_profile_and_sufficient_headroom():
    from datetime import datetime, timezone

    checked_at = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)
    result = _validate_quota_preflight(
        _status_body(),
        {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "26",
         "X-RateLimit-Reset": "1794754800"},
        planned_requests=25,
        checked_at=checked_at,
    )
    assert result["plan"] == "community"
    assert result["rate_limit_hour"] == 300
    assert result["burst_per_minute"] == 20
    assert result["quota_remaining"] == 26
    assert result["requests_planned"] == 25
    assert len(result["response_sha256"]) == 64


@pytest.mark.parametrize(
    "body,headers,planned,code",
    [
        (_status_body(plan="free"), {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "100"}, 25,
         "FIVEDOLLAR_QUOTA_PREFLIGHT_PLAN_MISMATCH"),
        (_status_body(hourly=200), {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "100"}, 25,
         "FIVEDOLLAR_QUOTA_PREFLIGHT_PROFILE_MISMATCH"),
        (_status_body(burst=10), {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "100"}, 25,
         "FIVEDOLLAR_QUOTA_PREFLIGHT_PROFILE_MISMATCH"),
        (_status_body(), {"X-RateLimit-Limit": "300"}, 25,
         "FIVEDOLLAR_QUOTA_PREFLIGHT_HEADERS_INCOMPLETE"),
        (_status_body(), {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "25"}, 25,
         "FIVEDOLLAR_QUOTA_PREFLIGHT_INSUFFICIENT_HEADROOM"),
    ],
)
def test_quota_preflight_fails_closed_on_profile_or_headroom_mismatch(body, headers, planned, code):
    from datetime import datetime, timezone

    with pytest.raises(RuntimeError, match=code):
        _validate_quota_preflight(
            body, headers, planned_requests=planned,
            checked_at=datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc),
        )
