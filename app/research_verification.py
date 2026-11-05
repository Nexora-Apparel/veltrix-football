"""Strict verification gate for structured external football match evidence.

This module does not scrape pages or parse search snippets. It accepts
structured source records from an approved source-specific extractor and only
marks a historical result model-eligible when two independent trusted domains
agree on the exact fixture identity, squad category, date and score.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

from app.research_evidence import _public_https_url


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _aware_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _match_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _trusted_host(host: str, trusted_domains: set[str]) -> bool:
    normalized = host.rstrip(".").lower()
    return any(normalized == domain or normalized.endswith("." + domain) for domain in trusted_domains)


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 and str(parsed) == str(value).strip() else None


def verify_structured_match_evidence(
    fixture: dict[str, Any],
    records: Iterable[dict[str, Any]],
    *,
    trusted_domains: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Verify historical results without fuzzy identity or cross-squad matching."""
    if not isinstance(fixture, dict):
        return {"status": "INVALID_FIXTURE", "verified_records": [], "model_eligible": False}

    home = _key(fixture.get("home_team"))
    away = _key(fixture.get("away_team"))
    competition = _key(fixture.get("competition"))
    squad = _key(fixture.get("squad_category"))
    kickoff = _aware_datetime(fixture.get("kickoff_utc") or fixture.get("kickoff"))
    if not all((home, away, competition, squad)) or kickoff is None:
        return {"status": "INVALID_FIXTURE_IDENTITY", "verified_records": [], "model_eligible": False}

    configured = trusted_domains
    if configured is None:
        configured = os.getenv("VELTRIX_RESEARCH_TRUSTED_DOMAINS", "").split(",")
    trusted = {str(item).strip().lower().rstrip(".") for item in configured if str(item).strip()}
    if not trusted:
        return {"status": "DISABLED_NO_TRUSTED_DOMAINS", "verified_records": [], "model_eligible": False}

    matching: dict[tuple[str, str, str, str, date], list[dict[str, Any]]] = defaultdict(list)
    rejected = 0
    for record in records:
        if not isinstance(record, dict):
            rejected += 1
            continue
        url = record.get("source_url")
        if not _public_https_url(url):
            rejected += 1
            continue
        host = (urlparse(url).hostname or "").lower()
        matching_trust_roots = [domain for domain in trusted if host == domain or host.endswith("." + domain)]
        if not matching_trust_roots:
            rejected += 1
            continue
        trust_root = min(matching_trust_roots, key=len)
        if (
            _key(record.get("home_team")) != home
            or _key(record.get("away_team")) != away
            or _key(record.get("competition")) != competition
            or _key(record.get("squad_category")) != squad
        ):
            rejected += 1
            continue

        played = _match_date(record.get("match_date"))
        published = _aware_datetime(record.get("published_at"))
        retrieved = _aware_datetime(record.get("retrieved_at_utc"))
        home_goals = _nonnegative_int(record.get("home_goals"))
        away_goals = _nonnegative_int(record.get("away_goals"))
        if (
            played is None
            or played >= kickoff.date()
            or published is None
            or retrieved is None
            or published > kickoff
            or retrieved > kickoff
            or home_goals is None
            or away_goals is None
        ):
            rejected += 1
            continue

        key = (home, away, competition, squad, played)
        matching[key].append({
            "home_goals": home_goals,
            "away_goals": away_goals,
            "source_url": url,
            "source_domain": host,
            "independent_source_group": trust_root,
            "source_record_id": record.get("source_record_id"),
            "published_at": record.get("published_at"),
            "retrieved_at_utc": record.get("retrieved_at_utc"),
        })

    verified: list[dict[str, Any]] = []
    conflicts = 0
    insufficient = 0
    for identity, evidence in matching.items():
        score_groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for item in evidence:
            score_groups[(item["home_goals"], item["away_goals"])].append(item)
        if len(score_groups) > 1:
            conflicts += len(evidence)
            continue
        (home_score, away_score), agreeing = next(iter(score_groups.items()))
        independent_domains = {item["independent_source_group"] for item in agreeing}
        if len(independent_domains) < 2:
            insufficient += len(agreeing)
            continue
        played = identity[4]
        verified.append({
            "match_date": played.isoformat(),
            "home_team": fixture["home_team"],
            "away_team": fixture["away_team"],
            "competition": fixture["competition"],
            "squad_category": fixture["squad_category"],
            "home_goals": home_score,
            "away_goals": away_score,
            "fixture_provider_id": fixture.get("provider_fixture_id") or fixture.get("fixture_id"),
            "verification_status": "VERIFIED_TWO_INDEPENDENT_SOURCES",
            "model_eligible": True,
            "provenance": agreeing,
        })

    if verified and (conflicts or insufficient or rejected):
        status = "PARTIALLY_VERIFIED"
    elif verified:
        status = "VERIFIED"
    elif conflicts:
        status = "QUARANTINED_CONFLICT"
    elif insufficient:
        status = "INSUFFICIENT_INDEPENDENT_SOURCES"
    elif matching:
        status = "INSUFFICIENT_INDEPENDENT_SOURCES"
    else:
        status = "NO_MATCHING_EVIDENCE"

    return {
        "status": status,
        "fixture_provider_id": fixture.get("provider_fixture_id") or fixture.get("fixture_id"),
        "verified_records": verified,
        "verified_record_count": len(verified),
        "quarantined_conflict_records": conflicts,
        "insufficient_source_records": insufficient,
        "rejected_records": rejected,
        "model_eligible": bool(verified),
        "policy": "Exact identity and squad match; historical date before kickoff; two independent trusted domains must agree.",
    }
