"""End-to-end offline odds event identity, quote extraction and market mapping."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from veltrix_v2.domain.identity import CanonicalFixtureIdentity
from veltrix_v2.identity.odds_link import (
    OddsFixtureLinkDecision,
    OddsFixtureLinkStatus,
    ProviderOddsEventIdentity,
    VerifiedTeamNameAlias,
    resolve_odds_event,
)
from veltrix_v2.identity.registry import ProviderCompetitionMapping
from veltrix_v2.ingestion.ports import RawProviderRecord, StoredSourceRecord
from veltrix_v2.odds.contracts import ProviderOddsQuote, RejectedOddsQuote
from veltrix_v2.odds.market_mapping import VerifiedMarketKeyMapping, NormalizedOddsQuote
from veltrix_v2.odds.market_normalization import map_provider_quote
from veltrix_v2.odds.normalization import normalize_event_odds


@dataclass(frozen=True, slots=True)
class RejectedCanonicalOddsQuote:
    provider_event_id: str
    bookmaker_key: str | None
    market_key: str | None
    outcome_name: str | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class OddsEventProcessingResult:
    fixture_link: OddsFixtureLinkDecision
    normalized_quotes: tuple[NormalizedOddsQuote, ...]
    rejected_quotes: tuple[RejectedCanonicalOddsQuote, ...]
    raw_response_sha256: str


def _event_identity(raw: RawProviderRecord) -> ProviderOddsEventIdentity:
    try:
        payload = json.loads(raw.raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ODDS_RESPONSE_INVALID_JSON") from exc
    events = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    event = next(
        (
            item for item in events
            if isinstance(item, dict)
            and str(item.get("id")) == str(raw.provider_fixture_id)
        ),
        None,
    )
    if event is None:
        raise ValueError("PROVIDER_EVENT_ID_NOT_FOUND")
    kickoff_value = event.get("commence_time")
    if not isinstance(kickoff_value, str):
        raise ValueError("ODDS_EVENT_KICKOFF_MISSING")
    try:
        kickoff = datetime.fromisoformat(kickoff_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ODDS_EVENT_KICKOFF_INVALID") from exc
    if kickoff.tzinfo is None or kickoff.utcoffset() is None:
        raise ValueError("ODDS_EVENT_KICKOFF_NOT_TIMEZONE_AWARE")
    if str(event.get("sport_key")) != str(raw.provider_competition_id):
        raise ValueError("PROVIDER_COMPETITION_ID_MISMATCH")
    return ProviderOddsEventIdentity(
        provider=raw.provider,
        source_id=raw.source_id,
        provider_event_id=str(raw.provider_fixture_id),
        provider_competition_id=str(raw.provider_competition_id),
        home_team_name=str(event.get("home_team") or ""),
        away_team_name=str(event.get("away_team") or ""),
        kickoff_at_utc=kickoff,
    )


def process_odds_event_record(
    raw: RawProviderRecord,
    stored: StoredSourceRecord,
    competition_mappings: tuple[ProviderCompetitionMapping, ...],
    home_aliases: tuple[VerifiedTeamNameAlias, ...],
    away_aliases: tuple[VerifiedTeamNameAlias, ...],
    candidate_fixtures: tuple[CanonicalFixtureIdentity, ...],
    market_mappings: tuple[VerifiedMarketKeyMapping, ...],
    *,
    evaluated_at_utc: datetime,
    kickoff_tolerance_minutes: int = 15,
) -> OddsEventProcessingResult:
    """Only emit canonical odds after exact event, team, competition and market links."""
    if raw.raw_payload_sha256 != stored.raw_payload_sha256:
        raise ValueError("STORED_RAW_PAYLOAD_DIGEST_MISMATCH")
    if raw.provider_fixture_id is None or raw.provider_competition_id is None:
        raise ValueError("PROVIDER_ODDS_EVENT_IDS_MISSING")

    event = _event_identity(raw)
    link = resolve_odds_event(
        event, competition_mappings, home_aliases, away_aliases,
        candidate_fixtures, evaluated_at_utc=evaluated_at_utc,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
    )
    digest = raw.raw_payload_sha256
    if link.status is not OddsFixtureLinkStatus.MATCHED:
        return OddsEventProcessingResult(
            link, (), (
                RejectedCanonicalOddsQuote(
                    event.provider_event_id, None, None, None,
                    "ODDS_EVENT_FIXTURE_LINK_UNRESOLVED",
                ),
            ), digest,
        )

    extracted = normalize_event_odds(
        raw.raw_payload,
        provider=raw.provider,
        source_id=raw.source_id,
        provider_event_id=event.provider_event_id,
        provider_competition_id=event.provider_competition_id,
        source_record_id=stored.source_record_id,
        fetched_at_utc=datetime.fromisoformat(
            # Fetch time is supplied by the immutable source record.
            raw_fetched_at := raw_fetched_at_iso(raw)
        ),
    )
    accepted: list[NormalizedOddsQuote] = []
    rejected: list[RejectedCanonicalOddsQuote] = []
    for quote in extracted.quotes:
        decision = map_provider_quote(
            quote, market_mappings, link, evaluated_at_utc=evaluated_at_utc
        )
        if decision.allowed and decision.normalized_quote is not None:
            accepted.append(decision.normalized_quote)
        else:
            rejected.append(RejectedCanonicalOddsQuote(
                quote.provider_event_id, quote.bookmaker_key,
                quote.provider_market_key, quote.outcome_name,
                decision.reason_code,
            ))
    for item in extracted.rejected:
        rejected.append(RejectedCanonicalOddsQuote(
            item.provider_event_id, item.bookmaker_key,
            item.market_key, item.outcome_name, item.reason_code,
        ))
    return OddsEventProcessingResult(
        link, tuple(accepted), tuple(rejected), digest
    )


def raw_fetched_at_iso(raw: RawProviderRecord) -> str:
    """The source envelope stores fetch time outside the provider payload."""
    fetched = getattr(raw, "fetched_at_utc", None)
    if fetched is None:
        raise ValueError("RAW_PROVIDER_RECORD_FETCH_TIMESTAMP_REQUIRED")
    if fetched.tzinfo is None or fetched.utcoffset() is None:
        raise ValueError("RAW_PROVIDER_RECORD_FETCH_TIMESTAMP_NOT_TIMEZONE_AWARE")
    return fetched.isoformat()
