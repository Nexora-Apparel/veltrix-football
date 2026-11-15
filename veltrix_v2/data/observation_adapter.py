"""Convert validated provider fixture contracts into model observations and targets.

Provider IDs are namespaced, not merged by display name. Historical rows with
an explicit retrieval timestamp may support future forecasts, but the
point_in_time_certifiable flag is carried through unchanged. Walk-forward
evaluation excludes rows whose source contract does not certify PIT eligibility.
"""
from __future__ import annotations

from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture
from veltrix_v2.models.poisson import MatchObservation
from veltrix_v2.models.engine import PredictionTarget


def historical_fixture_to_observation(
    fixture: HistoricalFixture,
) -> MatchObservation | None:
    """Convert a settled, timestamped fixture; return None for unsettled rows."""
    if not isinstance(fixture, HistoricalFixture):
        raise TypeError("HISTORICAL_FIXTURE_REQUIRED")
    if fixture.status is not FixtureStatus.FINISHED:
        return None
    if fixture.home_score is None or fixture.away_score is None:
        return None
    if fixture.available_at_utc is None or fixture.available_at_utc > fixture.retrieved_at_utc:
        return None
    return MatchObservation(
        fixture_id=f"{fixture.source_id}:{fixture.provider_fixture_id}",
        competition_id=f"{fixture.source_id}:{fixture.provider_competition_id}",
        home_team_id=f"{fixture.source_id}:{fixture.provider_home_team_id}",
        away_team_id=f"{fixture.source_id}:{fixture.provider_away_team_id}",
        kickoff_at=fixture.kickoff_at_utc,
        available_at=fixture.available_at_utc,
        recorded_at=fixture.retrieved_at_utc,
        home_goals=fixture.home_score,
        away_goals=fixture.away_score,
        provider=fixture.provider,
        source_id=fixture.source_id,
        availability_basis=fixture.availability_basis,
        point_in_time_certifiable=fixture.point_in_time_certifiable,
        payload_sha256=fixture.payload_sha256,
        rights_approval_id=fixture.rights_approval_id,
        evidence_manifest_sha256=fixture.capture_manifest_sha256,
        capture_evidence_sha256=fixture.response_sha256,
    )


def historical_fixture_to_target(fixture: HistoricalFixture) -> PredictionTarget | None:
    """Convert a known future scheduled provider fixture into a prediction target."""
    if not isinstance(fixture, HistoricalFixture):
        raise TypeError("HISTORICAL_FIXTURE_REQUIRED")
    if fixture.status is not FixtureStatus.SCHEDULED:
        return None
    if fixture.kickoff_at_utc <= fixture.retrieved_at_utc:
        return None
    return PredictionTarget(
        fixture_id=f"{fixture.source_id}:{fixture.provider_fixture_id}",
        competition_id=f"{fixture.source_id}:{fixture.provider_competition_id}",
        home_team_id=f"{fixture.source_id}:{fixture.provider_home_team_id}",
        away_team_id=f"{fixture.source_id}:{fixture.provider_away_team_id}",
        kickoff_at=fixture.kickoff_at_utc,
        provider=fixture.provider,
        source_id=fixture.source_id,
        source_fixture_id=fixture.provider_fixture_id,
        retrieved_at=fixture.retrieved_at_utc,
        payload_sha256=fixture.payload_sha256,
        rights_approval_id=fixture.rights_approval_id,
        provider_competition_id=fixture.provider_competition_id,
        response_sha256=fixture.response_sha256,
        capture_manifest_sha256=fixture.capture_manifest_sha256,
        home_team_name=fixture.home_team_name,
        away_team_name=fixture.away_team_name,
    )


OPENPLAY_PROVIDER = "OpenPlay / WhoScored / Opta"
OPENPLAY_SOURCE_ID = "openplay-data-v0.1.0"
OPENPLAY_APPROVAL_ID = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"
OPENPLAY_TIMESTAMP_EVIDENCE_ID = "openplay-data-v0.1.0:DATA_DICTIONARY.md#matches.scraped_at"
OPENPLAY_TIMESTAMP_EVIDENCE_SHA256 = "24a1037a948afa1759e3bc2babeb8b17b9e1e2dc3c8a8beea2e18f9b5b671279"


