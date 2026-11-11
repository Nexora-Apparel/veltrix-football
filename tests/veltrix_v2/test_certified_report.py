from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.evaluation.certification import MarketCertificationEvidence, certify_release
from veltrix_v2.publishing.certified_report import (
    MarketForecasts,
    PublishedFixture,
    build_certified_daily_report,
    telegram_report_text,
    website_report_payload,
)

UTC = timezone.utc


def passing_certification():
    rows = [
        MarketCertificationEvidence(
            market=market,
            walk_forward_matches=1000,
            prospective_settled_selections=300,
            distinct_dates=90,
            timestamped_odds_coverage=Decimal("0.99"),
            net_roi=Decimal("0.03"),
            roi_ci95_lower=Decimal("0.01"),
            roi_ci_method="chronological_block_bootstrap_by_match_date",
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
        certification=passing_certification(),
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
    assert "Value bet: NO QUALIFIED VALUE" in message
    assert "experimental" not in message.lower()


def test_uncertified_report_cannot_be_published():
    cert = certify_release(
        [
            MarketCertificationEvidence(
                market=market, walk_forward_matches=0,
                prospective_settled_selections=0, distinct_dates=0,
                timestamped_odds_coverage=Decimal("0"), net_roi=Decimal("0"),
                roi_ci95_lower=Decimal("0"),
                roi_ci_method="iid_bet_row_bootstrap",
                source_approved=False, point_in_time_validated=False,
            )
            for market in ("1X2", "BTTS", "TOTALS")
        ],
        one_x_two_beats_bookmaker_brier=False,
        one_x_two_beats_bookmaker_log_loss=False,
    )
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
            fixtures=(),
        )


def test_empty_day_report_is_valid_but_does_not_force_fixtures():
    report = build([])
    assert report.fixtures == ()
    assert "No fixtures passed the publication gate today." in telegram_report_text(report)


def test_report_rejects_fixtures_outside_wat_report_date():
    with pytest.raises(ValueError, match="OUTSIDE_WAT_REPORT_DATE"):
        build([fixture("tomorrow", datetime(2026, 11, 12, 23, 30, tzinfo=UTC))])
