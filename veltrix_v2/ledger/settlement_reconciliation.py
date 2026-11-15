"""Exact-identity reconciliation of 5Dollar finished results to V2 shadow targets."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture, SourceApproval
from veltrix_v2.ledger.paper_predictions import PaperLedgerEvent, ProspectivePaperLedger
from veltrix_v2.ledger.settlement import settle_from_verified_fixture


def reconcile_finished_fixtures(
    ledger: ProspectivePaperLedger,
    fixtures: Iterable[HistoricalFixture],
    approval: SourceApproval,
    *,
    recorded_at: datetime,
) -> tuple[tuple[PaperLedgerEvent, ...], tuple[tuple[str, str], ...]]:
    """Append eligible first-observed shadow settlements to an in-memory ledger.

    Unrelated provider rows are ignored. Rows targeting a prediction but failing
    identity, timing, rights or duplicate checks are returned as quarantined
    (fixture ID, stable reason code). This function performs no I/O.
    """
    if not isinstance(ledger, ProspectivePaperLedger):
        raise ValueError("PAPER_LEDGER_REQUIRED")
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ValueError("SETTLEMENT_RECORDING_TIMESTAMP_MUST_BE_AWARE")

    predictions = {
        (event.payload.get("target_source_id"), event.payload.get("target_source_fixture_id")): event
        for event in ledger.events
        if event.event_type == "SHADOW_PREDICTION"
        and event.payload.get("evidence_class") == "PROSPECTIVE_OBSERVED_ONLY"
        and event.payload.get("target_provider") == "5DollarFootballAPI"
    }
    appended: list[PaperLedgerEvent] = []
    quarantined: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for fixture in fixtures:
        if not isinstance(fixture, HistoricalFixture):
            quarantined.append(("unknown", "SETTLEMENT_FIXTURE_TYPE_INVALID"))
            continue
        key = (fixture.source_id, fixture.provider_fixture_id)
        prediction = predictions.get(key)
        if prediction is None:
            continue
        if key in seen:
            quarantined.append((fixture.provider_fixture_id, "DUPLICATE_PROVIDER_FIXTURE_IN_BATCH"))
            continue
        seen.add(key)
        if fixture.provider != "5DollarFootballAPI" or fixture.status is not FixtureStatus.FINISHED:
            quarantined.append((fixture.provider_fixture_id, "SETTLEMENT_REQUIRES_FINISHED_5DOLLAR_FIXTURE"))
            continue
        payload = prediction.payload
        expected = (
            payload.get("fixture_id") == fixture.source_id + ":" + fixture.provider_fixture_id,
            payload.get("competition_id") == fixture.source_id + ":" + fixture.provider_competition_id,
            payload.get("home_team_id") == fixture.source_id + ":" + fixture.provider_home_team_id,
            payload.get("away_team_id") == fixture.source_id + ":" + fixture.provider_away_team_id,
            payload.get("kickoff_at") == fixture.kickoff_at_utc.isoformat(),
            payload.get("target_provider_competition_id") == fixture.provider_competition_id,
        )
        if not all(expected):
            quarantined.append((fixture.provider_fixture_id, "SETTLEMENT_FIXTURE_IDENTITY_MISMATCH"))
            continue
        if fixture.kickoff_at_utc > recorded_at:
            quarantined.append((fixture.provider_fixture_id, "SETTLEMENT_FIXTURE_NOT_KICKED_OFF"))
            continue
        if fixture.retrieved_at_utc < fixture.kickoff_at_utc or fixture.retrieved_at_utc > recorded_at:
            quarantined.append((fixture.provider_fixture_id, "SETTLEMENT_FIRST_OBSERVED_CLOCK_INVALID"))
            continue
        # The provider has no trusted publication timestamp. Replace its
        # conservative proxy with the exact collector first-observed timestamp.
        observed = replace(
            fixture,
            available_at_utc=fixture.retrieved_at_utc,
            availability_basis="collector_first_observed_v1",
            point_in_time_certifiable=False,
        )
        try:
            event = settle_from_verified_fixture(
                ledger, observed, approval, recorded_at=recorded_at,
                model_version=prediction.model_version,
            )
        except (ValueError, PermissionError) as exc:
            quarantined.append((fixture.provider_fixture_id, str(exc)[:160]))
            continue
        appended.append(event)

    return tuple(appended), tuple(quarantined)
