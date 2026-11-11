from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.evaluation.certification import (
    MarketCertificationEvidence, PredictionMarketEvidence,
    certify_prediction_publication, certify_release,
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
    return certify_prediction_publication([
        PredictionMarketEvidence(
            market=market, walk_forward_matches=1000,
            source_approved=True, point_in_time_validated=True,
            leakage_tests_passed=True, calibration_passed=True,
        )
        for market in ("1X2", "BTTS", "TOTALS")
    ])


def passing_value_bet_certification():
    rows = [
        MarketCertificationEvidence(
            market=market,
            walk_forward_matches=1000,
            prospective_settled_selections=300,
            distinct_dates=90,
            timestamped_odds_coverage=Decimal("0.99"),
            net_roi=Decimal("0.03"),
            roi_ci95_lower=Decimal("0.01"),
            roi_ci_method="date_block_bootstrap_by_match_date",
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
                net_roi=Decimal("0.02"), roi_ci95_lower=Decimal("0.01"),
                roi_ci_method="date_block_bootstrap_by_match_date",
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
            source_provider_ids=("5dollarfootballapi",),
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
        source_provider_ids=("5dollarfootballapi",),
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
        source_provider_ids=("openligadb",),
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
