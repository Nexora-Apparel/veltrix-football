"""Deterministic coverage and integrity profiling for validated 5Dollar archives.

Coverage means the requested provider pages were fetched and the returned
records were validated. It does not assert that the provider's catalogue is
complete or that a competition has complete historical match coverage.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.provider_historical_archive import (
    HistoricalArchiveError,
    validate_fivedollar_history_archive,
)


class HistoricalCoverageError(ValueError):
    pass


def _digest(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _months(start: date, end: date) -> list[str]:
    values = []
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cursor <= last:
        values.append(cursor.strftime("%Y-%m"))
        cursor = date(cursor.year + (cursor.month == 12),
                      1 if cursor.month == 12 else cursor.month + 1, 1)
    return values


def profile_fivedollar_historical_coverage(archive: Any) -> dict:
    try:
        verified = validate_fivedollar_history_archive(archive)
    except (HistoricalArchiveError, TypeError, KeyError) as exc:
        raise HistoricalCoverageError(f"archive_not_valid:{type(exc).__name__}:{str(exc)[:100]}") from None

    target = archive["target_window"]
    start = date.fromisoformat(target["start_date"])
    end = date.fromisoformat(target["end_date"])
    zone = ZoneInfo("Africa/Lagos")
    records = archive["records"]
    months = _months(start, end)
    by_comp = defaultdict(list)
    global_months = Counter()
    team_appearances = defaultdict(Counter)
    team_names = defaultdict(lambda: defaultdict(set))
    slots = Counter()
    kickoff_dates = set()
    total_goals = 0
    max_team_score = 0

    for index, row in enumerate(records):
        try:
            kickoff = datetime.fromisoformat(row["kickoff_at"].replace("Z", "+00:00"))
            if kickoff.tzinfo is None or kickoff.utcoffset() is None:
                raise ValueError
            local = kickoff.astimezone(zone)
            local_day = local.date()
            if not start <= local_day <= end:
                raise ValueError
            if row["normalized_status"] != "finished":
                raise ValueError
            home_score, away_score = row["home_score"], row["away_score"]
            if (isinstance(home_score, bool) or not isinstance(home_score, int) or home_score < 0
                    or isinstance(away_score, bool) or not isinstance(away_score, int) or away_score < 0):
                raise ValueError
            if not row["home_team_source_id"] or not row["away_team_source_id"]:
                raise ValueError
            if row["home_team_source_id"] == row["away_team_source_id"]:
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError):
            raise HistoricalCoverageError(f"archive_record_invalid:{index}") from None

        competition = row["competition_key"]
        by_comp[competition].append(row)
        month = local.strftime("%Y-%m")
        global_months[month] += 1
        kickoff_dates.add(local_day.isoformat())
        total_goals += home_score + away_score
        max_team_score = max(max_team_score, home_score, away_score)
        for side in ("home", "away"):
            team_id = row[f"{side}_team_source_id"]
            team_name = row[f"{side}_team_name"]
            team_appearances[competition][team_id] += 1
            team_names[competition][team_id].add(team_name)
        slot = (
            competition, local.isoformat(), row["home_team_source_id"],
            row["away_team_source_id"],
        )
        slots[slot] += 1

    per_competition = {}
    duplicate_slots = 0
    team_name_conflicts = 0
    for competition in sorted(archive["competition_scope"]):
        comp_rows = by_comp.get(competition, [])
        dates = sorted({
            datetime.fromisoformat(row["kickoff_at"].replace("Z", "+00:00"))
            .astimezone(zone).date().isoformat()
            for row in comp_rows
        })
        comp_teams = team_appearances[competition]
        conflicts = sum(1 for names in team_names[competition].values() if len(names) > 1)
        team_name_conflicts += conflicts
        duplicate_count = sum(count - 1 for key, count in slots.items()
                              if key[0] == competition and count > 1)
        duplicate_slots += duplicate_count
        scores = [
            row["home_score"] + row["away_score"]
            for row in comp_rows
        ]
        per_competition[competition] = {
            "accepted_finished_matches": len(comp_rows),
            "active_calendar_days": len(dates),
            "first_match_local_date": dates[0] if dates else None,
            "last_match_local_date": dates[-1] if dates else None,
            "unique_provider_team_ids": len(comp_teams),
            "team_name_variants_for_same_id": conflicts,
            "duplicate_match_slots": duplicate_count,
            "total_goals": sum(scores),
            "mean_total_goals": round(sum(scores) / len(scores), 4) if scores else None,
            "max_team_score": max(
                (max(row["home_score"], row["away_score"]) for row in comp_rows),
                default=None,
            ),
        }

    report = {
        "schema_version": 1,
        "report_type": "veltrix_fivedollar_historical_coverage_profile",
        "source_archive_sha256": verified["archive_sha256"],
        "target_window": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "timezone": "Africa/Lagos",
            "inclusive_calendar_dates": True,
            "calendar_days_requested": (end - start).days + 1,
        },
        "acquisition_coverage": {
            "batch_count": verified["batch_count"],
            "page_fetches": archive["request_budget"]["actual_requests"],
            "provider_page_coverage_complete": True,
            "provider_catalogue_completeness_claimed": False,
            "historical_match_completeness_claimed": False,
        },
        "quality": {
            "accepted_finished_matches": len(records),
            "matches_by_month": {month: global_months.get(month, 0) for month in months},
            "active_calendar_days": len(kickoff_dates),
            "unique_match_slots": len(slots),
            "duplicate_match_slots": duplicate_slots,
            "team_name_variants_for_same_id": team_name_conflicts,
            "total_goals": total_goals,
            "mean_total_goals": round(total_goals / len(records), 4) if records else None,
            "maximum_team_score": max_team_score if records else None,
            "unavailable_metrics": [
                "xg", "shots", "lineups", "player_minutes", "odds",
                "elo_point_in_time", "ppda", "travel_and_fatigue",
            ],
        },
        "competitions": per_competition,
        "training_readiness": {
            "ready_for_model_training": False,
            "reason": "Coverage profiling is not point-in-time feature validation or leakage-safe model certification",
            "next_required_work": [
                "independent source completeness assessment",
                "team identity and season continuity review",
                "feature provenance and as_of_timestamp contracts",
                "chronological train-validation-test partition",
                "point-in-time odds and lineup availability audit",
            ],
        },
        "side_effects": {
            "provider_requests": 0,
            "database_writes": 0,
            "imports": 0,
            "model_training_runs": 0,
            "prediction_publications": 0,
        },
    }
    report["report_sha256"] = _digest(report)
    return report


def validate_fivedollar_coverage_profile(report: Any) -> dict:
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise HistoricalCoverageError("coverage_profile_schema_invalid")
    if report.get("report_type") != "veltrix_fivedollar_historical_coverage_profile":
        raise HistoricalCoverageError("coverage_profile_type_invalid")
    supplied = report.get("report_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64:
        raise HistoricalCoverageError("coverage_profile_hash_invalid")
    unhashed = dict(report)
    unhashed.pop("report_sha256", None)
    if _digest(unhashed) != supplied:
        raise HistoricalCoverageError("coverage_profile_hash_mismatch")
    quality = report.get("quality")
    competitions = report.get("competitions")
    readiness = report.get("training_readiness")
    if not isinstance(quality, dict) or not isinstance(competitions, dict) or not isinstance(readiness, dict):
        raise HistoricalCoverageError("coverage_profile_sections_invalid")
    total = quality.get("accepted_finished_matches")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise HistoricalCoverageError("coverage_match_count_invalid")
    if sum(report.get("quality", {}).get("matches_by_month", {}).values()) != total:
        raise HistoricalCoverageError("coverage_month_totals_mismatch")
    if sum(item.get("accepted_finished_matches", -1) for item in competitions.values()) != total:
        raise HistoricalCoverageError("coverage_competition_totals_mismatch")
    if readiness.get("ready_for_model_training") is not False:
        raise HistoricalCoverageError("coverage_profile_cannot_certify_training")
    side_effects = report.get("side_effects")
    if not isinstance(side_effects, dict) or any(side_effects.get(key) != 0 for key in (
        "provider_requests", "database_writes", "imports", "model_training_runs",
        "prediction_publications",
    )):
        raise HistoricalCoverageError("coverage_side_effect_boundary_invalid")
    return {
        "valid": True,
        "report_sha256": supplied,
        "accepted_finished_matches": total,
        "competition_count": len(competitions),
        "ready_for_model_training": False,
    }
