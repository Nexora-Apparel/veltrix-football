"""Historical data completeness diagnostics; no imputation or prediction logic."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timezone

from veltrix_v2.history.contracts import HistoricalMatch


@dataclass(frozen=True, slots=True)
class HistoricalCoverageReport:
    total_matches: int
    distinct_competitions: int
    distinct_teams: int
    first_match_date: date | None
    last_match_date: date | None
    matches_by_competition: tuple[tuple[str, int], ...]
    matches_by_squad_category: tuple[tuple[str, int], ...]
    provider_fixture_reference_count: int
    source_record_reference_count: int
    duplicate_canonical_fixture_ids: tuple[str, ...]
    invalid_rows: tuple[str, ...]


def assess_historical_coverage(matches: tuple[HistoricalMatch, ...] | list[HistoricalMatch]) -> HistoricalCoverageReport:
    competitions = Counter()
    squads = Counter()
    fixture_ids = Counter()
    teams: set[str] = set()
    dates: list[date] = []
    invalid: list[str] = []
    provider_refs = source_refs = 0
    for match in matches:
        fixture_ids[match.canonical_fixture_id] += 1
        competitions[match.canonical_competition_id] += 1
        squads[match.squad_category] += 1
        teams.update((match.home_team_id, match.away_team_id))
        dates.append(match.kickoff_at_utc.astimezone(timezone.utc).date())
        provider_refs += len(match.provider_fixture_refs)
        source_refs += len(match.source_record_ids)
        if not match.provider_fixture_refs or not match.source_record_ids:
            invalid.append(match.historical_match_id)
    duplicates = tuple(sorted(key for key, count in fixture_ids.items() if count > 1))
    return HistoricalCoverageReport(
        total_matches=len(matches), distinct_competitions=len(competitions),
        distinct_teams=len(teams), first_match_date=min(dates) if dates else None,
        last_match_date=max(dates) if dates else None,
        matches_by_competition=tuple(sorted(competitions.items())),
        matches_by_squad_category=tuple(sorted(squads.items())),
        provider_fixture_reference_count=provider_refs,
        source_record_reference_count=source_refs,
        duplicate_canonical_fixture_ids=duplicates, invalid_rows=tuple(sorted(invalid)),
    )
