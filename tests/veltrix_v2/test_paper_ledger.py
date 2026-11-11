from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.contracts.odds import OddsSnapshot
from veltrix_v2.evaluation.paper_ledger import PaperLedger, PaperSelection
from veltrix_v2.evaluation.settlement import MarketBet, MatchResult

UTC = timezone.utc
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
KICKOFF = NOW + timedelta(days=1)


def selection(selection_id="s1", *, selected_at=NOW + timedelta(minutes=1), probability="0.6"):
    quote = OddsSnapshot(
        snapshot_id=f"odds-{selection_id}",
        fixture_id=f"fixture-{selection_id}",
        source_id="the-odds-api",
        bookmaker_id="bet365",
        market="1X2",
        selection="HOME",
        decimal_odds=Decimal("2.0"),
        captured_at=NOW,
        kickoff_at=KICKOFF,
        provider_quote_at=NOW,
    )
    bet = MarketBet(
        fixture_id=f"fixture-{selection_id}",
        market="1X2",
        selection="HOME",
        decimal_odds=Decimal("2.0"),
        stake=Decimal("1.0"),
    )
    return PaperSelection(
        selection_id=selection_id,
        report_id="report-1",
        forecast_id=f"forecast-id-{selection_id}",
        prediction_certification_id="prediction-cert-1",
        bet=bet,
        odds_snapshot=quote,
        model_probability=Decimal(probability),
        model_version="veltrix-v2-test",
        forecast_generated_at_utc=NOW - timedelta(minutes=1),
        selected_at_utc=selected_at,
        forecast_source_observation_ids=(f"forecast-{selection_id}",),
    )


def test_paper_selection_requires_prematch_forecast_odds_and_positive_value():
    with pytest.raises(ValueError, match="NOT_PROSPECTIVE"):
        selection(selected_at=KICKOFF + timedelta(seconds=1))
    with pytest.raises(ValueError, match="NO_POSITIVE_EXPECTED_VALUE"):
        selection(probability="0.4")


def test_paper_selection_rejects_missing_forecast_provenance():
    row = selection()
    with pytest.raises(ValueError, match="FORECAST_PROVENANCE_REQUIRED"):
        PaperSelection(
            selection_id=row.selection_id,
            report_id=row.report_id,
            forecast_id=row.forecast_id,
            prediction_certification_id=row.prediction_certification_id,
            bet=row.bet,
            odds_snapshot=row.odds_snapshot,
            model_probability=row.model_probability,
            model_version=row.model_version,
            forecast_generated_at_utc=row.forecast_generated_at_utc,
            selected_at_utc=row.selected_at_utc,
            forecast_source_observation_ids=(),
        )


def test_ledger_is_append_only_and_rejects_duplicate_fixture_market_selection():
    row = selection()
    ledger = PaperLedger().record_selection(row)
    assert len(ledger.selections) == 1
    with pytest.raises(ValueError, match="DUPLICATE_SELECTION_ID"):
        PaperLedger((row, row), ())
    duplicate_id = PaperSelection(
        selection_id="s2",
        report_id="report-1",
        forecast_id="forecast-id-s2",
        prediction_certification_id="prediction-cert-1",
        bet=row.bet,
        odds_snapshot=OddsSnapshot(
            snapshot_id="odds-s2", fixture_id=row.bet.fixture_id,
            source_id="the-odds-api", bookmaker_id="bet365",
            market="1X2", selection="HOME", decimal_odds=Decimal("2"),
            captured_at=NOW, kickoff_at=KICKOFF, provider_quote_at=NOW,
        ),
        model_probability=Decimal("0.61"), model_version="veltrix-v2-test",
        forecast_generated_at_utc=NOW, selected_at_utc=NOW + timedelta(minutes=2),
        forecast_source_observation_ids=("forecast-s2",),
    )
    with pytest.raises(ValueError, match="DUPLICATE_FIXTURE_MARKET_SELECTION"):
        ledger.record_selection(duplicate_id)


def test_settlement_is_recorded_once_and_counts_only_non_void_selections():
    row = selection()
    ledger = PaperLedger().record_selection(row)
    result = MatchResult(
        fixture_id=row.bet.fixture_id,
        status="COMPLETED",
        home_goals_regulation=2,
        away_goals_regulation=0,
        match_date=date(2026, 1, 2),
        match_date_source_observation_id="match-date-observation",
    )
    settled_at = KICKOFF + timedelta(hours=5)
    ledger = ledger.settle_selection(
        row.selection_id, result, event_id="settlement-1",
        result_observed_at_utc=KICKOFF + timedelta(hours=3),
        result_source_observation_id="result-observation",
        settled_at_utc=settled_at,
    )
    assert ledger.entries[0].settlement_event is not None
    assert ledger.entries[0].settlement_event.settlement.status == "WIN"
    assert ledger.settlements_for_market("1X2")[0].status == "WIN"
    counts = ledger.counts_for_market("1X2")
    assert counts.selected_count == 1
    assert counts.settled_count == 1
    assert counts.distinct_settled_dates == 1
    assert not counts.sample_gate_passed
    with pytest.raises(ValueError, match="ALREADY_SETTLED"):
        ledger.settle_selection(
            row.selection_id, result, event_id="settlement-2",
            result_observed_at_utc=KICKOFF + timedelta(hours=3),
            result_source_observation_id="result-observation",
            settled_at_utc=settled_at,
        )


def test_voided_selection_is_not_counted_as_prospective_settled_sample():
    row = selection()
    ledger = PaperLedger().record_selection(row)
    result = MatchResult(fixture_id=row.bet.fixture_id, status="POSTPONED")
    observed = NOW + timedelta(hours=12)
    ledger = ledger.settle_selection(
        row.selection_id, result, event_id="void-1",
        result_observed_at_utc=observed,
        result_source_observation_id="postponement-observation",
        settled_at_utc=observed + timedelta(minutes=1),
    )
    counts = ledger.counts_for_market("1X2")
    assert counts.voided_count == 1
    assert counts.settled_count == 0
    assert counts.pending_count == 0



def test_market_count_rejects_unsupported_market():
    with pytest.raises(ValueError, match="MARKET_UNSUPPORTED"):
        PaperLedger().counts_for_market("CORNERS")
