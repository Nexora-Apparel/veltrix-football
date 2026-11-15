import json
import sys

import pytest

from scripts.phase2_capture_fivedollar_opening_odds import (
    MAX_FIXTURES,
    _header_int,
    _validate_fixture_identity,
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
