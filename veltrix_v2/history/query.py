"""Point-in-time team-history selection with fail-closed coverage states."""
from __future__ import annotations

from datetime import datetime, timezone

from veltrix_v2.domain.contracts import HistoryState
from veltrix_v2.history.contracts import (
    HistoricalMatch,
    HistoryEvidenceResult,
    TeamHistoryQuery,
)


def select_team_history(
    source_matches: tuple[HistoricalMatch, ...] | list[HistoricalMatch],
    query: TeamHistoryQuery,
) -> HistoryEvidenceResult:
    """Select recent, verified team matches strictly before the feature cutoff.

    The caller supplies only canonicalized records. A squad-category conflict
    for the requested canonical team is surfaced as IDENTITY_MISMATCH instead
    of being silently mixed into the time series.
    """
    team_rows = [
        match for match in source_matches
        if query.canonical_team_id in {match.home_team_id, match.away_team_id}
    ]
    mismatched = [
        match for match in team_rows
        if match.squad_category != query.squad_category
    ]
    if mismatched:
        evidence = tuple(dict.fromkeys(
            source_id
            for match in mismatched
            for source_id in match.source_record_ids
        ))
        return HistoryEvidenceResult(
            canonical_team_id=query.canonical_team_id,
            state=HistoryState.IDENTITY_MISMATCH,
            matches=(),
            total_match_count=0,
            evidence_ids=evidence,
            reason_code="SQUAD_CATEGORY_CONFLICT",
        )

    cutoff = query.cutoff_at_utc.astimezone(timezone.utc)
    lower_date = query.window_start_date
    candidates = [
        match for match in team_rows
        if match.kickoff_at_utc.astimezone(timezone.utc) < cutoff
        and match.kickoff_at_utc.date() >= lower_date
        and (
            not query.competition_ids
            or match.canonical_competition_id in query.competition_ids
        )
    ]
    candidates.sort(key=lambda item: item.kickoff_at_utc.astimezone(timezone.utc))
    total = len(candidates)
    selected = candidates[-query.max_matches:]
    evidence_ids = tuple(dict.fromkeys(
        source_id
        for match in selected
        for source_id in match.source_record_ids
    ))

    if total == 0:
        return HistoryEvidenceResult(
            canonical_team_id=query.canonical_team_id,
            state=HistoryState.NOT_FOUND,
            matches=(),
            total_match_count=0,
            evidence_ids=(),
            reason_code="NO_MATCHES_IN_REQUESTED_WINDOW",
        )
    if total < query.minimum_matches:
        return HistoryEvidenceResult(
            canonical_team_id=query.canonical_team_id,
            state=HistoryState.INSUFFICIENT_COVERAGE,
            matches=tuple(selected),
            total_match_count=total,
            evidence_ids=evidence_ids,
            reason_code="BELOW_MINIMUM_TEAM_HISTORY",
        )
    return HistoryEvidenceResult(
        canonical_team_id=query.canonical_team_id,
        state=HistoryState.FOUND,
        matches=tuple(selected),
        total_match_count=total,
        evidence_ids=evidence_ids,
        reason_code="MINIMUM_TEAM_HISTORY_MET",
    )
