"""Certified-only daily report contract for website and Telegram adapters.

This module defines the boundary, not a transport integration. Prediction
publication and value-bet activation have separate certification gates. No
schedule or network delivery is performed here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from veltrix_v2.evaluation.certification import PredictionReleaseCertification, ReleaseCertification

WAT = ZoneInfo("Africa/Lagos")
MAX_DAILY_FIXTURES = 25
PROVIDER_ATTRIBUTION_RULES = {
    "5dollarfootballapi": "Football data by 5DollarFootballAPI — https://5dollarfootballapi.com",
    "openligadb": "Data by OpenLigaDB (ODbL 1.0) — https://www.openligadb.de",
    "openfootball": None,
}


@dataclass(frozen=True, slots=True)
class MarketForecasts:
    p_home: Decimal
    p_draw: Decimal
    p_away: Decimal
    p_btts_yes: Decimal
    total_line: Decimal
    p_over: Decimal

    def __post_init__(self) -> None:
        values = (self.p_home, self.p_draw, self.p_away, self.p_btts_yes, self.p_over)
        if any(not isinstance(value, Decimal) or not value.is_finite() for value in values):
            raise ValueError("REPORT_PROBABILITIES_MUST_BE_FINITE_DECIMALS")
        if any(value <= 0 or value >= 1 for value in values):
            raise ValueError("REPORT_PROBABILITIES_MUST_BE_STRICTLY_BETWEEN_ZERO_AND_ONE")
        if abs(self.p_home + self.p_draw + self.p_away - Decimal("1")) > Decimal("0.000000001"):
            raise ValueError("REPORT_1X2_PROBABILITIES_MUST_SUM_TO_ONE")
        if not isinstance(self.total_line, Decimal) or not self.total_line.is_finite():
            raise ValueError("REPORT_TOTAL_LINE_INVALID")
        if self.total_line < 0 or self.total_line % Decimal("1") != Decimal("0.5"):
            raise ValueError("REPORT_TOTAL_LINE_MUST_BE_HALF_GOAL")


@dataclass(frozen=True, slots=True)
class PublishedFixture:
    fixture_id: str
    competition: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    forecasts: MarketForecasts
    source_provider_ids: tuple[str, ...]
    verdict: str
    ai_insight: str
    value_bet_verdict: str = "LOCKED — NOT CERTIFIED"

    def __post_init__(self) -> None:
        for field in ("fixture_id", "competition", "home_team", "away_team", "verdict", "ai_insight", "value_bet_verdict"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"REPORT_{field.upper()}_REQUIRED")
        if self.home_team == self.away_team:
            raise ValueError("REPORT_HOME_AWAY_TEAMS_MUST_DIFFER")
        if not isinstance(self.forecasts, MarketForecasts):
            raise ValueError("REPORT_MARKET_FORECASTS_REQUIRED")
        if not isinstance(self.kickoff_utc, datetime) or self.kickoff_utc.tzinfo is None or self.kickoff_utc.utcoffset() is None:
            raise ValueError("REPORT_KICKOFF_MUST_BE_TIMEZONE_AWARE")
        object.__setattr__(self, "kickoff_utc", self.kickoff_utc.astimezone(timezone.utc))
        providers = tuple(dict.fromkeys(self.source_provider_ids))
        if not providers:
            raise ValueError("REPORT_SOURCE_PROVIDER_REQUIRED")
        if any(not isinstance(provider, str) or provider not in PROVIDER_ATTRIBUTION_RULES for provider in providers):
            raise ValueError("REPORT_SOURCE_PROVIDER_UNKNOWN_OR_UNMAPPED")
        object.__setattr__(self, "source_provider_ids", providers)


@dataclass(frozen=True, slots=True)
class CertifiedDailyReport:
    report_date_wat: date
    generated_at_utc: datetime
    delivery_deadline_utc: datetime
    certification_id: str
    prediction_certification: PredictionReleaseCertification
    value_bet_certification: ReleaseCertification | None
    value_bets_enabled: bool
    source_attributions: tuple[str, ...]
    fixtures: tuple[PublishedFixture, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.report_date_wat, date) or isinstance(self.report_date_wat, datetime):
            raise ValueError("REPORT_DATE_WAT_INVALID")
        if not isinstance(self.certification_id, str) or not self.certification_id.strip():
            raise ValueError("REPORT_CERTIFICATION_ID_REQUIRED")
        if not isinstance(self.generated_at_utc, datetime) or self.generated_at_utc.tzinfo is None or self.generated_at_utc.utcoffset() is None:
            raise ValueError("REPORT_GENERATED_AT_MUST_BE_AWARE")
        if not isinstance(self.delivery_deadline_utc, datetime) or self.delivery_deadline_utc.tzinfo is None or self.delivery_deadline_utc.utcoffset() is None:
            raise ValueError("REPORT_DELIVERY_DEADLINE_MUST_BE_AWARE")
        generated = self.generated_at_utc.astimezone(timezone.utc)
        deadline = self.delivery_deadline_utc.astimezone(timezone.utc)
        object.__setattr__(self, "generated_at_utc", generated)
        object.__setattr__(self, "delivery_deadline_utc", deadline)
        if deadline != datetime.combine(self.report_date_wat, time(6, 0), tzinfo=WAT).astimezone(timezone.utc):
            raise ValueError("REPORT_DEADLINE_MUST_BE_0600_WAT")
        if generated >= deadline:
            raise ValueError("REPORT_GENERATED_AFTER_0600_WAT_DEADLINE")
        if generated.astimezone(WAT).date() != self.report_date_wat:
            raise ValueError("REPORT_GENERATION_DATE_WAT_MISMATCH")
        if not isinstance(self.prediction_certification, PredictionReleaseCertification) or not self.prediction_certification.passed:
            raise ValueError("REPORT_PREDICTION_RELEASE_CERTIFICATION_REQUIRED")
        if self.value_bet_certification is not None and not isinstance(self.value_bet_certification, ReleaseCertification):
            raise ValueError("REPORT_VALUE_BET_CERTIFICATION_TYPE_INVALID")
        expected_value_bets_enabled = bool(self.value_bet_certification and self.value_bet_certification.passed)
        if type(self.value_bets_enabled) is not bool or self.value_bets_enabled != expected_value_bets_enabled:
            raise ValueError("REPORT_VALUE_BET_STATE_CONFLICTS_WITH_CERTIFICATION")
        attributions = tuple(self.source_attributions)
        if any(not isinstance(item, str) or not item.strip() for item in attributions):
            raise ValueError("REPORT_SOURCE_ATTRIBUTIONS_INVALID")
        object.__setattr__(self, "source_attributions", tuple(dict.fromkeys(attributions)))
        rows = tuple(self.fixtures)
        if any(not isinstance(row, PublishedFixture) for row in rows):
            raise ValueError("REPORT_FIXTURE_TYPE_INVALID")
        object.__setattr__(self, "fixtures", rows)
        if len(rows) > MAX_DAILY_FIXTURES:
            raise ValueError("REPORT_FIXTURE_CAP_EXCEEDED")
        ids = [row.fixture_id for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("REPORT_DUPLICATE_FIXTURE_IDS")
        if any(row.kickoff_utc <= generated for row in rows):
            raise ValueError("REPORT_CONTAINS_STARTED_OR_PAST_FIXTURE")
        if any(row.kickoff_utc.astimezone(WAT).date() != self.report_date_wat for row in rows):
            raise ValueError("REPORT_FIXTURE_OUTSIDE_WAT_REPORT_DATE")
        for fixture in rows:
            if not self.value_bets_enabled and fixture.value_bet_verdict != "LOCKED — NOT CERTIFIED":
                raise ValueError("REPORT_UNCERTIFIED_VALUE_BET_MUST_REMAIN_LOCKED")
            for provider in fixture.source_provider_ids:
                required_attribution = PROVIDER_ATTRIBUTION_RULES[provider]
                if required_attribution and required_attribution not in self.source_attributions:
                    raise ValueError(f"REPORT_REQUIRED_PROVIDER_ATTRIBUTION_MISSING:{provider}")
        if tuple(sorted(rows, key=lambda row: (row.kickoff_utc, row.fixture_id))) != rows:
            raise ValueError("REPORT_FIXTURES_MUST_BE_CHRONOLOGICALLY_SORTED")


def build_certified_daily_report(
    *,
    report_date_wat: date,
    generated_at_utc: datetime,
    certification: PredictionReleaseCertification,
    certification_id: str,
    fixtures: tuple[PublishedFixture, ...],
    value_bet_certification: ReleaseCertification | None = None,
    source_attributions: tuple[str, ...] = (),
) -> CertifiedDailyReport:
    if not isinstance(certification, PredictionReleaseCertification) or not certification.passed:
        raise ValueError("REPORT_PREDICTION_RELEASE_CERTIFICATION_REQUIRED")
    if value_bet_certification is not None and not isinstance(value_bet_certification, ReleaseCertification):
        raise ValueError("REPORT_VALUE_BET_CERTIFICATION_TYPE_INVALID")
    value_bets_enabled = bool(value_bet_certification and value_bet_certification.passed)
    if not certification_id or not certification_id.strip():
        raise ValueError("REPORT_CERTIFICATION_ID_REQUIRED")
    ordered = tuple(sorted(fixtures, key=lambda row: (row.kickoff_utc, row.fixture_id)))
    supplied_attributions = set(source_attributions)
    for fixture in ordered:
        for provider in fixture.source_provider_ids:
            required_attribution = PROVIDER_ATTRIBUTION_RULES[provider]
            if required_attribution and required_attribution not in supplied_attributions:
                raise ValueError(f"REPORT_REQUIRED_PROVIDER_ATTRIBUTION_MISSING:{provider}")
    if not value_bets_enabled:
        ordered = tuple(replace(row, value_bet_verdict="LOCKED — NOT CERTIFIED") for row in ordered)
    deadline = datetime.combine(report_date_wat, time(6, 0), tzinfo=WAT).astimezone(timezone.utc)
    return CertifiedDailyReport(
        report_date_wat=report_date_wat,
        generated_at_utc=generated_at_utc,
        delivery_deadline_utc=deadline,
        certification_id=certification_id,
        prediction_certification=certification,
        value_bet_certification=value_bet_certification,
        value_bets_enabled=value_bets_enabled,
        source_attributions=tuple(source_attributions),
        fixtures=ordered,
    )


def website_report_payload(report: CertifiedDailyReport) -> dict[str, Any]:
    """Return a stable JSON-ready report payload for the existing website API."""
    return {
        "schema_version": 1,
        "report_date_wat": report.report_date_wat.isoformat(),
        "generated_at_utc": report.generated_at_utc.isoformat(),
        "delivery_deadline_utc": report.delivery_deadline_utc.isoformat(),
        "certification_id": report.certification_id,
        "value_bets_enabled": report.value_bets_enabled,
        "source_attributions": list(report.source_attributions),
        "fixture_count": len(report.fixtures),
        "fixtures": [
            {
                **{key: value for key, value in asdict(row).items() if key not in {"forecasts", "source_provider_ids"}},
                "source_provider_ids": list(row.source_provider_ids),
                "kickoff_utc": row.kickoff_utc.isoformat(),
                "kickoff_wat": row.kickoff_utc.astimezone(WAT).isoformat(),
                "forecasts": {
                    key: str(value)
                    for key, value in asdict(row.forecasts).items()
                },
            }
            for row in report.fixtures
        ],
    }


def telegram_report_text(report: CertifiedDailyReport) -> str:
    """Render the concise public report; transport/chunking remains external."""
    lines = [
        "🔔 🆕 NEW VELTRIX UPDATE",
        f"Date: {report.report_date_wat.isoformat()} (WAT)",
        f"Qualified fixtures: {len(report.fixtures)}",
        f"Value betting: {'ENABLED' if report.value_bets_enabled else 'LOCKED — NOT CERTIFIED'}",
        "",
    ]
    if not report.fixtures:
        lines.append("No fixtures passed the publication gate today.")
    else:
        for index, fixture in enumerate(report.fixtures, start=1):
            local_kickoff = fixture.kickoff_utc.astimezone(WAT).strftime("%H:%M")
            f = fixture.forecasts
            lines.extend([
                f"{index}. {fixture.home_team} vs {fixture.away_team}",
                f"{fixture.competition} · {local_kickoff} WAT",
                f"Verdict: {fixture.verdict}",
                f"1X2: H {f.p_home:.0%} | D {f.p_draw:.0%} | A {f.p_away:.0%}",
                f"BTTS: {f.p_btts_yes:.0%} YES",
                f"O/U {f.total_line}: {f.p_over:.0%} OVER",
                f"AI insight: {fixture.ai_insight}",
                f"Value bet: {fixture.value_bet_verdict}",
                "",
            ])
    if report.source_attributions:
        lines.extend(["", *report.source_attributions])
    return "\n".join(lines).rstrip()
