from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts.phase4_odds_one_event_probe import (
    MAX_CREDITS,
    SPORT,
    reconcile_quota,
    select_exact_fixture,
)


KICKOFF = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)


def _fixture(home="Chelsea", away="Leeds", fixture_id=2502):
    return {
        "fixture_id": fixture_id,
        "home": home,
        "away": away,
        "kickoff_at": KICKOFF,
    }


def _event(event_id="evt-1", home="Chelsea", away="Leeds", kickoff="2026-11-21T15:00:00Z", sport_key=SPORT):
    return {
        "id": event_id,
        "sport_key": sport_key,
        "home_team": home,
        "away_team": away,
        "commence_time": kickoff,
    }


def test_select_exact_fixture_accepts_only_exact_names_and_kickoff():
    selected = select_exact_fixture([_fixture()], [_event()])
    assert selected is not None
    fixture, event, kickoff = selected
    assert fixture["fixture_id"] == 2502
    assert event["id"] == "evt-1"
    assert kickoff == KICKOFF


def test_select_exact_fixture_rejects_aliases_and_fuzzy_team_names():
    assert select_exact_fixture([_fixture()], [_event(away="Leeds United")]) is None
    assert select_exact_fixture([_fixture()], [_event(home="Manchester City")]) is None


def test_select_exact_fixture_rejects_ambiguous_event_or_fixture_matches():
    assert select_exact_fixture([_fixture()], [_event(), _event(event_id="evt-2")]) is None
    assert select_exact_fixture([_fixture(), _fixture(fixture_id=2503)], [_event()]) is None


def _quota(used, remaining, last):
    return SimpleNamespace(
        complete=True,
        requests_used=used,
        requests_remaining=remaining,
        requests_last=last,
    )


def test_quota_reconciliation_requires_exact_counter_delta_and_three_credit_cap():
    before = SimpleNamespace(quota_evidence=_quota(226, 274, 0))
    after = SimpleNamespace(status_code=200, quota_evidence=_quota(229, 271, 3))
    assert reconcile_quota(before, after) == 3


@pytest.mark.parametrize(
    "after,match",
    [
        (_quota(229, 272, 3), "ODDS_API_QUOTA_COUNTER_DELTA_MISMATCH"),
        (_quota(230, 270, 4), "ODDS_API_REQUEST_COST_OUTSIDE_THREE_CREDIT_CAP"),
        (_quota(229, 271, 3), None),
    ],
)
def test_quota_reconciliation_fails_closed(after, match):
    before = SimpleNamespace(quota_evidence=_quota(226, 274, 0))
    postflight = SimpleNamespace(status_code=200, quota_evidence=after)
    if match is None:
        assert reconcile_quota(before, postflight) == 3
    else:
        with pytest.raises(ValueError, match=match):
            reconcile_quota(before, postflight)


def test_quota_reconciliation_rejects_missing_headers_and_non_200():
    before = SimpleNamespace(quota_evidence=_quota(226, 274, 0))
    missing = SimpleNamespace(
        status_code=200,
        quota_evidence=SimpleNamespace(
            complete=False, requests_used=None, requests_remaining=None, requests_last=None
        ),
    )
    with pytest.raises(ValueError, match="ODDS_API_QUOTA_HEADERS_INCOMPLETE"):
        reconcile_quota(before, missing)
    after = SimpleNamespace(status_code=403, quota_evidence=_quota(226, 274, 0))
    with pytest.raises(ValueError, match="ODDS_API_ODDS_RESPONSE_NOT_SUCCESSFUL"):
        reconcile_quota(before, after)


def test_select_exact_fixture_accepts_another_explicitly_approved_sport_key():
    fixture = _fixture(home="Como", away="Cagliari")
    event = _event(home="Como", away="Cagliari", sport_key="soccer_italy_serie_a")
    selected = select_exact_fixture(
        [fixture], [event], sport_key="soccer_italy_serie_a"
    )
    assert selected is not None
    assert selected[1]["id"] == "evt-1"
