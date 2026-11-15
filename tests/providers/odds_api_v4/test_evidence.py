from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json

from veltrix_v2.providers.odds_api_v4.evidence import (
    FixtureCrosswalk, QuoteRights, evaluate_quote_admission,
)
from veltrix_v2.providers.odds_api_v4.parser import parse_bulk_odds


UTC = timezone.utc
CUTOFF = datetime(2026, 11, 20, 17, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
RETRIEVED = datetime(2026, 11, 20, 16, 50, tzinfo=UTC)
PUBLISHED = datetime(2026, 11, 20, 16, 45, tzinfo=UTC)
HASH = hashlib.sha256(b"raw").hexdigest()


def quote(*, price="2.15", published="2026-11-20T16:45:00Z",
          retrieved=RETRIEVED):
    raw = json.dumps([{
        "id": "event-abc",
        "bookmakers": [{
            "key": "bookmaker-x", "title": "Bookmaker X",
            "markets": [{
                "key": "h2h", "last_update": published,
                "outcomes": [{"name": "Home", "price": price}],
            }],
        }],
    }]).encode()
    return parse_bulk_odds(raw, sport_key="soccer_epl",
                            retrieved_at=retrieved).observations[0]


def evidence(q):
    crosswalk = FixtureCrosswalk(
        "the_odds_api", "odds_api_v4", "event-abc", 123,
        "FIXTURE", "RESOLVED", RETRIEVED - timedelta(days=1),
        None, 7,
    )
    rights = QuoteRights(
        "approval-odds-1", "the_odds_api", "odds_api_v4", "APPROVED",
        frozenset({"COLLECTION", "STORAGE"}),
        RETRIEVED - timedelta(days=3), RETRIEVED - timedelta(days=2),
        RETRIEVED + timedelta(days=30), "a" * 64,
    )
    return evaluate_quote_admission(
        quote=q, crosswalk=crosswalk, rights=rights, fixture_id=123,
        prediction_cutoff_at=CUTOFF, kickoff_at=KICKOFF,
        evaluated_at=RETRIEVED + timedelta(seconds=1),
    )


def test_exact_quote_crosswalk_rights_and_both_clocks_admit():
    q = quote()
    result = evidence(q)
    assert result.admitted
    assert result.reason_codes == ()
    assert len(result.observation_key) == 64


def test_market_update_after_cutoff_is_rejected_even_if_retrieval_is_before_cutoff():
    q = quote(published="2026-11-20T17:05:00Z")
    result = evidence(q)
    assert not result.admitted
    assert "SOURCE_TIMESTAMP_AFTER_PREDICTION_CUTOFF" in result.reason_codes
    assert "SOURCE_TIMESTAMP_AFTER_RETRIEVAL" in result.reason_codes


def test_retrieval_after_cutoff_is_rejected_even_if_market_timestamp_is_earlier():
    q = quote(retrieved=CUTOFF + timedelta(seconds=1))
    result = evidence(q)
    assert not result.admitted
    assert "RETRIEVAL_AFTER_PREDICTION_CUTOFF" in result.reason_codes


def test_exact_fixture_identity_is_mandatory():
    q = quote()
    result = evaluate_quote_admission(
        quote=q,
        crosswalk=FixtureCrosswalk(
            "the_odds_api", "odds_api_v4", "other-event", 123,
            "FIXTURE", "RESOLVED", RETRIEVED - timedelta(days=1), None, 7
        ),
        rights=QuoteRights(
            "approval-odds-1", "the_odds_api", "odds_api_v4", "APPROVED",
            frozenset({"COLLECTION", "STORAGE"}),
            RETRIEVED - timedelta(days=3), RETRIEVED - timedelta(days=2),
            RETRIEVED + timedelta(days=30), "a" * 64,
        ),
        fixture_id=123, prediction_cutoff_at=CUTOFF,
        kickoff_at=KICKOFF, evaluated_at=RETRIEVED + timedelta(seconds=1),
    )
    assert not result.admitted
    assert "FIXTURE_CROSSWALK_MISMATCH" in result.reason_codes


def test_rights_must_be_approved_before_quote_retrieval():
    q = quote()
    result = evaluate_quote_admission(
        quote=q,
        crosswalk=FixtureCrosswalk(
            "the_odds_api", "odds_api_v4", "event-abc", 123,
            "FIXTURE", "RESOLVED", RETRIEVED - timedelta(days=1), None, 7,
        ),
        rights=QuoteRights(
            "approval-odds-1", "the_odds_api", "odds_api_v4", "APPROVED",
            frozenset({"COLLECTION", "STORAGE"}),
            RETRIEVED + timedelta(seconds=2), RETRIEVED + timedelta(seconds=3),
            RETRIEVED + timedelta(days=30), "a" * 64,
        ),
        fixture_id=123, prediction_cutoff_at=CUTOFF,
        kickoff_at=KICKOFF, evaluated_at=RETRIEVED + timedelta(seconds=4),
    )
    assert not result.admitted
    assert "QUOTE_RIGHTS_NOT_VALID_AT_EVALUATION" in result.reason_codes


def test_unapproved_rights_missing_timestamp_or_bad_hash_fail_closed():
    q = quote()
    result = evaluate_quote_admission(
        quote=q,
        crosswalk=None,
        rights=QuoteRights(
            "approval-odds-1", "the_odds_api", "odds_api_v4", "REVOKED",
            frozenset({"COLLECTION"}), RETRIEVED - timedelta(days=3),
            RETRIEVED - timedelta(days=2), None, "bad",
        ),
        fixture_id=123, prediction_cutoff_at=CUTOFF,
        kickoff_at=KICKOFF, evaluated_at=RETRIEVED + timedelta(seconds=1),
    )
    assert not result.admitted
    assert {
        "FIXTURE_CROSSWALK_MISSING", "QUOTE_RIGHTS_SCOPE_NOT_APPROVED",
        "QUOTE_RIGHTS_HASH_INVALID",
    }.issubset(result.reason_codes)


def test_price_change_creates_a_distinct_immutable_observation_key():
    first = evidence(quote(price="2.15"))
    second = evidence(quote(price="2.20"))
    assert first.admitted and second.admitted
    assert first.observation_key != second.observation_key
