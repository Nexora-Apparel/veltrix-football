"""Point-in-time-safe OpenPlay team-match feature adapter.

The Parquet release contains post-match observations. Source page-save time is
not substituted for VELTRIX's actual import time. These features are eligible
only for cutoffs strictly after both timestamps and can never be backdated into
historical cutoffs preceding the staging import.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping


OPENPLAY_PROVIDER = "OpenPlay / WhoScored / Opta"
OPENPLAY_SOURCE_ID = "openplay-data-v0.1.0"
OPENPLAY_APPROVAL_ID = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"
OPENPLAY_XG_MODEL = "openplay_xg_v1"


def _aware_utc(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        raise ValueError(f"OPENPLAY_{field}_MISSING")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"OPENPLAY_{field}_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip()[:10])
    raise ValueError("OPENPLAY_MATCH_DATE_INVALID")


def _num(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    if value is None:
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    if result != result or result in (float("inf"), float("-inf")):
        return 0.0
    return result


def _canonical_json_hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, default=str, allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class OpenPlayTeamMatchFeature:
    provider_match_id: str
    provider_team_id: str
    provider_opponent_id: str
    canonical_team_id: str
    canonical_opponent_id: str
    canonical_competition_id: str
    competition_code: str
    season: str
    match_date: date
    source_published_at: datetime
    available_at: datetime
    recorded_at: datetime
    xg_model: str
    metrics: Mapping[str, Any]
    rights_approval_id: str
    commercial_use_allowed: bool
    feature_sha256: str

    def eligible_at(self, cutoff_at: datetime) -> bool:
        cutoff = _aware_utc(cutoff_at, "CUTOFF_AT")
        return (
            self.commercial_use_allowed is False
            and cutoff > self.source_published_at
            and cutoff > self.available_at
            and cutoff > self.recorded_at
        )


def build_openplay_team_match_features(
    *,
    matches: Iterable[Mapping[str, Any]],
    team_match_stats: Iterable[Mapping[str, Any]],
    player_match_stats: Iterable[Mapping[str, Any]],
    lineups: Iterable[Mapping[str, Any]],
    shots: Iterable[Mapping[str, Any]],
    cards: Iterable[Mapping[str, Any]],
    formations: Iterable[Mapping[str, Any]],
    team_crosswalk: Mapping[str, str],
    competition_crosswalk: Mapping[str, str],
    recorded_at_by_match: Mapping[str, datetime],
) -> tuple[OpenPlayTeamMatchFeature, ...]:
    """Build one post-match feature row per team and match.

    Crosswalks must be exact, already-resolved canonical IDs from the staging
    registry. Unmapped entities are excluded rather than guessed. Duplicate
    team-match natural keys are rejected; duplicate player natural keys are
    excluded from player aggregates and reported through the audit counts.
    """
    match_by_id: dict[str, Mapping[str, Any]] = {}
    for row in matches:
        match_id = str(row.get("match_id") or "")
        if not match_id or match_id in match_by_id:
            raise ValueError("OPENPLAY_MATCH_ID_MISSING_OR_DUPLICATE")
        match_by_id[match_id] = row

    def grouped(rows: Iterable[Mapping[str, Any]], key_fn):
        result: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
        for row in rows:
            key = key_fn(row)
            result.setdefault(key, []).append(row)
        return result

    stats_by_match_team = grouped(
        team_match_stats,
        lambda row: (str(row.get("match_id") or ""), str(row.get("team_id") or "")),
    )
    if any(len(rows) != 1 for rows in stats_by_match_team.values()):
        raise ValueError("OPENPLAY_TEAM_MATCH_STATS_DUPLICATE_NATURAL_KEY")

    player_groups = grouped(
        player_match_stats,
        lambda row: (str(row.get("match_id") or ""), str(row.get("team_id") or "")),
    )
    lineup_groups = grouped(
        lineups,
        lambda row: (str(row.get("match_id") or ""), str(row.get("team_id") or "")),
    )
    shot_groups = grouped(
        shots,
        lambda row: (str(row.get("match_id") or ""), str(row.get("team_id") or "")),
    )
    card_groups = grouped(
        cards,
        lambda row: (str(row.get("match_id") or ""), str(row.get("team_id") or "")),
    )
    formation_groups = grouped(
        formations,
        lambda row: (str(row.get("match_id") or ""), str(row.get("team_id") or "")),
    )

    features: list[OpenPlayTeamMatchFeature] = []
    for (match_id, team_id), stats_rows in sorted(stats_by_match_team.items()):
        match = match_by_id.get(match_id)
        if match is None:
            continue
        comp_code = str(match.get("comp") or "")
        home_id = str(match.get("home_team_id") or "")
        away_id = str(match.get("away_team_id") or "")
        if team_id not in {home_id, away_id}:
            continue
        opponent_id = away_id if team_id == home_id else home_id
        canonical_team = team_crosswalk.get(team_id)
        canonical_opponent = team_crosswalk.get(opponent_id)
        canonical_comp = competition_crosswalk.get(comp_code)
        if not all(isinstance(v, str) and v.strip() for v in (
            canonical_team, canonical_opponent, canonical_comp,
        )):
            continue
        if canonical_team == canonical_opponent:
            raise ValueError("OPENPLAY_CANONICAL_TEAM_COLLISION")

        source_saved_at = _aware_utc(match.get("scraped_at"), "SOURCE_SCRAPED_AT")
        recorded_at = _aware_utc(recorded_at_by_match.get(match_id), "VELTRIX_RECORDED_AT")
        if recorded_at < source_saved_at:
            raise ValueError("OPENPLAY_RECORDED_BEFORE_SOURCE_PAGE_SAVE")
        xg_model = str(match.get("xg_model") or "")
        if xg_model != OPENPLAY_XG_MODEL:
            raise ValueError("OPENPLAY_XG_MODEL_ID_UNEXPECTED")

        player_rows = player_groups.get((match_id, team_id), [])
        unique_players: dict[str, Mapping[str, Any]] = {}
        duplicate_player_ids: set[str] = set()
        for player in player_rows:
            player_id = str(player.get("player_id") or "")
            if not player_id:
                continue
            if player_id in unique_players:
                duplicate_player_ids.add(player_id)
            else:
                unique_players[player_id] = player
        for duplicate_id in duplicate_player_ids:
            unique_players.pop(duplicate_id, None)

        lineup_rows = lineup_groups.get((match_id, team_id), [])
        shot_rows = shot_groups.get((match_id, team_id), [])
        card_rows = card_groups.get((match_id, team_id), [])
        formation_rows = formation_groups.get((match_id, team_id), [])

        player_metrics = {
            "players_in_match_stats": len(unique_players),
            "starters": sum(bool(p.get("is_starter")) for p in unique_players.values()),
            "minutes_played_total": sum(_num(p, "minutes_played") for p in unique_players.values()),
            "player_xg": sum(_num(p, "xg") for p in unique_players.values()),
            "player_npxg": sum(_num(p, "npxg") for p in unique_players.values()),
            "player_shots": sum(_num(p, "shots") for p in unique_players.values()),
            "player_shots_on_target": sum(_num(p, "shots_on_target") for p in unique_players.values()),
            "player_goals": sum(_num(p, "goals") for p in unique_players.values()),
            "player_xa": sum(_num(p, "xa") for p in unique_players.values()),
            "player_key_passes": sum(_num(p, "key_passes") for p in unique_players.values()),
            "player_tackles": sum(_num(p, "tackles") for p in unique_players.values()),
            "player_interceptions": sum(_num(p, "interceptions") for p in unique_players.values()),
        }
        lineup_metrics = {
            "squad_size": len(lineup_rows),
            "lineup_starters": sum(bool(p.get("is_starter")) for p in lineup_rows),
            "lineup_players_used": sum(bool(p.get("played")) for p in lineup_rows),
            "captains": sum(bool(p.get("is_captain_start")) for p in lineup_rows),
        }
        shot_metrics = {
            "shot_rows": len(shot_rows),
            "shot_xg": sum(_num(s, "xg") for s in shot_rows if not s.get("is_shootout")),
            "non_penalty_shot_xg": sum(
                _num(s, "xg") for s in shot_rows
                if not s.get("is_shootout") and not s.get("is_penalty")
            ),
            "shots_on_target": sum(bool(s.get("is_on_target")) for s in shot_rows if not s.get("is_shootout")),
            "big_chances": sum(bool(s.get("is_big_chance")) for s in shot_rows if not s.get("is_shootout")),
            "set_piece_shots": sum(bool(s.get("is_set_piece")) for s in shot_rows if not s.get("is_shootout")),
        }
        card_metrics = {
            "yellow_cards": sum(str(c.get("card")) == "yellow" for c in card_rows),
            "second_yellows": sum(str(c.get("card")) == "second_yellow" for c in card_rows),
            "red_cards": sum(str(c.get("card")) == "red" for c in card_rows),
        }
        formations_sorted = sorted(
            {
                (
                    str(f.get("period") or ""),
                    int(f.get("start_expanded_minute") or 0),
                    str(f.get("formation") or ""),
                )
                for f in formation_rows
            }
        )
        team_metrics = {
            key: stats_rows[0].get(key)
            for key in (
                "goals_for","goals_against","xg","npxg","xg_against","npxg_against",
                "shots","shots_on_target","shots_against","shots_on_target_against",
                "passes","passes_completed","pass_pct","passes_final_third",
                "progressive_passes","key_passes","xa","tackles","tackles_won",
                "interceptions","clearances","ball_recoveries","aerials","aerials_won",
                "fouls_committed","offsides","corners_taken",
            )
        }
        metrics = {
            "team": team_metrics,
            "players": player_metrics,
            "lineup": lineup_metrics,
            "shots": shot_metrics,
            "cards": card_metrics,
            "formation_spells": [
                {"period": period, "start_minute": minute, "formation": formation}
                for period, minute, formation in formations_sorted
            ],
            "xg_model": xg_model,
            "source_match_score_consistent": bool(match.get("score_matches_events")),
            # The pinned v0.1.0 release documents this as a share, but the
            # observed values include negatives and therefore violate that
            # contract. Keep it out of model features until source semantics
            # are independently resolved; never rescale or infer a replacement.
            "excluded_source_metrics": {
                "possession_pct": "SOURCE_VALUES_VIOLATE_DOCUMENTED_PERCENTAGE_RANGE"
            },
        }
        identity = {
            "provider": OPENPLAY_PROVIDER,
            "source_id": OPENPLAY_SOURCE_ID,
            "match_id": match_id,
            "team_id": team_id,
            "canonical_team_id": canonical_team,
            "canonical_opponent_id": canonical_opponent,
            "canonical_competition_id": canonical_comp,
            "source_published_at": source_saved_at.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "metrics": metrics,
        }
        features.append(OpenPlayTeamMatchFeature(
            provider_match_id=match_id, provider_team_id=team_id,
            provider_opponent_id=opponent_id, canonical_team_id=canonical_team,
            canonical_opponent_id=canonical_opponent,
            canonical_competition_id=canonical_comp, competition_code=comp_code,
            season=str(match.get("season") or ""), match_date=_date(match.get("date")),
            source_published_at=source_saved_at, available_at=source_saved_at,
            recorded_at=recorded_at, xg_model=xg_model, metrics=metrics,
            rights_approval_id=OPENPLAY_APPROVAL_ID, commercial_use_allowed=False,
            feature_sha256=_canonical_json_hash(identity),
        ))
    return tuple(features)


def eligible_openplay_team_match_features(
    features: Iterable[OpenPlayTeamMatchFeature], *, cutoff_at: datetime,
) -> tuple[OpenPlayTeamMatchFeature, ...]:
    """Select only previously played, already imported post-match features."""
    cutoff = _aware_utc(cutoff_at, "CUTOFF_AT")
    return tuple(sorted(
        (row for row in features if row.eligible_at(cutoff)),
        key=lambda row: (row.match_date, row.provider_match_id, row.canonical_team_id),
    ))
