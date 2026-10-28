from datetime import datetime, timezone

from app.multi_source import (
    FixtureRecord,
    OddsQuote,
    best_current_quotes,
    normalize_name,
    reconcile_fixtures,
)


def test_normalize_name_handles_accents_and_punctuation():
    assert normalize_name("Atlético-Madrid") == "atletico madrid"


def test_reconcile_fixtures_groups_same_match_and_preserves_provenance():
    rows = reconcile_fixtures([
        FixtureRecord(
            source="provider_a", source_id="a1",
            kickoff="2026-10-28T18:00:00Z",
            home="Atlético Madrid", away="Real Madrid",
            competition="La Liga", status="FT", home_goals=2, away_goals=1,
        ),
        FixtureRecord(
            source="provider_b", source_id="b9",
            kickoff="2026-10-28T18:00:00+00:00",
            home="Atletico Madrid", away="Real Madrid",
            competition="La Liga", status="FT", home_goals=2, away_goals=1,
        ),
    ])
    assert len(rows) == 1
    assert rows[0]["source_count"] == 2
    assert rows[0]["score"] == (2, 1)
    assert rows[0]["needs_review"] is False
    assert rows[0]["sources"] == ["provider_a", "provider_b"]


def test_reconcile_fixtures_flags_disagreeing_scores():
    rows = reconcile_fixtures([
        FixtureRecord(
            source="provider_a", source_id="a1",
            kickoff="2026-10-28T18:00:00Z",
            home="Home FC", away="Away FC", competition="League",
            status="FT", home_goals=1, away_goals=0,
        ),
        FixtureRecord(
            source="provider_b", source_id="b1",
            kickoff="2026-10-28T18:00:00Z",
            home="Home FC", away="Away FC", competition="League",
            status="FT", home_goals=2, away_goals=0,
        ),
    ])
    assert len(rows) == 1
    assert rows[0]["score"] is None
    assert rows[0]["score_conflict"] is True
    assert rows[0]["needs_review"] is True


def test_reconcile_rejects_naive_kickoff_instead_of_guessing_timezone():
    rows = reconcile_fixtures([
        FixtureRecord(
            source="provider_a", source_id="a1",
            kickoff="2026-10-28T18:00:00",
            home="Home FC", away="Away FC", competition="League",
        ),
    ])
    assert len(rows) == 1
    assert rows[0]["identity"] is None
    assert rows[0]["needs_review"] is True


def test_best_current_quotes_uses_highest_fresh_price_and_keeps_source():
    now = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
    quotes = [
        OddsQuote(
            source="provider_a", source_fixture_id="a1", bookmaker="Book A",
            market="BTTS", selection="Yes", decimal_odds=1.80,
            captured_at="2026-10-28T11:30:00Z",
        ),
        OddsQuote(
            source="provider_b", source_fixture_id="b1", bookmaker="Book B",
            market="BTTS", selection="Yes", decimal_odds=1.88,
            captured_at="2026-10-28T11:50:00Z",
        ),
        OddsQuote(
            source="provider_c", source_fixture_id="c1", bookmaker="Book C",
            market="BTTS", selection="Yes", decimal_odds=2.10,
            captured_at="2026-10-28T06:00:00Z",
        ),
    ]
    best = best_current_quotes(quotes, now=now, max_age_minutes=180)
    quote = best[("btts", "yes")]
    assert quote["decimal_odds"] == 1.88
    assert quote["source"] == "provider_b"
    assert quote["bookmaker"] == "Book B"


def test_best_current_quotes_ignores_invalid_prices():
    now = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
    quote = OddsQuote(
        source="provider_a", source_fixture_id="a1", bookmaker="Book A",
        market="BTTS", selection="Yes", decimal_odds=1.0,
        captured_at="2026-10-28T11:30:00Z",
    )
    assert best_current_quotes([quote], now=now) == {}
