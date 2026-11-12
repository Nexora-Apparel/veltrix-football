from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache

import pytest

from veltrix_v2.evaluation.roi import MarketPerformance, evaluate_roi
from veltrix_v2.evaluation.settlement import MarketBet, MatchResult, settle_market_bet
from veltrix_v2.evaluation.certification import (
    MarketCertificationEvidence, PredictionMarketEvidence,
    _certify_prediction_publication_from_derived_evidence, certify_release,
)
from veltrix_v2.publishing.certified_report import (
    MarketForecasts,
    PublishedFixture,
    build_certified_daily_report,
    telegram_report_text,
    website_report_payload,
)

UTC = timezone.utc


def passing_prediction_certification():
    return _certify_prediction_publication_from_derived_evidence([
        PredictionMarketEvidence(
            market=market, walk_forward_matches=1000,
            source_approved=True, point_in_time_validated=True,
            leakage_tests_passed=True, calibration_passed=True,
        )
        for market in ("1X2", "BTTS", "TOTALS")
    ])


@lru_cache(maxsize=None)
def computed_roi_performance(market):
    settlements = []
    for index in range(300):
        fixture_id = f"cert-{market.lower()}-{index}"
        match_day = date(2026, 1, 1) + timedelta(days=index % 90)
        selection, line, home, away = {
            "1X2": ("HOME", None, 2, 0),
            "BTTS": ("YES", None, 2, 1),
            "TOTALS": ("OVER", Decimal("2.5"), 2, 1),
        }[market]
        bet = MarketBet(
            fixture_id=fixture_id, market=market, selection=selection,
            decimal_odds=Decimal("2.0"), stake=Decimal("1"), line=line,
        )
        result = MatchResult(
            fixture_id=fixture_id, status="COMPLETED",
            home_goals_regulation=home, away_goals_regulation=away,
            match_date=match_day,
            match_date_source_observation_id=f"obs-{fixture_id}",
        )
        settlements.append(settle_market_bet(bet, result))
    report = evaluate_roi(settlements, bootstrap_draws=100)
    return next(row for row in report.markets if row.market == market)


def empty_roi_performance(market):
    return MarketPerformance(
        market=market, total_bets=0, wins=0, losses=0, pushes=0, voids=0,
        decisive_bets=0, settled_bets=0, win_rate=None, win_rate_ci_95=None,
        settled_turnover=Decimal("0"), gross_return=Decimal("0"),
        net_profit=Decimal("0"), roi=None, roi_ci_95=None,
        roi_ci_method="unavailable_insufficient_match_dates",
    )


def passing_value_bet_certification():
    rows = [
        MarketCertificationEvidence(
            market=market,
            walk_forward_matches=1000,
            prospective_settled_selections=300,
            distinct_dates=90,
            timestamped_odds_coverage=Decimal("0.99"),
            roi_performance=computed_roi_performance(market),
            source_approved=True,
            point_in_time_validated=True,
        )
        for market in ("1X2", "BTTS", "TOTALS")
    ]
    return certify_release(
        rows,
        one_x_two_beats_bookmaker_brier=True,
        one_x_two_beats_bookmaker_log_loss=True,
    )


def fixture(fid, kickoff):
    return PublishedFixture(
        fixture_id=fid,
        competition="England Premier League",
        home_team="Team A",
        away_team="Team B",
        kickoff_utc=kickoff,
        forecasts=MarketForecasts(
            Decimal("0.55"), Decimal("0.25"), Decimal("0.20"),
            Decimal("0.58"), Decimal("2.5"), Decimal("0.53"),
        ),
        source_provider_ids=("5dollarfootballapi",),
        verdict="HOME LEAN",
        ai_insight="Home side creates more high-quality chances.",
    )


def build(rows):
    return build_certified_daily_report(
        report_date_wat=date(2026, 11, 12),
        generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
        certification=passing_prediction_certification(),
        certification_id="cert-v2-001",
        fixtures=tuple(rows),
        source_attributions=("Football data by 5DollarFootballAPI — https://5dollarfootballapi.com",),
    )


def test_certified_report_serializes_for_website_and_telegram():
    report = build([fixture("f1", datetime(2026, 11, 12, 6, tzinfo=UTC))])
    payload = website_report_payload(report)
    assert payload["schema_version"] == 1
    assert payload["fixture_count"] == 1
    assert payload["fixtures"][0]["kickoff_wat"].startswith("2026-11-12T07:00")
    message = telegram_report_text(report)
    assert message.startswith("🔔 🆕 NEW VELTRIX UPDATE")
    assert report.value_bets_enabled is False
    assert payload["value_bets_enabled"] is False
    assert "Value betting: LOCKED — NOT CERTIFIED" in message
    assert "Value bet: LOCKED — NOT CERTIFIED" in message
    assert "experimental" not in message.lower()


