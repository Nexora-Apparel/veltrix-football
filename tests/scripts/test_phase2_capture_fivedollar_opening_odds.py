import json
import sys

import pytest

from scripts.phase2_capture_fivedollar_opening_odds import (
    MAX_FIXTURES,
    _header_int,
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
