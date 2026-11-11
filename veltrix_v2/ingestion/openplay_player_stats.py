"""Lossless, non-live adapter for the pinned OpenPlay historical release.

The adapter deliberately preserves unzoned source dates as text. It never invents
UTC kickoff or availability timestamps and does not approve rights or model use.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


_METRIC_COLUMNS = {
    "minutes_played": "minutes_played",
    "goals": "goals",
    "assists": "assists",
    "shots": "shots",
    "shots_on_target": "shots_on_target",
    "xg": "xg",
    "npxg": "npxg",
    "xa": "xa",
    "key_passes": "key_passes",
    "passes_attempted": "passes_attempted",
    "passes_completed": "passes_completed",
    "tackles": "tackles",
    "interceptions": "interceptions",
    "clearances": "clearances",
    "blocks": "blocks",
    "duels_won": "duels_won",
    "aerials_won": "aerials_won",
    "yellow_cards": "yellow_cards",
    "red_cards": "red_cards",
    "saves": "saves",
    "goals_conceded": "goals_conceded",
    "recoveries": "recoveries",
}
_COUNT_METRICS = frozenset(_METRIC_COLUMNS) - {"minutes_played", "xg", "npxg", "xa"}


def _required_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if value is None or not str(value).strip():
        raise ValueError(f"OPENPLAY_REQUIRED_FIELD_MISSING:{key}")
    return str(value).strip()


def _metric(value: object, name: str) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"OPENPLAY_INVALID_METRIC:{name}")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"OPENPLAY_INVALID_METRIC:{name}")
    if name in _COUNT_METRICS and type(value) is not int:
        raise ValueError(f"OPENPLAY_NON_INTEGER_COUNT:{name}")
    if name == "minutes_played" and value > 150:
        raise ValueError("OPENPLAY_INVALID_MINUTES")
    return value


@dataclass(frozen=True, slots=True)
class OpenPlayHistoricalPlayerRow:
    provider_match_id: str
    provider_player_id: str
    provider_team_id: str
    competition_code: str
    season: str
    source_match_date: str
    source_scraped_at: str | None
    metrics: Mapping[str, int | float | None]
    started: bool | None
    position: str | None
    xg_model_id: str | None
    xa_model_id: str | None
    payload_sha256: str
    source_release: str = "data-v0.1.0"
    quality_state: str = "eligible_for_research"

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


def adapt_player_match_row(
    row: Mapping[str, object],
    *,
    xg_model_id: str | None,
    xa_model_id: str | None = None,
    known_issue_match_ids: frozenset[str] = frozenset(),
    covered_competition_seasons: frozenset[tuple[str, str]] | None = None,
) -> OpenPlayHistoricalPlayerRow:
    """Convert one raw player_match_stats row without inventing timestamp precision.

    xG model identity is supplied from the matching OpenPlay match record because the
    player table does not guarantee a per-row model column. Rights approval is separate.
    """
    if not isinstance(row, Mapping):
        raise ValueError("OPENPLAY_ROW_MUST_BE_MAPPING")

    match_id = _required_text(row, "match_id")
    player_id = _required_text(row, "player_id")
    team_id = _required_text(row, "team_id")
    competition = _required_text(row, "comp")
    season = _required_text(row, "season")
    source_date = _required_text(row, "date")
    raw_scraped_at = row.get("scraped_at")
    scraped_at = None if raw_scraped_at in (None, "") else str(raw_scraped_at)

    metrics = {
        target: _metric(row.get(source), target)
        for target, source in _METRIC_COLUMNS.items()
        if source in row
    }
    if any(metrics.get(key) is not None for key in ("xg", "npxg")) and not (xg_model_id or "").strip():
        raise ValueError("OPENPLAY_XG_MODEL_ID_REQUIRED")
    if metrics.get("xa") is not None and not (xa_model_id or "").strip():
        raise ValueError("OPENPLAY_XA_MODEL_ID_REQUIRED")

    starter_value = row.get("is_starter")
    if starter_value in (None, ""):
        started = None
    elif type(starter_value) is bool:
        started = starter_value
    elif starter_value in (0, 1):
        started = bool(starter_value)
    else:
        raise ValueError("OPENPLAY_INVALID_STARTER_FLAG")

    quality = "eligible_for_research"
    if match_id in known_issue_match_ids:
        quality = "quarantined_known_match_issue"
    if covered_competition_seasons is not None and (competition, season) not in covered_competition_seasons:
        quality = "quarantined_outside_declared_coverage"

    canonical = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=str).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return OpenPlayHistoricalPlayerRow(
        provider_match_id=match_id,
        provider_player_id=player_id,
        provider_team_id=team_id,
        competition_code=competition,
        season=season,
        source_match_date=source_date,
        source_scraped_at=scraped_at,
        metrics=metrics,
        started=started,
        position=None if row.get("position") in (None, "") else str(row["position"]),
        xg_model_id=xg_model_id,
        xa_model_id=xa_model_id,
        payload_sha256=digest,
        quality_state=quality,
    )