def test_uncertified_report_cannot_be_published():
    cert = certify_prediction_publication([
            PredictionMarketEvidence(
                market=market, walk_forward_matches=0,
                source_approved=False, point_in_time_validated=False,
                leakage_tests_passed=False, calibration_passed=False,
            )
            for market in ("1X2", "BTTS", "TOTALS")
    ])
    with pytest.raises(ValueError, match="CERTIFICATION_REQUIRED"):
        build_certified_daily_report(
            report_date_wat=date(2026, 11, 12),
            generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
            certification=cert,
            certification_id="cert-fail",
            fixtures=(),
        )


def test_report_rejects_started_fixtures_and_more_than_25():
    with pytest.raises(ValueError, match="STARTED_OR_PAST"):
        build([fixture("past", datetime(2026, 11, 12, 4, 0, tzinfo=UTC))])
    rows = [
        fixture(f"f{i}", datetime(2026, 11, 12, 6, tzinfo=UTC) + timedelta(hours=i))
        for i in range(26)
    ]
    with pytest.raises(ValueError, match="FIXTURE_CAP"):
        build(rows)


def test_report_deadline_is_exactly_0600_wat():
    with pytest.raises(ValueError, match="DEADLINE_MUST_BE_0600_WAT"):
        from veltrix_v2.publishing.certified_report import CertifiedDailyReport
        CertifiedDailyReport(
            report_date_wat=date(2026, 11, 12),
            generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
            delivery_deadline_utc=datetime(2026, 11, 12, 6, 0, tzinfo=UTC),
            certification_id="cert-v2-001",
            prediction_certification=passing_prediction_certification(),
            value_bet_certification=None,
            value_bets_enabled=False,
            source_attributions=(),
            fixtures=(),
        )


def test_empty_day_report_is_valid_but_does_not_force_fixtures():
    report = build([])
    assert report.fixtures == ()
    assert "No fixtures passed the publication gate today." in telegram_report_text(report)


def test_report_rejects_fixtures_outside_wat_report_date():
    with pytest.raises(ValueError, match="OUTSIDE_WAT_REPORT_DATE"):
        build([fixture("tomorrow", datetime(2026, 11, 12, 23, 30, tzinfo=UTC))])



def test_value_bets_unlock_only_after_full_value_bet_certification():
    value_fixture = PublishedFixture(
        fixture_id="f-value", competition="England Premier League",
        home_team="Team A", away_team="Team B",
        kickoff_utc=datetime(2026, 11, 12, 6, tzinfo=UTC),
        forecasts=MarketForecasts(
            Decimal("0.55"), Decimal("0.25"), Decimal("0.20"),
            Decimal("0.58"), Decimal("2.5"), Decimal("0.53"),
        ),
        source_provider_ids=("5dollarfootballapi",),
        verdict="HOME LEAN", ai_insight="Test-only certified evidence.",
        value_bet_verdict="QUALIFIED VALUE",
    )
    report = build_certified_daily_report(
        report_date_wat=date(2026, 11, 12),
        generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
        certification=passing_prediction_certification(),
        certification_id="prediction-cert-v2-001",
        fixtures=(value_fixture,),
        value_bet_certification=passing_value_bet_certification(),
        source_attributions=("Football data by 5DollarFootballAPI — https://5dollarfootballapi.com",),
    )
    assert report.value_bets_enabled is True
    assert report.fixtures[0].value_bet_verdict == "QUALIFIED VALUE"


def test_failed_value_bet_certification_does_not_block_prediction_publication():
    failed_value_cert = certify_release(
        [
            MarketCertificationEvidence(
                market=market, walk_forward_matches=1000,
                prospective_settled_selections=0, distinct_dates=90,
                timestamped_odds_coverage=Decimal("0.99"),
                roi_performance=empty_roi_performance(market),
                source_approved=True, point_in_time_validated=True,
            )
            for market in ("1X2", "BTTS", "TOTALS")
        ],
        one_x_two_beats_bookmaker_brier=True,
        one_x_two_beats_bookmaker_log_loss=True,
    )
    report = build_certified_daily_report(
        report_date_wat=date(2026, 11, 12),
        generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
        certification=passing_prediction_certification(),
        certification_id="prediction-cert-v2-001",
        fixtures=(fixture("f-locked", datetime(2026, 11, 12, 6, tzinfo=UTC)),),
        value_bet_certification=failed_value_cert,
        source_attributions=("Football data by 5DollarFootballAPI — https://5dollarfootballapi.com",),
    )
    assert report.value_bets_enabled is False
    assert report.fixtures[0].value_bet_verdict == "LOCKED — NOT CERTIFIED"



