"""Exact-identity reconciliation of 5Dollar finished results to V2 shadow targets."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable, Mapping

from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture, SourceApproval
from veltrix_v2.ledger.paper_predictions import PaperLedgerEvent, ProspectivePaperLedger
from veltrix_v2.ledger.paper_predictions import V2_PIT_MODEL_VERSION
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

    predictions: dict[tuple[str, str], list[PaperLedgerEvent]] = {}
    for event in ledger.events:
        if (
            event.event_type == "SHADOW_PREDICTION"
            and event.payload.get("evidence_class") == "PROSPECTIVE_OBSERVED_ONLY"
            and event.payload.get("target_provider") == "5DollarFootballAPI"
        ):
            key = (
                event.payload.get("target_source_id"),
                event.payload.get("target_source_fixture_id"),
            )
            predictions.setdefault(key, []).append(event)
    appended: list[PaperLedgerEvent] = []
    quarantined: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for fixture in fixtures:
        if not isinstance(fixture, HistoricalFixture):
            quarantined.append(("unknown", "SETTLEMENT_FIXTURE_TYPE_INVALID"))
            continue
        key = (fixture.source_id, fixture.provider_fixture_id)
        matching_predictions = predictions.get(key)
        if matching_predictions is None:
            continue
        if key in seen:
            quarantined.append((fixture.provider_fixture_id, "DUPLICATE_PROVIDER_FIXTURE_IN_BATCH"))
            continue
        seen.add(key)
        if fixture.provider != "5DollarFootballAPI" or fixture.status is not FixtureStatus.FINISHED:
            quarantined.append((fixture.provider_fixture_id, "SETTLEMENT_REQUIRES_FINISHED_5DOLLAR_FIXTURE"))
            continue
        identity_matches = all(
            prediction.payload.get(key_name) == expected_value
            for prediction in matching_predictions
            for key_name, expected_value in (
                ("fixture_id", fixture.source_id + ":" + fixture.provider_fixture_id),
                ("competition_id", fixture.source_id + ":" + fixture.provider_competition_id),
                ("home_team_id", fixture.source_id + ":" + fixture.provider_home_team_id),
                ("away_team_id", fixture.source_id + ":" + fixture.provider_away_team_id),
                ("kickoff_at", fixture.kickoff_at_utc.isoformat()),
                ("target_provider_competition_id", fixture.provider_competition_id),
            )
        )
        if not identity_matches:
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
        for prediction in matching_predictions:
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


def reconcile_v2_finished_fixtures(
    ledger: ProspectivePaperLedger,
    fixtures: Iterable[HistoricalFixture],
    approval: SourceApproval,
    *,
    v2_feature_links: Mapping[str, Mapping[str, object]],
    recorded_at: datetime,
) -> tuple[tuple[PaperLedgerEvent, ...], tuple[tuple[str, str], ...]]:
    """Settle only PIT-certified V2 predictions with immutable feature-evidence links."""
    if not isinstance(ledger, ProspectivePaperLedger):
        raise ValueError("PAPER_LEDGER_REQUIRED")
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ValueError("SETTLEMENT_RECORDING_TIMESTAMP_MUST_BE_AWARE")

    predictions: dict[tuple[str,str], list[tuple[PaperLedgerEvent,Mapping[str,object]]]] = {}
    quarantined: list[tuple[str,str]] = []
    for event in ledger.events:
        if event.event_type != "PREDICTION" or event.model_version != V2_PIT_MODEL_VERSION:
            continue
        payload=event.payload
        if (
            payload.get("evidence_class") != "PIT_CERTIFIED"
            or payload.get("point_in_time_certifiable") is not True
            or payload.get("target_provider") != "5DollarFootballAPI"
        ):
            quarantined.append((payload.get("target_source_fixture_id","unknown"),
                                "V2_SETTLEMENT_PREDICTION_NOT_PIT_CERTIFIED"))
            continue
        link=v2_feature_links.get(event.event_sha256)
        if (
            link is None
            or link.get("prediction_event_sha256") != event.event_sha256
            or link.get("forecast_evidence_sha256") != payload.get("evidence_sha256")
            or not link.get("link_sha256")
        ):
            quarantined.append((payload.get("target_source_fixture_id","unknown"),
                                "V2_SETTLEMENT_FEATURE_EVIDENCE_LINK_MISSING_OR_MISMATCHED"))
            continue
        required=("target_source_id","target_source_fixture_id",
                  "target_provider_competition_id","kickoff_at")
        if not all(isinstance(payload.get(key),str) and payload[key].strip() for key in required):
            quarantined.append((payload.get("target_source_fixture_id","unknown"),
                                "V2_SETTLEMENT_TARGET_PROVENANCE_INCOMPLETE"))
            continue
        key=(payload["target_source_id"],payload["target_source_fixture_id"])
        predictions.setdefault(key,[]).append((event,link))

    appended: list[PaperLedgerEvent] = []
    seen: set[tuple[str,str]] = set()
    for fixture in fixtures:
        if not isinstance(fixture,HistoricalFixture):
            quarantined.append(("unknown","SETTLEMENT_FIXTURE_TYPE_INVALID"))
            continue
        key=(fixture.source_id,fixture.provider_fixture_id)
        matching=predictions.get(key)
        if matching is None:
            continue
        if key in seen:
            quarantined.append((fixture.provider_fixture_id,"DUPLICATE_PROVIDER_FIXTURE_IN_BATCH"))
            continue
        seen.add(key)
        if fixture.provider!="5DollarFootballAPI" or fixture.status is not FixtureStatus.FINISHED:
            quarantined.append((fixture.provider_fixture_id,"SETTLEMENT_REQUIRES_FINISHED_5DOLLAR_FIXTURE"))
            continue
        identity_matches=all(
            event.payload.get(field)==expected
            for event,_ in matching
            for field,expected in (
                ("fixture_id",fixture.source_id+":"+fixture.provider_fixture_id),
                ("competition_id",fixture.source_id+":"+fixture.provider_competition_id),
                ("home_team_id",fixture.source_id+":"+fixture.provider_home_team_id),
                ("away_team_id",fixture.source_id+":"+fixture.provider_away_team_id),
                ("kickoff_at",fixture.kickoff_at_utc.isoformat()),
                ("target_provider_competition_id",fixture.provider_competition_id),
            )
        )
        if not identity_matches:
            quarantined.append((fixture.provider_fixture_id,"SETTLEMENT_FIXTURE_IDENTITY_MISMATCH"))
            continue
        if fixture.kickoff_at_utc>recorded_at:
            quarantined.append((fixture.provider_fixture_id,"SETTLEMENT_FIXTURE_NOT_KICKED_OFF"))
            continue
        if fixture.retrieved_at_utc<fixture.kickoff_at_utc or fixture.retrieved_at_utc>recorded_at:
            quarantined.append((fixture.provider_fixture_id,"SETTLEMENT_FIRST_OBSERVED_CLOCK_INVALID"))
            continue
        observed=replace(
            fixture,
            available_at_utc=fixture.retrieved_at_utc,
            availability_basis="collector_first_observed_v1",
            point_in_time_certifiable=False,
        )
        for event,link in matching:
            try:
                settled=settle_from_verified_fixture(
                    ledger,observed,approval,recorded_at=recorded_at,
                    model_version=event.model_version,prediction_feature_link=link,
                )
            except (ValueError,PermissionError) as exc:
                quarantined.append((fixture.provider_fixture_id,str(exc)[:160]))
                continue
            appended.append(settled)
    return tuple(appended),tuple(quarantined)
