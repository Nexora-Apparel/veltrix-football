"""Transactional PostgreSQL writer for immutable The Odds API quote evidence.

All observations in a capture are admitted and inserted in one transaction.
Raw response bytes, provider request linkage, fixture crosswalk and current
rights evidence are re-read from PostgreSQL; caller-supplied metadata is not
trusted as a substitute for persisted evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Callable

from veltrix_v2.providers.odds_api_v4.evidence import (
    FixtureCrosswalk, QuoteRights, evaluate_quote_admission,
)


@dataclass(frozen=True)
class QuoteWriteContext:
    fixture_id: int
    crosswalk_version_id: int
    response_id: int
    capture_request_id: int
    rights_approval_id: str
    raw_response: bytes
    prediction_cutoff_at: datetime | None
    kickoff_at: datetime


@dataclass(frozen=True)
class QuoteWriteResult:
    inserted: int
    duplicates: int
    rejected: int


class PostgresOddsQuoteStore:
    """Persist quote observations after revalidating every linked evidence row."""

    def __init__(self, connect: Callable):
        if not callable(connect):
            raise ValueError("DATABASE_CONNECT_FACTORY_REQUIRED")
        self._connect = connect

    def write_capture(self, parsed_capture, context: QuoteWriteContext) -> QuoteWriteResult:
        if not isinstance(context, QuoteWriteContext):
            raise ValueError("QUOTE_WRITE_CONTEXT_REQUIRED")
        if not isinstance(context.raw_response, bytes):
            raise ValueError("RAW_RESPONSE_BYTES_REQUIRED")
        digest = hashlib.sha256(context.raw_response).hexdigest()
        if digest != parsed_capture.response_sha256:
            raise ValueError("RAW_RESPONSE_HASH_MISMATCH")
        if not parsed_capture.observations:
            return QuoteWriteResult(0, 0, len(parsed_capture.diagnostics))

        inserted = duplicates = rejected = 0
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT provider, source_id, response_sha256, raw_body
                       FROM provider_responses WHERE id=%s FOR SHARE""",
                    (context.response_id,),
                )
                response = cur.fetchone()
                if response is None or response[0] != "the_odds_api" or response[1] != "odds_api_v4":
                    raise ValueError("PERSISTED_PROVIDER_RESPONSE_IDENTITY_MISMATCH")
                if response[2].strip() != digest or bytes(response[3]) != context.raw_response:
                    raise ValueError("PERSISTED_RAW_RESPONSE_HASH_OR_BYTES_MISMATCH")

                cur.execute(
                    """SELECT provider, source_id, response_id
                       FROM provider_capture_requests
                       WHERE capture_request_id=%s FOR SHARE""",
                    (context.capture_request_id,),
                )
                request = cur.fetchone()
                if request != ("the_odds_api", "odds_api_v4", context.response_id):
                    raise ValueError("CAPTURE_REQUEST_RESPONSE_LINK_MISMATCH")

                cur.execute(
                    """SELECT provider, source_id, provider_entity_id, canonical_entity_key,
                              entity_type, mapping_status, valid_from, valid_until
                       FROM entity_crosswalk_versions
                       WHERE crosswalk_version_id=%s FOR SHARE""",
                    (context.crosswalk_version_id,),
                )
                mapping = cur.fetchone()
                if mapping is None:
                    raise ValueError("FIXTURE_CROSSWALK_MISSING")
                try:
                    mapped_fixture_id = int(mapping[3])
                except (TypeError, ValueError):
                    raise ValueError("FIXTURE_CROSSWALK_CANONICAL_ID_INVALID")
                crosswalk = FixtureCrosswalk(
                    provider=mapping[0], source_id=mapping[1],
                    provider_event_id=mapping[2], fixture_id=mapped_fixture_id,
                    entity_type=mapping[4], status=mapping[5],
                    valid_from=mapping[6], valid_until=mapping[7],
                    crosswalk_version_id=context.crosswalk_version_id,
                )
                if mapped_fixture_id != context.fixture_id:
                    raise ValueError("FIXTURE_CROSSWALK_FIXTURE_ID_MISMATCH")

                cur.execute(
                    """SELECT approval_id, provider, source_id, competition_scope, data_type,
                              status, permitted_uses, valid_from, reviewed_at,
                              valid_until, evidence_sha256
                       FROM source_approvals WHERE approval_id=%s FOR SHARE""",
                    (context.rights_approval_id,),
                )
                approval = cur.fetchone()
                if approval is None:
                    raise ValueError("QUOTE_RIGHTS_APPROVAL_MISSING")
                if approval[4] != "odds_quote":
                    raise ValueError("QUOTE_RIGHTS_DATA_TYPE_MISMATCH")
                permitted = approval[6] if isinstance(approval[6], (list, tuple)) else ()
                allowed_sports = set((approval[3] or "").split(","))
                cur.execute(
                    """SELECT status, effective_at FROM source_approval_status_events
                       WHERE approval_id=%s
                       ORDER BY effective_at DESC, event_id DESC LIMIT 1""",
                    (context.rights_approval_id,),
                )
                status_event = cur.fetchone()
                status = status_event[0] if status_event else approval[5]
                effective_at = status_event[1] if status_event else approval[7]
                rights = QuoteRights(
                    approval_id=approval[0], provider=approval[1], source_id=approval[2],
                    status=status, permitted_uses=frozenset(permitted),
                    effective_at=effective_at, recorded_at=approval[8],
                    valid_until=approval[9], evidence_sha256=approval[10].strip(),
                )

                for quote in parsed_capture.observations:
                    if quote.sport_key not in allowed_sports:
                        rejected += 1
                        continue
                    admission = evaluate_quote_admission(
                        quote=quote, crosswalk=crosswalk, rights=rights,
                        fixture_id=context.fixture_id,
                        prediction_cutoff_at=context.prediction_cutoff_at,
                        kickoff_at=context.kickoff_at,
                        evaluated_at=datetime.now(tz=quote.retrieved_at.tzinfo),
                    )
                    if not admission.admitted or admission.observation_key is None:
                        rejected += 1
                        continue
                    cur.execute(
                        """INSERT INTO odds_quote_observations (
                               observation_key, provider, source_id, sport_key,
                               provider_event_id, fixture_id, crosswalk_version_id,
                               response_id, capture_request_id, bookmaker_key,
                               bookmaker_title, market_key, selection_name,
                               selection_key, line_point, decimal_price,
                               source_timestamp_raw, source_published_at, retrieved_at,
                               response_sha256, rights_approval_id, rights_evidence_sha256
                           ) VALUES (
                               %s,'the_odds_api','odds_api_v4',%s,%s,%s,%s,%s,%s,
                               %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                           ) ON CONFLICT (observation_key) DO NOTHING
                           RETURNING odds_quote_observation_id""",
                        (
                            admission.observation_key, quote.sport_key,
                            quote.provider_event_id, context.fixture_id,
                            context.crosswalk_version_id, context.response_id,
                            context.capture_request_id, quote.bookmaker_key,
                            quote.bookmaker_title, quote.market_key,
                            quote.selection_name, quote.selection_key, quote.point,
                            quote.decimal_price, quote.source_timestamp_raw,
                            quote.source_published_at, quote.retrieved_at,
                            quote.response_sha256, context.rights_approval_id,
                            rights.evidence_sha256,
                        ),
                    )
                    if cur.fetchone() is None:
                        duplicates += 1
                    else:
                        inserted += 1
        return QuoteWriteResult(inserted, duplicates, rejected)
