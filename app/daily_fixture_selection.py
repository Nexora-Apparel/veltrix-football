"""Deterministic, evidence-gated daily fixture selection (maximum 25)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


LAGOS = ZoneInfo("Africa/Lagos")
MAX_DAILY_FIXTURES = 25


def _aware(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def select_daily_fixtures(*, records: list[dict], target_date: str,
                          as_of: str, qualified_sources: dict[str, list[str]],
                          max_fixtures: int = MAX_DAILY_FIXTURES) -> dict:
    """Select only future scheduled records from explicitly qualified sources.

    qualified_sources is an evidence-backed allowlist keyed by provider,
    containing provider-scoped competition keys. This function does not infer
    competition qualification, merge providers, or manufacture missing rows.
    """
    if not isinstance(records, list):
        raise ValueError("records_must_be_a_list")
    try:
        target = date.fromisoformat(target_date)
    except (TypeError, ValueError):
        raise ValueError("target_date_invalid") from None
    as_of_utc = _aware(as_of, "as_of")
    if not isinstance(qualified_sources, dict):
        raise ValueError("qualified_sources_must_be_object")
    if isinstance(max_fixtures, bool) or not isinstance(max_fixtures, int) or not 1 <= max_fixtures <= MAX_DAILY_FIXTURES:
        raise ValueError("max_fixtures_must_be_between_1_and_25")

    allowlist: set[tuple[str, str]] = set()
    for provider, competitions in qualified_sources.items():
        if not isinstance(provider, str) or not provider.strip() or not isinstance(competitions, list):
            raise ValueError("qualified_source_entry_invalid")
        for competition in competitions:
            if not isinstance(competition, (str, int)) or not str(competition).strip():
                raise ValueError("qualified_competition_key_invalid")
            allowlist.add((provider, str(competition)))

    eligible = []
    excluded = Counter()
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            excluded["record_not_object"] += 1
            continue
        provider = record.get("provider")
        competition = record.get("competition_key")
        source_id = record.get("source_id")
        if (provider, str(competition)) not in allowlist:
            excluded["source_or_competition_not_qualified"] += 1
            continue
        if record.get("normalized_status") != "scheduled":
            excluded["not_scheduled"] += 1
            continue
        if not isinstance(source_id, str) or not source_id.strip():
            excluded["source_identity_missing"] += 1
            continue
        identity = (provider, str(competition), source_id)
        if identity in seen:
            excluded["duplicate_source_identity"] += 1
            continue
        seen.add(identity)
        try:
            kickoff = _aware(record.get("kickoff_at"), "kickoff")
        except ValueError:
            excluded["kickoff_invalid_or_timezone_missing"] += 1
            continue
        if kickoff <= as_of_utc:
            excluded["kickoff_not_in_future"] += 1
            continue
        if kickoff.astimezone(LAGOS).date() != target:
            excluded["outside_target_lagos_date"] += 1
            continue
        eligible.append((kickoff, provider, str(competition), source_id, record))

    eligible.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    selected = [item[4] for item in eligible[:max_fixtures]]
    overflow = max(0, len(eligible) - max_fixtures)
    if overflow:
        excluded["daily_cap_exceeded"] += overflow

    return {
        "schema_version": 1,
        "mode": "qualified_future_daily_fixture_selection",
        "target_date": target.isoformat(),
        "timezone": "Africa/Lagos",
        "as_of": as_of_utc.isoformat().replace("+00:00", "Z"),
        "maximum_fixtures": max_fixtures,
        "candidate_count": len(records),
        "eligible_count": len(eligible),
        "selected_count": len(selected),
        "excluded_count": sum(excluded.values()),
        "excluded_reasons": dict(sorted(excluded.items())),
        "selected": selected,
        "policy": {
            "favourites_only_filter": False,
            "synthetic_fixtures": 0,
            "cross_provider_fuzzy_merges": 0,
            "database_writes": 0,
            "prediction_publications": 0,
        },
    }
