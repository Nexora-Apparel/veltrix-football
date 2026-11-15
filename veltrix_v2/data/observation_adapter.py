"""Convert validated provider fixture contracts into model observations and targets.

Provider IDs are namespaced, not merged by display name. Historical rows with
an explicit retrieval timestamp may support future forecasts, but the
point_in_time_certifiable flag is carried through unchanged. Walk-forward
evaluation excludes rows whose source contract does not certify PIT eligibility.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import Any, Mapping

UTC = timezone.utc

from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture
from veltrix_v2.models.poisson import MatchObservation
from veltrix_v2.models.engine import PredictionTarget


def historical_fixture_to_observation(
    fixture: HistoricalFixture,
    *,
    team_crosswalk: Mapping[str, str] | None = None,
    competition_crosswalk: Mapping[str, str] | None = None,
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
    if (team_crosswalk is None) != (competition_crosswalk is None):
        raise ValueError("HISTORICAL_FIXTURE_CROSSWALK_PAIR_REQUIRED")
    if team_crosswalk is None:
        competition_id = f"{fixture.source_id}:{fixture.provider_competition_id}"
        home_team_id = f"{fixture.source_id}:{fixture.provider_home_team_id}"
        away_team_id = f"{fixture.source_id}:{fixture.provider_away_team_id}"
    else:
        competition_id = competition_crosswalk.get(str(fixture.provider_competition_id))
        home_team_id = team_crosswalk.get(str(fixture.provider_home_team_id))
        away_team_id = team_crosswalk.get(str(fixture.provider_away_team_id))
        if not all(isinstance(value, str) and value.strip()
                   for value in (competition_id, home_team_id, away_team_id)):
            return None
        if home_team_id == away_team_id:
            return None
    return MatchObservation(
        fixture_id=f"{fixture.source_id}:{fixture.provider_fixture_id}",
        competition_id=competition_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
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


def historical_fixture_to_target(
    fixture: HistoricalFixture,
    *,
    team_crosswalk: Mapping[str, str] | None = None,
    competition_crosswalk: Mapping[str, str] | None = None,
) -> PredictionTarget | None:
    """Convert a known future scheduled provider fixture into a prediction target."""
    if not isinstance(fixture, HistoricalFixture):
        raise TypeError("HISTORICAL_FIXTURE_REQUIRED")
    if fixture.status is not FixtureStatus.SCHEDULED:
        return None
    if fixture.kickoff_at_utc <= fixture.retrieved_at_utc:
        return None
    if (team_crosswalk is None) != (competition_crosswalk is None):
        raise ValueError("HISTORICAL_FIXTURE_CROSSWALK_PAIR_REQUIRED")
    if team_crosswalk is None:
        competition_id = f"{fixture.source_id}:{fixture.provider_competition_id}"
        home_team_id = f"{fixture.source_id}:{fixture.provider_home_team_id}"
        away_team_id = f"{fixture.source_id}:{fixture.provider_away_team_id}"
    else:
        competition_id = competition_crosswalk.get(str(fixture.provider_competition_id))
        home_team_id = team_crosswalk.get(str(fixture.provider_home_team_id))
        away_team_id = team_crosswalk.get(str(fixture.provider_away_team_id))
        if not all(isinstance(value, str) and value.strip()
                   for value in (competition_id, home_team_id, away_team_id)):
            return None
        if home_team_id == away_team_id:
            return None
    return PredictionTarget(
        fixture_id=f"{fixture.source_id}:{fixture.provider_fixture_id}",
        competition_id=competition_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
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
    *,
    team_crosswalk: Mapping[str, str],
    competition_crosswalk: Mapping[str, str],
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
        raw_match_date = payload.get("match_date")
        if isinstance(raw_match_date, datetime):
            match_date = raw_match_date.date()
        elif isinstance(raw_match_date, date):
            match_date = raw_match_date
        else:
            raw_match_date = str(raw_match_date)
            try:
                match_date = date.fromisoformat(raw_match_date)
            except ValueError:
                match_date = datetime.fromisoformat(raw_match_date.replace("Z", "+00:00")).date()
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
    canonical_competition = competition_crosswalk.get(comp)
    canonical_home = team_crosswalk.get(home_id)
    canonical_away = team_crosswalk.get(away_id)
    if not all(isinstance(value, str) and value.strip()
               for value in (canonical_competition, canonical_home, canonical_away)):
        return None
    if canonical_home == canonical_away:
        return None
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
               for value in (payload_hash, manifest_hash, response_hash)):
        return None
    if isinstance(response_id, bool) or not isinstance(response_id, int) or response_id <= 0:
        return None

    return MatchObservation(
        fixture_id=f"{OPENPLAY_SOURCE_ID}:{match_id}",
        competition_id=canonical_competition,
        home_team_id=canonical_home,
        away_team_id=canonical_away,
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


def load_openplay_match_observations(connection) -> tuple[MatchObservation, ...]:
    """Load only rights-approved, resolved-identity OpenPlay result snapshots.

    This is a read-only staging loader. PIT eligibility is still evaluated
    separately for every prediction cutoff by the chronological evaluator.
    """
    if connection is None:
        raise ValueError("OPENPLAY_DATABASE_CONNECTION_REQUIRED")
    cursor = connection.cursor()
    try:
        cursor.execute("""
            SELECT s.provider,s.source_id,s.entity_type,s.provider_entity_id,
                   s.payload_sha256,s.retrieved_at,s.payload,s.available_at,
                   s.availability_basis,s.rights_approval_id,s.provider_response_id,
                   s.point_in_time_certifiable,s.source_published_at,s.recorded_at,
                   s.source_timestamp_basis,
                   hc.canonical_entity_key AS canonical_home_team,
                   ac.canonical_entity_key AS canonical_away_team,
                   cc.canonical_entity_key AS canonical_competition
            FROM source_observations s
            JOIN entity_crosswalk_versions hc
              ON hc.entity_type='TEAM' AND hc.provider=s.provider
             AND hc.source_id=s.source_id
             AND hc.provider_entity_id=s.payload->>'home_team_id'
             AND hc.mapping_status='RESOLVED'
             AND hc.mapping_method='EXACT_NAME_AND_COMPETITION_OVERLAP'
            JOIN entity_crosswalk_versions ac
              ON ac.entity_type='TEAM' AND ac.provider=s.provider
             AND ac.source_id=s.source_id
             AND ac.provider_entity_id=s.payload->>'away_team_id'
             AND ac.mapping_status='RESOLVED'
             AND ac.mapping_method='EXACT_NAME_AND_COMPETITION_OVERLAP'
            JOIN entity_crosswalk_versions cc
              ON cc.entity_type='COMPETITION' AND cc.provider=s.provider
             AND cc.source_id=s.source_id
             AND cc.provider_entity_id=s.payload->>'competition_code'
             AND cc.mapping_status='RESOLVED'
             AND cc.mapping_method='EXPLICIT_REGION_NAME_ALIAS'
            JOIN source_approvals a
              ON a.approval_id=s.rights_approval_id
             AND a.status='APPROVED'
             AND a.commercial_use_allowed=FALSE
             AND a.permitted_uses @> '["model_training"]'::jsonb
            WHERE s.provider=%s AND s.source_id=%s
              AND s.entity_type='match_result_snapshot'
              AND s.point_in_time_certifiable IS TRUE
              AND s.source_timestamp_basis='documented_guarantee'
              AND s.availability_basis='openplay_page_saved_at_utc_v1'
            ORDER BY s.id
        """, (OPENPLAY_PROVIDER, OPENPLAY_SOURCE_ID))
        rows = cursor.fetchall()
    finally:
        cursor.close()

    observations: list[MatchObservation] = []
    for row in rows:
        (
            provider, source_id, entity_type, provider_entity_id, payload_sha256,
            retrieved_at, payload, available_at, availability_basis, rights_approval_id,
            provider_response_id, point_in_time_certifiable, source_published_at,
            recorded_at, source_timestamp_basis, canonical_home_team,
            canonical_away_team, canonical_competition,
        ) = row
        if not isinstance(payload, Mapping):
            continue
        home_source_id = str(payload.get("home_team_id") or "")
        away_source_id = str(payload.get("away_team_id") or "")
        competition_source_id = str(payload.get("competition_code") or "")
        observation = openplay_match_snapshot_to_observation(
            {
                "provider": provider, "source_id": source_id,
                "entity_type": entity_type, "provider_entity_id": provider_entity_id,
                "payload_sha256": payload_sha256, "retrieved_at": retrieved_at,
                "recorded_at": recorded_at, "available_at": available_at,
                "source_published_at": source_published_at,
                "availability_basis": availability_basis,
                "source_timestamp_basis": source_timestamp_basis,
                "rights_approval_id": rights_approval_id,
                "provider_response_id": provider_response_id,
                "point_in_time_certifiable": point_in_time_certifiable,
                "payload": payload,
            },
            team_crosswalk={
                home_source_id: str(canonical_home_team),
                away_source_id: str(canonical_away_team),
            },
            competition_crosswalk={
                competition_source_id: str(canonical_competition),
            },
        )
        if observation is not None:
            observations.append(observation)
    return tuple(observations)
