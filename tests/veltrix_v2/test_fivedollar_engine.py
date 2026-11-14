from datetime import datetime, timedelta, timezone
import hashlib
import json

from veltrix_v2.data.contracts import (
    ApprovalStatus, DataUsePurpose, FixtureStatus, HistoricalFixture, SourceApproval,
)
from veltrix_v2.data.fivedollar_engine import build_fivedollar_forecast_batch

UTC = timezone.utc
CUTOFF = datetime(2026, 11, 14, 12, tzinfo=UTC)
APPROVAL_ID = "approval-5dollar-community-fixture-result-2026-11"


def approval(scope="4160026622"):
    return SourceApproval(
        approval_id=APPROVAL_ID, provider="5DollarFootballAPI",
        source_id="5dollarfootballapi", competition_scope=scope,
        data_type="fixture_result", status=ApprovalStatus.APPROVED,
        permitted_uses=frozenset({
            DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE,
            DataUsePurpose.MODEL_TRAINING, DataUsePurpose.CACHE,
        }),
        commercial_use_allowed=True, terms_url="https://5dollarfootballapi.com/terms",
        terms_version="October 2026", evidence_uri="https://example.org/terms-review",
        evidence_sha256="a" * 64, rights_basis="TERMS",
        reviewed_at_utc=datetime(2026, 11, 12, tzinfo=UTC),
        reviewer_id="test-reviewer", valid_from_utc=datetime(2026, 11, 12, tzinfo=UTC),
    )


def fixture(i, *, status=FixtureStatus.FINISHED, kickoff=None, retrieved=None,
            competition="4160026622", approval_id=APPROVAL_ID, home="101", away="102"):
    kickoff = kickoff or datetime(2026, 8, 1, tzinfo=UTC) + timedelta(days=i)
    retrieved = retrieved or CUTOFF - timedelta(hours=1)
    finished = status is FixtureStatus.FINISHED
    payload = {
        "id": str(i), "status": status.value,
        "league": {"id": competition, "name": "England Premier League"},
        "teams": {"home": {"id": home, "name": "Home"}, "away": {"id": away, "name": "Away"}},
        "kickoff_utc": kickoff.isoformat(),
        "goals": {"home": 2, "away": 1} if finished else None,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return HistoricalFixture(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        provider_fixture_id=str(i), provider_competition_id=competition,
        provider_home_team_id=home, provider_away_team_id=away,
        competition_name="England Premier League", home_team_name="Home", away_team_name="Away",
        kickoff_at_utc=kickoff, season_key="2026-2027", status=status,
        home_score=2 if finished else None, away_score=1 if finished else None,
        payload=payload, payload_sha256=digest, retrieved_at_utc=retrieved,
        source_event_time_utc=kickoff,
        available_at_utc=kickoff + timedelta(days=4) if finished else None,
        availability_basis="provider_finished_status_conservative_4d" if finished else "not_settled",
        point_in_time_certifiable=False, rights_approval_id=approval_id,
    )


def test_builds_forecasts_from_approved_finished_history_and_future_targets():
    history = [
        fixture(i, home=str(100 + (i % 6)), away=str(101 + (i % 6)))
        for i in range(120)
    ]
    # Ensure the target teams are represented in the competition history.
    target_fixture = fixture(
        999, status=FixtureStatus.SCHEDULED,
        kickoff=CUTOFF + timedelta(hours=5),
        retrieved=CUTOFF - timedelta(minutes=10),
        home="100", away="101",
    )
    report = build_fivedollar_forecast_batch(
        history + [target_fixture], approval=approval(), cutoff_at=CUTOFF
    )
    assert report.observation_count == 120
    assert report.target_count == 1
    assert report.prediction_report.forecast_count == 1
    assert not report.prediction_report.forecasts[0].model.publishable


def test_recent_results_before_four_day_availability_are_excluded():
    recent = fixture(200, kickoff=CUTOFF - timedelta(days=2))
    scheduled = fixture(201, status=FixtureStatus.SCHEDULED,
                        kickoff=CUTOFF + timedelta(hours=2),
                        retrieved=CUTOFF - timedelta(minutes=5))
    report = build_fivedollar_forecast_batch(
        [recent, scheduled], approval=approval(), cutoff_at=CUTOFF
    )
    assert report.observation_count == 0
    assert report.skipped_unavailable_results == 1
    assert report.prediction_report.skipped_no_history == 1


def test_unapproved_competition_and_wrong_approval_reference_are_skipped():
    rows = [
        fixture(1, competition="999999"),
        fixture(2, approval_id="wrong-approval"),
    ]
    report = build_fivedollar_forecast_batch(rows, approval=approval(), cutoff_at=CUTOFF)
    assert report.skipped_rights == 2
    assert report.observation_count == 0


def test_duplicate_source_fixture_ids_are_excluded_in_full():
    duplicate = fixture(1)
    report = build_fivedollar_forecast_batch(
        [duplicate, duplicate], approval=approval(), cutoff_at=CUTOFF
    )
    assert report.skipped_duplicate_source_fixtures == 2
    assert report.observation_count == 0


def test_unapproved_source_or_unapproved_use_fails_closed():
    unapproved = SourceApproval(
        approval_id=APPROVAL_ID, provider="5DollarFootballAPI",
        source_id="5dollarfootballapi", competition_scope="4160026622",
        data_type="fixture_result", status=ApprovalStatus.PROVISIONAL,
        permitted_uses=frozenset({DataUsePurpose.COLLECTION}),
        commercial_use_allowed=False, terms_url=None, terms_version=None,
        evidence_uri=None, evidence_sha256=None, rights_basis=None,
        reviewed_at_utc=None, reviewer_id=None, valid_from_utc=datetime(2026, 11, 12, tzinfo=UTC),
    )
    import pytest
    with pytest.raises(ValueError, match="FIVEDOLLAR_SOURCE_APPROVAL_NOT_APPROVED"):
        build_fivedollar_forecast_batch([], approval=unapproved, cutoff_at=CUTOFF)
