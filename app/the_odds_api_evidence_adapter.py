"""Strict The Odds API event-to-canonical-fixture odds evidence adapter.

Requires an explicit reviewed event crosswalk. It never guesses fixture
identity from team names or kickoff proximity.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import unicodedata
from typing import Any

from app.bookmaker_odds_evidence import (
    BookmakerOddsEvidenceError, MARKET_SELECTIONS, build_odds_observation,
)


class OddsProviderAdapterError(ValueError):
    pass


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise OddsProviderAdapterError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise OddsProviderAdapterError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OddsProviderAdapterError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _market_prices(market: dict, event: dict, canonical: dict) -> tuple[str, dict] | None:
    key = market.get("key")
    outcomes = market.get("outcomes")
    if not isinstance(outcomes, list):
        return None
    if key == "h2h":
        target = "1x2"
        prices = {}
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            label = _name(outcome.get("name"))
            if label == _name(event.get("home_team")):
                selection = "home"
            elif label == _name(event.get("away_team")):
                selection = "away"
            elif label == "draw":
                selection = "draw"
            else:
                continue
            prices[selection] = outcome.get("price")
    elif key == "btts":
        target = "btts"
        prices = {}
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            label = _name(outcome.get("name"))
            if label in {"yes", "no"}:
                prices[label] = outcome.get("price")
    elif key == "totals":
        target = "over_2_5"
        prices = {}
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            try:
                point = float(outcome.get("point"))
            except (TypeError, ValueError):
                continue
            if not math.isclose(point, 2.5, rel_tol=0.0, abs_tol=1e-9):
                continue
            label = _name(outcome.get("name"))
            if label == "over":
                prices["yes"] = outcome.get("price")
            elif label == "under":
                prices["no"] = outcome.get("price")
    else:
        return None
    if set(prices) != set(MARKET_SELECTIONS[target]):
        return None
    return target, prices


def adapt_the_odds_api_event(*, event_payload: dict, crosswalk: dict,
                             retrieved_at: str,
                             max_quote_age_seconds: int = 86400) -> dict:
    """Convert a single event response into point-in-time odds observations.

    Crosswalk fields are provider_event_id, fixture_id, kickoff_at, home_team,
    away_team, mapping_status='verified', and crosswalk_evidence_sha256.
    """
    if not isinstance(event_payload, dict):
        raise OddsProviderAdapterError("event_payload_invalid")
    if not isinstance(crosswalk, dict):
        raise OddsProviderAdapterError("crosswalk_invalid")
    required = {
        "provider_event_id", "fixture_id", "kickoff_at", "home_team",
        "away_team", "mapping_status", "crosswalk_evidence_sha256",
    }
    if set(crosswalk) != required:
        raise OddsProviderAdapterError("crosswalk_shape_invalid")
    if crosswalk["mapping_status"] != "verified":
        raise OddsProviderAdapterError("crosswalk_not_verified")
    for name in ("provider_event_id", "fixture_id", "home_team", "away_team"):
        if not isinstance(crosswalk[name], str) or not crosswalk[name].strip():
            raise OddsProviderAdapterError(f"crosswalk_{name}_invalid")
    crosswalk_digest = crosswalk["crosswalk_evidence_sha256"]
    if (not isinstance(crosswalk_digest, str) or len(crosswalk_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in crosswalk_digest)):
        raise OddsProviderAdapterError("crosswalk_evidence_digest_invalid")
    retrieved = _time(retrieved_at, "retrieved_at")
    kickoff = _time(crosswalk["kickoff_at"], "crosswalk_kickoff_at")
    if isinstance(max_quote_age_seconds, bool) or not isinstance(max_quote_age_seconds, int) or max_quote_age_seconds < 0:
        raise OddsProviderAdapterError("max_quote_age_seconds_invalid")

    event_id = event_payload.get("id")
    if not isinstance(event_id, str) or event_id != crosswalk["provider_event_id"]:
        raise OddsProviderAdapterError("event_crosswalk_id_mismatch")
    event_kickoff = _time(event_payload.get("commence_time"), "event_commence_time")
    if event_kickoff != kickoff:
        raise OddsProviderAdapterError("event_crosswalk_kickoff_mismatch")
    if (_name(event_payload.get("home_team")) != _name(crosswalk["home_team"])
            or _name(event_payload.get("away_team")) != _name(crosswalk["away_team"])):
        raise OddsProviderAdapterError("event_crosswalk_team_mismatch")
    if retrieved > kickoff:
        raise OddsProviderAdapterError("event_retrieved_after_kickoff")

    raw_digest = _digest(event_payload)
    bookmakers = event_payload.get("bookmakers")
    if not isinstance(bookmakers, list):
        raise OddsProviderAdapterError("event_bookmakers_invalid")
    observations, rejected = [], []
    for book_index, book in enumerate(bookmakers):
        if not isinstance(book, dict):
            rejected.append({"bookmaker_index": book_index, "reason": "bookmaker_not_object"})
            continue
        bookmaker = book.get("key")
        if not isinstance(bookmaker, str) or not bookmaker.strip():
            rejected.append({"bookmaker_index": book_index, "reason": "bookmaker_key_missing"})
            continue
        quote_time_raw = book.get("last_update")
        try:
            quote_time = _time(quote_time_raw, "bookmaker_last_update")
        except OddsProviderAdapterError as exc:
            rejected.append({"bookmaker": bookmaker, "reason": str(exc)})
            continue
        if quote_time > retrieved:
            rejected.append({"bookmaker": bookmaker, "reason": "quote_after_retrieval"})
            continue
        if quote_time > kickoff:
            rejected.append({"bookmaker": bookmaker, "reason": "quote_after_kickoff"})
            continue
        if (kickoff - quote_time).total_seconds() > max_quote_age_seconds:
            rejected.append({"bookmaker": bookmaker, "reason": "quote_stale"})
            continue
        markets = book.get("markets")
        if not isinstance(markets, list):
            rejected.append({"bookmaker": bookmaker, "reason": "markets_invalid"})
            continue
        for market_index, market in enumerate(markets):
            if not isinstance(market, dict):
                continue
            parsed = _market_prices(market, event_payload, crosswalk)
            if parsed is None:
                continue
            market_name, prices = parsed
            try:
                observation = build_odds_observation(
                    provider="the_odds_api",
                    provider_event_id=event_id,
                    fixture_id=crosswalk["fixture_id"],
                    market=market_name,
                    bookmaker=bookmaker,
                    captured_at=quote_time.isoformat(),
                    kickoff_at=kickoff.isoformat(),
                    decimal_odds=prices,
                    raw_payload=event_payload,
                    source_payload_sha256=raw_digest,
                    crosswalk_evidence_sha256=crosswalk_digest,
                )
            except BookmakerOddsEvidenceError as exc:
                rejected.append({
                    "bookmaker": bookmaker, "market_index": market_index,
                    "reason": str(exc)[:120],
                })
                continue
            observations.append(observation)
    return {
        "schema_version": 1,
        "provider": "the_odds_api",
        "provider_event_id": event_id,
        "fixture_id": crosswalk["fixture_id"],
        "observation_count": len(observations),
        "observations": observations,
        "rejected_count": len(rejected),
        "rejected": rejected,
        "raw_event_payload_sha256": raw_digest,
        "crosswalk_evidence_sha256": crosswalk_digest,
        "provider_requests_made": 0,
        "database_writes": 0,
        "publication_count": 0,
    }
