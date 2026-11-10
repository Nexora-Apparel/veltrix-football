"""Immutable point-in-time bookmaker odds observations and snapshot selection.

This module validates already-retrieved odds payloads. It performs no network
requests, fixture matching guesses, persistence, or prediction publication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

MARKET_SELECTIONS = {
    "1x2": ("home", "draw", "away"),
    "btts": ("no", "yes"),
    "over_2_5": ("no", "yes"),
}
SCHEMA_VERSION = 1


class BookmakerOddsEvidenceError(ValueError):
    pass


def _canonical_hash(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise BookmakerOddsEvidenceError("payload_not_canonical_json") from None
    return hashlib.sha256(raw).hexdigest()


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise BookmakerOddsEvidenceError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BookmakerOddsEvidenceError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BookmakerOddsEvidenceError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def build_odds_observation(*, provider: str, provider_event_id: str,
                           fixture_id: str, market: str, bookmaker: str,
                           captured_at: str, kickoff_at: str,
                           decimal_odds: dict, raw_payload: dict,
                           source_payload_sha256: str,
                           crosswalk_evidence_sha256: str | None = None) -> dict:
    for name, value in (
        ("provider", provider), ("provider_event_id", provider_event_id),
        ("fixture_id", fixture_id), ("bookmaker", bookmaker),
    ):
        if not isinstance(value, str) or not value.strip():
            raise BookmakerOddsEvidenceError(f"{name}_invalid")
    if market not in MARKET_SELECTIONS:
        raise BookmakerOddsEvidenceError("market_unsupported")
    captured = _time(captured_at, "captured_at")
    kickoff = _time(kickoff_at, "kickoff_at")
    if captured > kickoff:
        raise BookmakerOddsEvidenceError("odds_captured_after_kickoff")
    if not isinstance(raw_payload, dict):
        raise BookmakerOddsEvidenceError("raw_payload_invalid")
    if not isinstance(source_payload_sha256, str) or len(source_payload_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in source_payload_sha256
    ):
        raise BookmakerOddsEvidenceError("source_payload_sha256_invalid")
    selections = MARKET_SELECTIONS[market]
    if not isinstance(decimal_odds, dict) or set(decimal_odds) != set(selections):
        raise BookmakerOddsEvidenceError("odds_selection_set_invalid")
    prices = {}
    for selection in selections:
        price = decimal_odds[selection]
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise BookmakerOddsEvidenceError(f"decimal_odds_invalid:{selection}")
        price = float(price)
        if not math.isfinite(price) or price <= 1.0 or price > 1000.0:
            raise BookmakerOddsEvidenceError(f"decimal_odds_out_of_range:{selection}")
        prices[selection] = price
    implied = {selection: 1.0 / price for selection, price in prices.items()}
    overround = sum(implied.values())
    if not math.isfinite(overround) or overround <= 0:
        raise BookmakerOddsEvidenceError("overround_invalid")
    normalized = {selection: probability / overround
                  for selection, probability in implied.items()}
    if crosswalk_evidence_sha256 is not None and (
        not isinstance(crosswalk_evidence_sha256, str)
        or len(crosswalk_evidence_sha256) != 64
        or any(char not in "0123456789abcdef" for char in crosswalk_evidence_sha256)
    ):
        raise BookmakerOddsEvidenceError("crosswalk_evidence_sha256_invalid")
    observation = {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "provider_event_id": provider_event_id,
        "fixture_id": fixture_id,
        "market": market,
        "bookmaker": bookmaker,
        "captured_at": captured.isoformat(),
        "kickoff_at": kickoff.isoformat(),
        "decimal_odds": prices,
        "raw_payload_sha256": _canonical_hash(raw_payload),
        "source_payload_sha256": source_payload_sha256,
        "implied_probabilities": normalized,
        "overround": overround,
    }
    if crosswalk_evidence_sha256 is not None:
        observation["crosswalk_evidence_sha256"] = crosswalk_evidence_sha256
    observation["observation_id"] = _canonical_hash(observation)
    return observation


def validate_odds_observation(item: Any) -> dict:
    required = {
        "schema_version", "provider", "provider_event_id", "fixture_id",
        "market", "bookmaker", "captured_at", "kickoff_at", "decimal_odds",
        "raw_payload_sha256", "source_payload_sha256", "implied_probabilities",
        "overround", "observation_id",
    }
    optional = {"crosswalk_evidence_sha256"}
    if not isinstance(item, dict) or not required.issubset(item) or set(item) - required - optional:
        raise BookmakerOddsEvidenceError("observation_shape_invalid")
    if "crosswalk_evidence_sha256" in item:
        crosswalk_digest = item["crosswalk_evidence_sha256"]
        if (not isinstance(crosswalk_digest, str) or len(crosswalk_digest) != 64
                or any(char not in "0123456789abcdef" for char in crosswalk_digest)):
            raise BookmakerOddsEvidenceError("crosswalk_evidence_sha256_invalid")
    if item["schema_version"] != SCHEMA_VERSION:
        raise BookmakerOddsEvidenceError("schema_version_unsupported")
    # Reconstruct from the immutable fields and a digest-only payload surrogate.
    # The raw payload itself is retained in the encrypted source-evidence archive.
    captured = _time(item["captured_at"], "captured_at")
    kickoff = _time(item["kickoff_at"], "kickoff_at")
    if captured > kickoff:
        raise BookmakerOddsEvidenceError("odds_captured_after_kickoff")
    if item["market"] not in MARKET_SELECTIONS:
        raise BookmakerOddsEvidenceError("market_unsupported")
    selections = MARKET_SELECTIONS[item["market"]]
    prices = item["decimal_odds"]
    if not isinstance(prices, dict) or set(prices) != set(selections):
        raise BookmakerOddsEvidenceError("odds_selection_set_invalid")
    implied = {}
    for key in selections:
        price = prices[key]
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise BookmakerOddsEvidenceError(f"decimal_odds_invalid:{key}")
        price = float(price)
        if not math.isfinite(price) or price <= 1.0 or price > 1000.0:
            raise BookmakerOddsEvidenceError(f"decimal_odds_out_of_range:{key}")
        implied[key] = 1.0 / price
    overround = sum(implied.values())
    normalized = {key: value / overround for key, value in implied.items()}
    digest_fields = ("raw_payload_sha256", "source_payload_sha256")
    digests_valid = all(
        isinstance(item.get(name), str) and len(item[name]) == 64
        and all(char in "0123456789abcdef" for char in item[name])
        for name in digest_fields
    )
    stored_probs = item.get("implied_probabilities")
    probabilities_valid = (
        isinstance(stored_probs, dict) and set(stored_probs) == set(selections)
        and all(isinstance(stored_probs[key], (int, float))
                and not isinstance(stored_probs[key], bool)
                and math.isfinite(float(stored_probs[key]))
                and math.isclose(float(stored_probs[key]), normalized[key], rel_tol=1e-12, abs_tol=1e-12)
                for key in selections)
    )
    stored_overround = item.get("overround")
    if (not digests_valid or not probabilities_valid
            or isinstance(stored_overround, bool)
            or not isinstance(stored_overround, (int, float))
            or not math.isfinite(float(stored_overround))
            or not math.isclose(float(stored_overround), overround, rel_tol=1e-12, abs_tol=1e-12)):
        raise BookmakerOddsEvidenceError("odds_observation_integrity_mismatch")
    payload = {key: value for key, value in item.items() if key != "observation_id"}
    if _canonical_hash(payload) != item["observation_id"]:
        raise BookmakerOddsEvidenceError("odds_observation_id_mismatch")
    return {"valid": True, "observation_id": item["observation_id"]}


def append_odds_observations(ledger: Any, observations: list[dict]) -> dict:
    if not isinstance(ledger, dict) or set(ledger) != {"schema_version", "observations"}:
        raise BookmakerOddsEvidenceError("ledger_shape_invalid")
    if ledger["schema_version"] != SCHEMA_VERSION or not isinstance(ledger["observations"], list):
        raise BookmakerOddsEvidenceError("ledger_schema_invalid")
    if not isinstance(observations, list):
        raise BookmakerOddsEvidenceError("observations_must_be_list")
    existing = list(ledger["observations"])
    seen = set()
    last: dict[tuple[str, str, str, str], datetime] = {}
    for item in existing:
        validate_odds_observation(item)
        if item["observation_id"] in seen:
            raise BookmakerOddsEvidenceError("existing_duplicate_observation")
        seen.add(item["observation_id"])
        key = (item["provider"], item["fixture_id"], item["market"], item["bookmaker"])
        stamp = _time(item["captured_at"], "captured_at")
        if key in last and stamp < last[key]:
            raise BookmakerOddsEvidenceError("existing_observation_order_invalid")
        last[key] = stamp
    added = 0
    for item in observations:
        validate_odds_observation(item)
        oid = item["observation_id"]
        if oid in seen:
            continue
        key = (item["provider"], item["fixture_id"], item["market"], item["bookmaker"])
        stamp = _time(item["captured_at"], "captured_at")
        if key in last and stamp < last[key]:
            raise BookmakerOddsEvidenceError("observation_time_regression")
        existing.append(item)
        seen.add(oid)
        last[key] = stamp
        added += 1
    return {
        "ledger": {"schema_version": SCHEMA_VERSION, "observations": existing},
        "added_count": added,
        "total_observation_count": len(existing),
        "database_writes": 0,
        "provider_requests_made": 0,
    }


def latest_pre_kickoff_snapshot(ledger: dict, *, fixture_id: str,
                                market: str, bookmaker: str,
                                kickoff_at: str) -> dict | None:
    if not isinstance(ledger, dict) or ledger.get("schema_version") != SCHEMA_VERSION:
        raise BookmakerOddsEvidenceError("ledger_schema_invalid")
    cutoff = _time(kickoff_at, "kickoff_at")
    matches = []
    for item in ledger.get("observations", []):
        validate_odds_observation(item)
        if (item["fixture_id"] == fixture_id and item["market"] == market
                and item["bookmaker"] == bookmaker):
            captured = _time(item["captured_at"], "captured_at")
            if captured <= cutoff and _time(item["kickoff_at"], "observation_kickoff") == cutoff:
                matches.append(item)
    if not matches:
        return None
    matches.sort(key=lambda item: _time(item["captured_at"], "captured_at"))
    chosen = matches[-1]
    return {
        "observation_id": chosen["observation_id"],
        "fixture_id": fixture_id,
        "market": market,
        "bookmaker": bookmaker,
        "captured_at": chosen["captured_at"],
        "kickoff_at": chosen["kickoff_at"],
        "decimal_odds": dict(chosen["decimal_odds"]),
        "implied_probabilities": dict(chosen["implied_probabilities"]),
        "overround": chosen["overround"],
        "source_payload_sha256": chosen["source_payload_sha256"],
        "timestamp_semantics": "latest_observed_pre_kickoff_snapshot",
    }
