"""Coverage qualification report for admitted historical football datasets.

This is a descriptive, fail-closed coverage layer. It does not qualify a
provider contract, prove historical availability, train models or authorize
publication. Season coverage is explicitly unavailable until season identity
is carried by reviewed source evidence.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from app.point_in_time_feature_contract import (
    FEATURE_CATALOGUE, validate_point_in_time_feature_snapshot,
)


class HistoricalSourceCoverageError(ValueError):
    pass


def _digest(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise HistoricalSourceCoverageError("coverage_report_not_canonical_json") from None
    return hashlib.sha256(raw).hexdigest()


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise HistoricalSourceCoverageError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HistoricalSourceCoverageError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HistoricalSourceCoverageError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def build_historical_source_coverage_report(
    pipeline_report: Any,
    *,
    minimum_fixtures_per_competition: int = 100,
    minimum_distinct_teams_per_competition: int = 16,
    minimum_feature_coverage_rate: float = 0.95,
) -> dict:
    """Measure admitted source coverage; never infer missing season identity."""
    if not isinstance(pipeline_report, dict):
        raise HistoricalSourceCoverageError("pipeline_report_invalid")
    for name, value, minimum in (
        ("minimum_fixtures_per_competition", minimum_fixtures_per_competition, 1),
        ("minimum_distinct_teams_per_competition", minimum_distinct_teams_per_competition, 2),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise HistoricalSourceCoverageError(f"{name}_invalid")
    if (isinstance(minimum_feature_coverage_rate, bool)
            or not isinstance(minimum_feature_coverage_rate, (int, float))
            or not 0 < minimum_feature_coverage_rate <= 1):
        raise HistoricalSourceCoverageError("minimum_feature_coverage_rate_invalid")

    eligibility = pipeline_report.get("acquisition_eligibility")
    reconstruction = pipeline_report.get("feature_reconstruction")
    dataset = pipeline_report.get("dataset")
    if not isinstance(eligibility, dict) or not isinstance(reconstruction, dict):
        raise HistoricalSourceCoverageError("pipeline_sections_missing")
    accepted = eligibility.get("accepted_records")
    snapshots = reconstruction.get("snapshots")
    if not isinstance(accepted, list) or not isinstance(snapshots, list):
        raise HistoricalSourceCoverageError("coverage_input_arrays_invalid")
    rows = [] if dataset is None else dataset.get("rows") if isinstance(dataset, dict) else None
    if not isinstance(rows, list):
        raise HistoricalSourceCoverageError("dataset_rows_invalid")

    accepted_by_id = {}
    competition_records = defaultdict(list)
    team_appearances = defaultdict(Counter)
    provider_counts = Counter()
    settlement_sources = Counter()
    kickoff_dates = defaultdict(set)
    for index, record in enumerate(accepted):
        if not isinstance(record, dict):
            raise HistoricalSourceCoverageError(f"accepted_record_invalid:{index}")
        fixture_id = record.get("fixture_id")
        competition = record.get("competition_id")
        provider = record.get("provider")
        home, away = record.get("home_team_id"), record.get("away_team_id")
        if (not isinstance(fixture_id, str) or not fixture_id
                or fixture_id in accepted_by_id):
            raise HistoricalSourceCoverageError(f"accepted_fixture_identity_invalid:{index}")
        if not all(isinstance(x, str) and x.strip() for x in (competition, provider, home, away)):
            raise HistoricalSourceCoverageError(f"accepted_record_scope_invalid:{fixture_id}")
        if home == away:
            raise HistoricalSourceCoverageError(f"accepted_record_same_team:{fixture_id}")
        kickoff = _utc(record.get("kickoff_at"), f"{fixture_id}_kickoff")
        _utc(record.get("settled_at"), f"{fixture_id}_settled")
        accepted_by_id[fixture_id] = record
        competition_records[competition].append(record)
        team_appearances[competition][home] += 1
        team_appearances[competition][away] += 1
        provider_counts[provider] += 1
        settlement_sources[record.get("settlement_source_id", "unknown")] += 1
        kickoff_dates[competition].add(kickoff.date().isoformat())

    snapshot_by_id = {}
    feature_source_counts = Counter()
    feature_source_ids = Counter()
    for index, snapshot in enumerate(snapshots):
        try:
            validate_point_in_time_feature_snapshot(snapshot)
        except (ValueError, TypeError, KeyError) as exc:
            raise HistoricalSourceCoverageError(
                f"feature_snapshot_invalid:{index}:{str(exc)[:100]}"
            ) from None
        fixture_id = snapshot["fixture_id"]
        if fixture_id in snapshot_by_id or fixture_id not in accepted_by_id:
            raise HistoricalSourceCoverageError(f"snapshot_fixture_join_invalid:{fixture_id}")
        snapshot_by_id[fixture_id] = snapshot
        for feature in snapshot["features"]:
            feature_source_counts[feature["source"]] += 1
            feature_source_ids[feature["source_id"]] += 1

    included_by_competition = Counter()
    feature_counts = Counter()
    included_fixture_ids = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise HistoricalSourceCoverageError(f"dataset_row_invalid:{index}")
        fixture_id = row.get("fixture_id")
        record = accepted_by_id.get(fixture_id)
        snapshot = snapshot_by_id.get(fixture_id)
        if (record is None or snapshot is None
                or row.get("feature_snapshot_sha256") != snapshot["snapshot_sha256"]):
            raise HistoricalSourceCoverageError(f"dataset_row_source_join_invalid:{index}")
        if row.get("competition_key") != record["competition_id"]:
            raise HistoricalSourceCoverageError(f"dataset_row_competition_mismatch:{fixture_id}")
        values = {feature["name"]: feature["value"] for feature in snapshot["features"]}
        if values != row.get("predictors"):
            raise HistoricalSourceCoverageError(f"dataset_row_feature_mismatch:{fixture_id}")
        if fixture_id in included_fixture_ids:
            raise HistoricalSourceCoverageError(f"duplicate_dataset_fixture:{fixture_id}")
        included_fixture_ids.add(fixture_id)
        included_by_competition[record["competition_id"]] += 1
        feature_counts.update(values.keys())

    competition_report = {}
    threshold_failures = []
    for competition, records in sorted(competition_records.items()):
        fixtures = len(records)
        teams = len(team_appearances[competition])
        included = included_by_competition[competition]
        snapshots_count = sum(1 for record in records if record["fixture_id"] in snapshot_by_id)
        meets_fixtures = fixtures >= minimum_fixtures_per_competition
        meets_teams = teams >= minimum_distinct_teams_per_competition
        item = {
            "settlement_eligible_fixtures": fixtures,
            "distinct_teams": teams,
            "feature_snapshots": snapshots_count,
            "dataset_rows": included,
            "distinct_kickoff_dates": len(kickoff_dates[competition]),
            "season_coverage": {
                "status": "not_available",
                "reason": "season_id_not_present_in_qualified_acquisition_record",
                "distinct_seasons": 0,
            },
            "thresholds": {
                "minimum_fixtures": minimum_fixtures_per_competition,
                "minimum_distinct_teams": minimum_distinct_teams_per_competition,
                "fixtures_met": meets_fixtures,
                "teams_met": meets_teams,
            },
        }
        competition_report[competition] = item
        if not meets_fixtures:
            threshold_failures.append(f"{competition}:insufficient_fixtures")
        if not meets_teams:
            threshold_failures.append(f"{competition}:insufficient_team_coverage")

    feature_domains = {
        "team_strength_and_form": [
            "home_team_elo", "away_team_elo", "elo_difference_home",
            "home_attack_goals_rate", "home_defence_conceded_rate",
            "away_attack_goals_rate", "away_defence_conceded_rate",
            "home_form_points_rate", "away_form_points_rate",
        ],
        "expected_goals": [
            "home_rolling_xg_for", "home_rolling_xg_against",
            "away_rolling_xg_for", "away_rolling_xg_against",
        ],
        "lineups": ["home_lineup_strength", "away_lineup_strength"],
        "fatigue_and_travel": [
            "home_rest_days", "away_rest_days", "home_travel_km", "away_travel_km",
        ],
        "market_odds": [
            "odds_home_decimal", "odds_draw_decimal", "odds_away_decimal",
            "odds_btts_yes_decimal", "odds_over_2_5_decimal",
        ],
    }
    domain_coverage = {}
    for domain, names in feature_domains.items():
        available = [name for name in names if name in FEATURE_CATALOGUE]
        cells = sum(feature_counts[name] for name in available)
        denominator = len(rows) * len(available)
        domain_coverage[domain] = {
            "catalogue_feature_count": len(available),
            "features_present": [name for name in available if feature_counts[name] > 0],
            "features_absent": [name for name in available if feature_counts[name] == 0],
            "feature_cell_coverage_rate": cells / denominator if denominator else 0.0,
        }
    for domain in ("injury_availability", "pressing_intensity_ppda"):
        domain_coverage[domain] = {
            "catalogue_feature_count": 0,
            "features_present": [],
            "features_absent": [],
            "feature_cell_coverage_rate": 0.0,
            "status": "not_in_feature_catalogue",
        }

    feature_report = {
        name: {
            "dataset_rows_with_feature": feature_counts[name],
            "dataset_row_denominator": len(rows),
            "coverage_rate": feature_counts[name] / len(rows) if rows else 0.0,
            "meets_minimum": bool(rows) and feature_counts[name] / len(rows) >= minimum_feature_coverage_rate,
        }
        for name in sorted(FEATURE_CATALOGUE)
    }
    absent_features = [name for name, item in feature_report.items()
                       if item["dataset_rows_with_feature"] == 0]
    below_threshold_features = [name for name, item in feature_report.items()
                                if not item["meets_minimum"]]
    if below_threshold_features:
        threshold_failures.append("feature_coverage_below_threshold")

    input_count = eligibility.get("input_record_count", 0)
    rejected_count = eligibility.get("rejected_count", len(eligibility.get("rejected_records", [])))
    if (isinstance(input_count, bool) or not isinstance(input_count, int) or input_count < 0
            or isinstance(rejected_count, bool) or not isinstance(rejected_count, int)
            or rejected_count < 0 or rejected_count + len(accepted) != input_count):
        raise HistoricalSourceCoverageError("settlement_admission_count_mismatch")

    historical_availability = pipeline_report.get("historical_availability_proven") is True
    if not historical_availability:
        threshold_failures.append("historical_feature_availability_unproven")
    if not competition_report:
        threshold_failures.append("no_competition_coverage")
    elif any(item["season_coverage"]["status"] != "verified" for item in competition_report.values()):
        threshold_failures.append("season_coverage_unavailable")

    report = {
        "schema_version": 1,
        "report_type": "veltrix_historical_source_coverage_qualification",
        "settlement_source_coverage": {
            "input_records": input_count,
            "settlement_eligible_records": len(accepted),
            "rejected_records": rejected_count,
            "settlement_eligibility_rate": len(accepted) / input_count if input_count else 0.0,
            "accepted_by_provider": dict(sorted(provider_counts.items())),
            "accepted_by_settlement_source": dict(sorted(settlement_sources.items())),
        },
        "competition_coverage": competition_report,
        "team_coverage": {
            competition: {
                "distinct_teams": len(counts),
                "team_fixture_appearances": dict(sorted(counts.items())),
            }
            for competition, counts in sorted(team_appearances.items())
        },
        "feature_coverage": {
            "dataset_row_denominator": len(rows),
            "minimum_coverage_rate": minimum_feature_coverage_rate,
            "by_feature": feature_report,
            "features_absent": absent_features,
            "features_below_threshold": below_threshold_features,
            "by_data_domain": domain_coverage,
            "feature_source_record_counts": dict(sorted(feature_source_counts.items())),
            "distinct_feature_source_id_count": len(feature_source_ids),
        },
        "historical_availability": {
            "proven": historical_availability,
            "status": "verified" if historical_availability else "unproven",
            "note": "A retrospective source download does not prove the data was available at the historical prediction cutoff.",
        },
        "qualification": {
            "coverage_thresholds_met": not any(
                reason.endswith("insufficient_fixtures")
                or reason.endswith("insufficient_team_coverage")
                or reason == "feature_coverage_below_threshold"
                or reason == "season_coverage_unavailable"
                for reason in threshold_failures
            ),
            "source_coverage_qualified": not threshold_failures,
            "threshold_failures": threshold_failures,
            "training_authorized": False,
            "value_betting_enabled": False,
            "publication_allowed": False,
        },
        "side_effects": {
            "model_training_runs": 0,
            "database_writes": 0,
            "prediction_publications": 0,
        },
    }
    report["report_sha256"] = _digest(report)
    return report
