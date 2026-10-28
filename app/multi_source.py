"""Source-neutral records and reconciliation for Veltrix's multi-provider data layer.

This module deliberately does not call any provider. Provider adapters should map
vendor payloads into these records, keeping source attribution and timestamps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import unicodedata
from typing import Any, Iterable


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_name(value: Any) -> str:
    """Normalize team/competition names for matching, without fuzzy guessing."""
    raw = unicodedata.normalize("NFKD", _text(value))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


def parse_datetime(value: Any) -> datetime | None:
    """Parse ISO timestamps; naive values are rejected because timezone is ambiguous."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class FixtureRecord:
    source: str
    source_id: str
    kickoff: str
    home: str
    away: str
    competition: str = ""
    season: str = ""
    status: str = "UNKNOWN"
    home_goals: int | None = None
    away_goals: int | None = None
    fetched_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def valid(self) -> bool:
        return bool(
            self.source.strip()
            and self.source_id.strip()
            and parse_datetime(self.kickoff)
            and normalize_name(self.home)
            and normalize_name(self.away)
        )

    @property
    def identity(self) -> tuple[str, str, str, str]:
        kickoff = parse_datetime(self.kickoff)
        # Minute-level grouping tolerates minor provider timestamp formatting,
        # but intentionally does not merge records several minutes apart.
        minute = kickoff.strftime("%Y-%m-%dT%H:%MZ") if kickoff else ""
        return (
            normalize_name(self.competition),
            minute,
            normalize_name(self.home),
            normalize_name(self.away),
        )


@dataclass(frozen=True)
class OddsQuote:
    source: str
    source_fixture_id: str
    bookmaker: str
    market: str
    selection: str
    decimal_odds: float
    captured_at: str
    kickoff: str = ""
    home: str = ""
    away: str = ""
    competition: str = ""
    currency: str = ""
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def valid(self) -> bool:
        try:
            price = float(self.decimal_odds)
        except (TypeError, ValueError, OverflowError):
            return False
        return bool(
            self.source.strip()
            and self.bookmaker.strip()
            and self.market.strip()
            and self.selection.strip()
            and 1.0 < price < 1000.0
            and parse_datetime(self.captured_at)
        )

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            normalize_name(self.bookmaker),
            normalize_name(self.market),
            normalize_name(self.selection),
            self.source_fixture_id.strip(),
        )


def reconcile_fixtures(records: Iterable[FixtureRecord]) -> list[dict[str, Any]]:
    """Group equivalent fixtures, preserve source provenance, flag conflicts.

    No result or kickoff is silently selected when providers disagree. The output
    keeps all source records and marks material conflicts for downstream handling.
    """
    groups: dict[tuple[str, str, str, str], list[FixtureRecord]] = {}
    invalid: list[FixtureRecord] = []
    for record in records:
        if not record.valid:
            invalid.append(record)
            continue
        groups.setdefault(record.identity, []).append(record)

    output: list[dict[str, Any]] = []
    for identity, group in sorted(groups.items(), key=lambda item: item[0]):
        # Prefer complete finished-score data only when all complete scores agree.
        scored = {
            (item.home_goals, item.away_goals)
            for item in group
            if item.home_goals is not None and item.away_goals is not None
        }
        statuses = {normalize_name(item.status) for item in group if item.status}
        conflict = len(scored) > 1
        output.append({
            "identity": identity,
            "home": group[0].home,
            "away": group[0].away,
            "competition": group[0].competition,
            "kickoff": group[0].kickoff,
            "source_count": len({item.source for item in group}),
            "sources": sorted({item.source for item in group}),
            "source_records": [
                {
                    "source": item.source,
                    "source_id": item.source_id,
                    "status": item.status,
                    "home_goals": item.home_goals,
                    "away_goals": item.away_goals,
                    "fetched_at": item.fetched_at,
                }
                for item in group
            ],
            "score_conflict": conflict,
            "score": next(iter(scored)) if len(scored) == 1 else None,
            "status_conflict": len(statuses) > 1,
            "needs_review": conflict or len(statuses) > 1,
        })

    for item in invalid:
        output.append({
            "identity": None,
            "home": item.home,
            "away": item.away,
            "competition": item.competition,
            "kickoff": item.kickoff,
            "source_count": 1,
            "sources": [item.source],
            "source_records": [{
                "source": item.source,
                "source_id": item.source_id,
                "status": item.status,
                "home_goals": item.home_goals,
                "away_goals": item.away_goals,
                "fetched_at": item.fetched_at,
            }],
            "score_conflict": False,
            "score": None,
            "status_conflict": False,
            "needs_review": True,
            "invalid_reason": "missing source/id/team or timezone-aware kickoff",
        })
    return output


def best_current_quotes(
    quotes: Iterable[OddsQuote],
    *,
    now: datetime | None = None,
    max_age_minutes: int = 180,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Return best fresh decimal price per market/selection, with provenance.

    Quotes are not combined across different market definitions. The caller must
    first map provider market labels to a canonical market/selection vocabulary.
    """
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for quote in quotes:
        if not quote.valid:
            continue
        captured = parse_datetime(quote.captured_at)
        if captured is None:
            continue
        age_minutes = (now_utc - captured).total_seconds() / 60
        if age_minutes < -5 or age_minutes > max_age_minutes:
            continue
        key = (normalize_name(quote.market), normalize_name(quote.selection))
        candidate = {
            "market": quote.market,
            "selection": quote.selection,
            "decimal_odds": float(quote.decimal_odds),
            "bookmaker": quote.bookmaker,
            "source": quote.source,
            "source_fixture_id": quote.source_fixture_id,
            "captured_at": quote.captured_at,
            "age_minutes": round(max(0.0, age_minutes), 1),
        }
        current = best.get(key)
        if current is None or candidate["decimal_odds"] > current["decimal_odds"]:
            best[key] = candidate
        elif current and candidate["decimal_odds"] == current["decimal_odds"]:
            # On equal prices, prefer the fresher quote.
            if candidate["age_minutes"] < current["age_minutes"]:
                best[key] = candidate
    return best