def test_provider_attribution_is_included_in_website_and_telegram_payloads():
    attribution = "Football data by 5DollarFootballAPI — https://5dollarfootballapi.com"
    report = build_certified_daily_report(
        report_date_wat=date(2026, 11, 12),
        generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
        certification=passing_prediction_certification(),
        certification_id="prediction-cert-v2-001",
        fixtures=(PublishedFixture(
            fixture_id="f-attribution", competition="England Premier League",
            home_team="Team A", away_team="Team B",
            kickoff_utc=datetime(2026, 11, 12, 6, tzinfo=UTC),
            forecasts=MarketForecasts(
                Decimal("0.5"), Decimal("0.3"), Decimal("0.2"),
                Decimal("0.55"), Decimal("2.5"), Decimal("0.52"),
            ),
            source_provider_ids=("5dollarfootballapi",),
            verdict="HOME LEAN", ai_insight="Attribution test.",
        ),),
        source_attributions=(attribution,),
    )
    payload = website_report_payload(report)
    message = telegram_report_text(report)
    assert payload["source_attributions"] == [attribution]
    assert payload["fixtures"][0]["source_provider_ids"] == ["5dollarfootballapi"]
    assert message.endswith(attribution)



def test_fivedollar_report_requires_visible_linked_provider_attribution():
    attributed_fixture = PublishedFixture(
        fixture_id="f-attribution-required", competition="England Premier League",
        home_team="Team A", away_team="Team B",
        kickoff_utc=datetime(2026, 11, 12, 6, tzinfo=UTC),
        forecasts=MarketForecasts(
            Decimal("0.5"), Decimal("0.3"), Decimal("0.2"),
            Decimal("0.55"), Decimal("2.5"), Decimal("0.52"),
        ),
        source_provider_ids=("5dollarfootballapi",),
        verdict="HOME LEAN", ai_insight="Attribution enforcement test.",

    )
    with pytest.raises(ValueError, match="REPORT_REQUIRED_PROVIDER_ATTRIBUTION_MISSING:5dollarfootballapi"):
        build_certified_daily_report(
            report_date_wat=date(2026, 11, 12),
            generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
            certification=passing_prediction_certification(),
            certification_id="prediction-cert-v2-001",
            fixtures=(attributed_fixture,),
        )


def test_openligadb_report_requires_odbl_attribution():
    attributed_fixture = PublishedFixture(
        fixture_id="f-openligadb", competition="Germany Bundesliga",
        home_team="Team A", away_team="Team B",
        kickoff_utc=datetime(2026, 11, 12, 6, tzinfo=UTC),
        forecasts=MarketForecasts(
            Decimal("0.5"), Decimal("0.3"), Decimal("0.2"),
            Decimal("0.55"), Decimal("2.5"), Decimal("0.52"),
        ),
        source_provider_ids=("openligadb",),
        verdict="HOME LEAN", ai_insight="ODbL attribution test.",

    )
    with pytest.raises(ValueError, match="REPORT_REQUIRED_PROVIDER_ATTRIBUTION_MISSING:openligadb"):
        build_certified_daily_report(
            report_date_wat=date(2026, 11, 12),
            generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
            certification=passing_prediction_certification(),
            certification_id="prediction-cert-v2-001",
            fixtures=(attributed_fixture,),
        )



def test_published_fixture_requires_explicit_source_provenance():
    with pytest.raises(ValueError, match="REPORT_SOURCE_PROVIDER_REQUIRED"):
        PublishedFixture(
            fixture_id="f-no-source", competition="England Premier League",
            home_team="Team A", away_team="Team B",
            kickoff_utc=datetime(2026, 11, 12, 6, tzinfo=UTC),
            forecasts=MarketForecasts(
                Decimal("0.5"), Decimal("0.3"), Decimal("0.2"),
                Decimal("0.55"), Decimal("2.5"), Decimal("0.52"),
            ),
            source_provider_ids=(),
            verdict="HOME LEAN", ai_insight="No source IDs should fail.",
        )



def test_report_value_bet_state_cannot_be_enabled_without_passed_certification():
    from veltrix_v2.publishing.certified_report import CertifiedDailyReport

    with pytest.raises(ValueError, match="VALUE_BET_STATE_CONFLICTS"):
        CertifiedDailyReport(
            report_date_wat=date(2026, 11, 12),
            generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
            delivery_deadline_utc=datetime(2026, 11, 12, 5, 0, tzinfo=UTC),
            certification_id="cert-v2-001",
            prediction_certification=passing_prediction_certification(),
            value_bet_certification=None,
            value_bets_enabled=True,
            source_attributions=(),
            fixtures=(),
        )


def test_report_constructor_rechecks_required_provider_attribution():
    from veltrix_v2.publishing.certified_report import CertifiedDailyReport

    with pytest.raises(ValueError, match="REQUIRED_PROVIDER_ATTRIBUTION_MISSING"):
        CertifiedDailyReport(
            report_date_wat=date(2026, 11, 12),
            generated_at_utc=datetime(2026, 11, 12, 4, 30, tzinfo=UTC),
            delivery_deadline_utc=datetime(2026, 11, 12, 5, 0, tzinfo=UTC),
            certification_id="cert-v2-001",
            prediction_certification=passing_prediction_certification(),
            value_bet_certification=None,
            value_bets_enabled=False,
            source_attributions=(),
            fixtures=(fixture("f-direct", datetime(2026, 11, 12, 6, tzinfo=UTC)),),
        )