def _parse_openplay_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    # The pinned OpenPlay data dictionary documents scraped_at as UTC.
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def openplay_match_snapshot_to_observation(
    source_observation: Mapping[str, Any],
) -> MatchObservation | None:
    """Adapt a hash-bound OpenPlay page snapshot for cutoffs after VELTRIX recorded it.

    The source page-save timestamp is documented as UTC. The actual VELTRIX
    recorded_at is preserved, so cutoffs before import cannot use this archive.
    """
    if not isinstance(source_observation, Mapping):
        return None
    payload = source_observation.get("payload")
    if not isinstance(payload, Mapping):
        return None
    if (
        source_observation.get("provider") != OPENPLAY_PROVIDER
        or source_observation.get("source_id") != OPENPLAY_SOURCE_ID
        or source_observation.get("entity_type") != "match_result_snapshot"
        or source_observation.get("source_timestamp_basis") != "documented_guarantee"
        or source_observation.get("availability_basis") != "openplay_page_saved_at_utc_v1"
        or source_observation.get("point_in_time_certifiable") is not True
        or source_observation.get("rights_approval_id") != OPENPLAY_APPROVAL_ID
        or payload.get("timestamp_guarantee_evidence_id") != OPENPLAY_TIMESTAMP_EVIDENCE_ID
        or payload.get("timestamp_guarantee_evidence_sha256") != OPENPLAY_TIMESTAMP_EVIDENCE_SHA256
        or payload.get("source_timestamp_semantics") != "page_saved_at_utc"
        or payload.get("rights_approval_id") != OPENPLAY_APPROVAL_ID
        or payload.get("commercial_use_allowed") is not False
    ):
        return None

    scraped_at = _parse_openplay_utc(payload.get("scraped_at_utc"))
    available_at = _parse_openplay_utc(source_observation.get("available_at"))
    published_at = _parse_openplay_utc(source_observation.get("source_published_at"))
    recorded_at = _parse_openplay_utc(source_observation.get("recorded_at"))
    retrieved_at = _parse_openplay_utc(source_observation.get("retrieved_at"))
    try:
        match_date = date.fromisoformat(str(payload.get("match_date")))
        home_goals = int(payload.get("home_score_90"))
        away_goals = int(payload.get("away_score_90"))
    except (TypeError, ValueError):
        return None
    if (
        scraped_at is None or available_at is None or published_at is None
        or recorded_at is None or retrieved_at is None
        or scraped_at != available_at or scraped_at != published_at
        or recorded_at < retrieved_at or recorded_at < scraped_at
        or scraped_at < datetime.combine(match_date + timedelta(days=2), datetime.min.time(), tzinfo=UTC)
        or not isinstance(home_goals, int) or not isinstance(away_goals, int)
        or home_goals < 0 or away_goals < 0
    ):
        return None

    match_id = str(payload.get("match_id") or source_observation.get("provider_entity_id") or "")
    comp = str(payload.get("competition_code") or "")
    home_id = str(payload.get("home_team_id") or "")
    away_id = str(payload.get("away_team_id") or "")
    payload_hash = source_observation.get("payload_sha256")
    manifest_hash = payload.get("capture_manifest_sha256")
    response_hash = payload.get("matches_parquet_sha256")
    response_id = source_observation.get("provider_response_id")
    if not all((match_id, comp, home_id, away_id, payload.get("season"), payload.get("xg_model"))):
        return None
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
               for value in (payload_hash, manifest_hash, response_hash)):
        return None
    if isinstance(response_id, bool) or not isinstance(response_id, int) or response_id <= 0:
        return None

    return MatchObservation(
        fixture_id=f"{OPENPLAY_SOURCE_ID}:{match_id}",
        competition_id=f"{OPENPLAY_SOURCE_ID}:{comp}",
        home_team_id=f"{OPENPLAY_SOURCE_ID}:{home_id}",
        away_team_id=f"{OPENPLAY_SOURCE_ID}:{away_id}",
        kickoff_at=None,
        available_at=available_at,
        recorded_at=recorded_at,
        home_goals=home_goals,
        away_goals=away_goals,
        kickoff_date=match_date,
        provider=OPENPLAY_PROVIDER,
        source_id=OPENPLAY_SOURCE_ID,
        availability_basis="openplay_page_saved_at_utc_v1",
        point_in_time_certifiable=True,
        payload_sha256=payload_hash,
        rights_approval_id=OPENPLAY_APPROVAL_ID,
        evidence_manifest_sha256=manifest_hash,
        capture_evidence_sha256=response_hash,
        provider_competition_id=comp,
    )
