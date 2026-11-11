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
from app.canonical_season_crosswalk import (
    SeasonCrosswalkError, verify_season_crosswalk_registry,
)
from app.canonical_team_crosswalk import (
    TeamCrosswalkError, verify_team_crosswalk_registry,
)
from app.feature_source_qualification import (
    FeatureSourceQualificationError, verify_feature_source_qualification_registry,
    validate_feature_source,
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
    season_crosswalk_registry: dict | None = None,
    trusted_kms_clients: dict | None = None,
    season_crosswalk_as_of: str | None = None,
    team_crosswalk_registry: dict | None = None,
    team_crosswalk_as_of: str | None = None,
    feature_source_qualification_registry: dict | None = None,
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

    crosswalk_verified = None
    if season_crosswalk_registry is not None:
        if not isinstance(trusted_kms_clients, dict) or not trusted_kms_clients:
            raise HistoricalSourceCoverageError("season_crosswalk_trusted_keys_required")
        if not isinstance(season_crosswalk_as_of, str) or not season_crosswalk_as_of:
            raise HistoricalSourceCoverageError("season_crosswalk_as_of_required")
        try:
            crosswalk_verified = verify_season_crosswalk_registry(
                registry=season_crosswalk_registry,
                trusted_kms_clients=trusted_kms_clients,
                as_of=season_crosswalk_as_of,
            )
        except SeasonCrosswalkError as exc:
            raise HistoricalSourceCoverageError(
                f"season_crosswalk_registry_rejected:{exc}"
            ) from None
    elif season_crosswalk_as_of is not None:
        raise HistoricalSourceCoverageError("season_crosswalk_inputs_incomplete")

    team_crosswalk_verified = None
    if team_crosswalk_registry is not None:
        if not isinstance(trusted_kms_clients, dict) or not trusted_kms_clients:
            raise HistoricalSourceCoverageError("team_crosswalk_trusted_keys_required")
        if not isinstance(team_crosswalk_as_of, str) or not team_crosswalk_as_of:
            raise HistoricalSourceCoverageError("team_crosswalk_as_of_required")
        try:
            team_crosswalk_verified = verify_team_crosswalk_registry(
                registry=team_crosswalk_registry,
                trusted_kms_clients=trusted_kms_clients,
                as_of=team_crosswalk_as_of,
            )
        except TeamCrosswalkError as exc:
            raise HistoricalSourceCoverageError(
                f"team_crosswalk_registry_rejected:{exc}"
            ) from None
    elif team_crosswalk_as_of is not None:
        raise HistoricalSourceCoverageError("team_crosswalk_inputs_incomplete")
    if (trusted_kms_clients is not None
            and season_crosswalk_registry is None
            and team_crosswalk_registry is None):
        raise HistoricalSourceCoverageError("crosswalk_trust_without_registry")

    accepted_by_id = {}
    competition_records = defaultdict(list)
    team_appearances = defaultdict(Counter)
    canonical_team_appearances = defaultdict(Counter)
    team_mapping_failures = Counter()
    team_scope_by_canonical_id = {}
    provider_counts = Counter()
    provider_input_counts = Counter()
    provider_rejected_counts = Counter()
    provider_rejection_reasons = defaultdict(Counter)
    provider_settlement_provenance = defaultdict(Counter)
    settlement_sources = Counter()
    kickoff_dates = defaultdict(set)
    source_seasons = defaultdict(Counter)
    missing_season_counts = Counter()
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
        settled = _utc(record.get("settled_at"), f"{fixture_id}_settled")
        retrieved_value = record.get("retrieved_at")
        if retrieved_value is None:
            provider_settlement_provenance[provider]["retrieval_timestamp_missing"] += 1
        else:
            retrieved = _utc(retrieved_value, f"{fixture_id}_retrieved")
            provider_settlement_provenance[provider]["retrieval_timestamp_present"] += 1
            if retrieved < settled:
                raise HistoricalSourceCoverageError(
                    f"provider_retrieval_precedes_settlement:{fixture_id}"
                )
            provider_settlement_provenance[provider]["retrieval_after_settlement"] += 1
        if settled < kickoff:
            raise HistoricalSourceCoverageError(f"settlement_precedes_kickoff:{fixture_id}")
        provider_settlement_provenance[provider]["settlement_timestamp_present"] += 1
        accepted_by_id[fixture_id] = record
        competition_records[competition].append(record)
        team_appearances[competition][home] += 1
        team_appearances[competition][away] += 1
        if team_crosswalk_verified is not None:
            identity_evidence = record.get("team_identity_evidence")
            if (not isinstance(identity_evidence, dict)
                    or identity_evidence.get("registry_sha256") != team_crosswalk_verified["registry_sha256"]
                    or identity_evidence.get("signing_key_arn") != team_crosswalk_verified["signing_key_arn"]):
                raise HistoricalSourceCoverageError(
                    f"accepted_record_team_identity_registry_mismatch:{fixture_id}"
                )
            source_ids = (
                record.get("home_team_source_id"),
                record.get("away_team_source_id"),
            )
            if source_ids != (
                identity_evidence.get("home_source_team_id"),
                identity_evidence.get("away_source_team_id"),
            ):
                raise HistoricalSourceCoverageError(
                    f"accepted_record_team_source_identity_mismatch:{fixture_id}"
                )
            for source_team_id, canonical_id in zip(source_ids, (home, away)):
                identity = (provider, competition, source_team_id)
                mapping = team_crosswalk_verified["mappings"].get(identity)
                if (mapping is None
                        or mapping.get("canonical_team_id") != canonical_id
                        or mapping.get("team_scope") != identity_evidence.get("team_scope")):
                    raise HistoricalSourceCoverageError(
                        f"accepted_record_team_crosswalk_binding_invalid:{fixture_id}"
                    )
                scope = mapping["team_scope"]
                prior_scope = team_scope_by_canonical_id.get(canonical_id)
                if prior_scope is not None and prior_scope != scope:
                    raise HistoricalSourceCoverageError("canonical_team_scope_collision")
                team_scope_by_canonical_id[canonical_id] = scope
                canonical_team_appearances[competition][canonical_id] += 1
        provider_counts[provider] += 1
        settlement_sources[record.get("settlement_source_id", "unknown")] += 1
        kickoff_dates[competition].add(kickoff.date().isoformat())
        source_season = record.get("source_season")
        if isinstance(source_season, str) and source_season.strip():
            source_seasons[competition][source_season.strip()] += 1
        else:
            missing_season_counts[competition] += 1

    feature_source_qualification = {
        "verified": False, "registry_sha256": None, "signing_key_arn": None,
        "qualified_feature_cells": 0, "source_feature_counts": {},
        "rejected_feature_cells": 0, "status": "unverified",
    }
    if feature_source_qualification_registry is not None:
        if not isinstance(trusted_kms_clients, dict) or not trusted_kms_clients:
            raise HistoricalSourceCoverageError("feature_source_trusted_keys_required")
        source_feature_counts = Counter()
        qualified_cells = 0
        for index, snapshot in enumerate(snapshots):
            if not isinstance(snapshot, dict):
                raise HistoricalSourceCoverageError(f"feature_snapshot_invalid:{index}")
            fixture_id = snapshot.get("fixture_id")
            prediction_as_of = snapshot.get("prediction_as_of")
            accepted_record = accepted_by_id.get(fixture_id)
            if accepted_record is None:
                raise HistoricalSourceCoverageError(
                    f"feature_snapshot_fixture_not_admitted:{fixture_id}"
                )
            try:
                verified_source_registry = verify_feature_source_qualification_registry(
                    registry=feature_source_qualification_registry,
                    trusted_kms_clients=trusted_kms_clients,
                    as_of=prediction_as_of,
                )
            except FeatureSourceQualificationError as exc:
                raise HistoricalSourceCoverageError(
                    f"feature_source_registry_rejected:{exc}"
                ) from None
            for feature in snapshot.get("features", []):
                qualification = feature.get("source_qualification") if isinstance(feature, dict) else None
                if not isinstance(qualification, dict):
                    raise HistoricalSourceCoverageError(
                        f"feature_source_qualification_missing:{fixture_id}"
                    )
                try:
                    expected = validate_feature_source(
                        verified_registry=verified_source_registry,
                        source=feature.get("source"),
                        feature_name=feature.get("name"),
                        competition_id=accepted_record["competition_id"],
                    )
                except FeatureSourceQualificationError as exc:
                    raise HistoricalSourceCoverageError(
                        f"feature_source_not_qualified:{fixture_id}:{exc}"
                    ) from None
                if qualification != expected:
                    raise HistoricalSourceCoverageError(
                        f"feature_source_qualification_binding_mismatch:{fixture_id}"
                    )
                source_feature_counts[feature["source"]] += 1
                qualified_cells += 1
            if feature_source_qualification["registry_sha256"] not in (
                None, verified_source_registry["registry_sha256"]
            ):
                raise HistoricalSourceCoverageError("feature_source_registry_changed_across_snapshots")
            feature_source_qualification["registry_sha256"] = verified_source_registry["registry_sha256"]
            feature_source_qualification["signing_key_arn"] = verified_source_registry["signing_key_arn"]
        feature_source_qualification.update({
            "verified": bool(snapshots),
            "qualified_feature_cells": qualified_cells,
            "source_feature_counts": dict(sorted(source_feature_counts.items())),
            "status": "verified" if snapshots else "no_feature_snapshots",
        })
    elif snapshots:
        feature_source_qualification["rejected_feature_cells"] = sum(
            len(item.get("features", [])) for item in snapshots if isinstance(item, dict)
        )

    rejected_records = eligibility.get("rejected_records", [])
    if not isinstance(rejected_records, list):
        raise HistoricalSourceCoverageError("rejected_records_invalid")
    for index, rejected in enumerate(rejected_records):
        if not isinstance(rejected, dict):
            raise HistoricalSourceCoverageError(f"rejected_record_invalid:{index}")
        provider = rejected.get("provider")
        reason = rejected.get("reason")
        if provider is None:
            # Malformed identities cannot be attributed to a provider.
            continue
        if not isinstance(provider, str) or not provider.strip() or not isinstance(reason, str) or not reason:
            raise HistoricalSourceCoverageError(f"rejected_provider_identity_invalid:{index}")
        provider_rejected_counts[provider] += 1
        provider_rejection_reasons[provider][reason.split(":", 1)[0]] += 1

    for provider, accepted_count in provider_counts.items():
        provider_input_counts[provider] += accepted_count
    for provider, rejected_count in provider_rejected_counts.items():
        provider_input_counts[provider] += rejected_count

    season_resolutions = {}
    season_mapping_failures = Counter()
    if crosswalk_verified is not None:
        for fixture_id, record in accepted_by_id.items():
            source_season = record.get("source_season")
            if not isinstance(source_season, str) or not source_season.strip():
                season_mapping_failures[record["competition_id"]] += 1
                continue
            identity = (record["provider"], record["competition_id"], source_season.strip())
            mapping = crosswalk_verified["mappings"].get(identity)
            if mapping is None:
                season_mapping_failures[record["competition_id"]] += 1
            else:
                season_resolutions[fixture_id] = mapping

    snapshot_by_id = {}
    feature_source_counts = Counter()
    feature_source_ids = Counter()
    feature_sources_by_name = defaultdict(Counter)
    feature_source_ids_by_name = defaultdict(Counter)
    feature_availability_lag_seconds = defaultdict(list)
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
            feature_sources_by_name[feature["name"]][feature["source"]] += 1
            feature_source_ids_by_name[feature["name"]][feature["source_id"]] += 1
            available = _utc(feature["available_at"], f"{fixture_id}_{feature['name']}_available")
            observed = _utc(feature["observed_at"], f"{fixture_id}_{feature['name']}_observed")
            retrieved = _utc(feature["retrieved_at"], f"{fixture_id}_{feature['name']}_retrieved")
            cutoff = _utc(snapshot["prediction_as_of"], f"{fixture_id}_prediction_as_of")
            if available < observed or retrieved < available or available > cutoff:
                raise HistoricalSourceCoverageError(
                    f"feature_source_chronology_invalid:{fixture_id}:{feature['name']}"
                )
            feature_availability_lag_seconds[feature["name"]].append(
                (retrieved - available).total_seconds()
            )

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
        source_teams = len(team_appearances[competition])
        canonical_teams = len(canonical_team_appearances[competition])
        all_team_ids_mapped = (
            team_crosswalk_verified is not None
            and team_mapping_failures[competition] == 0
            and canonical_team_appearances[competition]
        )
        teams = canonical_teams if team_crosswalk_verified is not None else None
        included = included_by_competition[competition]
        snapshots_count = sum(1 for record in records if record["fixture_id"] in snapshot_by_id)
        meets_fixtures = fixtures >= minimum_fixtures_per_competition
        meets_teams = bool(all_team_ids_mapped) and canonical_teams >= minimum_distinct_teams_per_competition
        season_values = source_seasons[competition]
        missing_seasons = missing_season_counts[competition]
        canonical_season_counts = Counter(
            season_resolutions[record["fixture_id"]]["canonical_season_id"]
            for record in records if record["fixture_id"] in season_resolutions
        )
        mapped_seasons = sum(canonical_season_counts.values())
        mapping_failures = season_mapping_failures[competition]
        if not season_values:
            season_status = "not_available"
        elif mapped_seasons == fixtures and mapping_failures == 0:
            season_status = "verified"
        elif mapped_seasons:
            season_status = "partially_verified"
        elif missing_seasons:
            season_status = "partially_reported"
        else:
            season_status = "source_reported_crosswalk_unverified"
        item = {
            "settlement_eligible_fixtures": fixtures,
            "distinct_teams": teams,
            "distinct_source_team_ids": source_teams,
            "canonical_distinct_teams": canonical_teams,
            "team_identity": {
                "status": (
                    "verified" if all_team_ids_mapped
                    else "partially_verified" if canonical_teams
                    else "unverified"
                ),
                "canonical_team_crosswalk_verified": bool(all_team_ids_mapped),
                "unmapped_team_appearances": team_mapping_failures[competition],
                "crosswalk_registry_sha256": (
                    team_crosswalk_verified["registry_sha256"] if team_crosswalk_verified else None
                ),
            },
            "feature_snapshots": snapshots_count,
            "dataset_rows": included,
            "distinct_kickoff_dates": len(kickoff_dates[competition]),
            "season_coverage": {
                "status": season_status,
                "source_reported_season_counts": dict(sorted(season_values.items())),
                "records_missing_season": missing_seasons,
                "distinct_source_seasons": len(season_values),
                "canonical_season_counts": dict(sorted(canonical_season_counts.items())),
                "mapped_records": mapped_seasons,
                "unmapped_records": fixtures - mapped_seasons,
                "canonical_season_crosswalk_verified": bool(
                    fixtures and mapped_seasons == fixtures and mapping_failures == 0
                ),
                "crosswalk_registry_sha256": (
                    crosswalk_verified["registry_sha256"] if crosswalk_verified else None
                ),
                "reason": (
                    "all provider/competition/source-season labels resolved through the trusted signed crosswalk"
                    if season_status == "verified"
                    else "source season labels require an exact reviewed provider/competition/source-season mapping"
                ),
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
            if team_crosswalk_verified is None or team_mapping_failures[competition]:
                threshold_failures.append(f"{competition}:team_identity_crosswalk_unverified")

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
            "source_record_counts": dict(sorted(feature_sources_by_name[name].items())),
            "distinct_source_id_count": len(feature_source_ids_by_name[name]),
            "availability_to_retrieval_lag_seconds": {
                "minimum": min(feature_availability_lag_seconds[name])
                if feature_availability_lag_seconds[name] else None,
                "maximum": max(feature_availability_lag_seconds[name])
                if feature_availability_lag_seconds[name] else None,
                "mean": (
                    sum(feature_availability_lag_seconds[name])
                    / len(feature_availability_lag_seconds[name])
                    if feature_availability_lag_seconds[name] else None
                ),
            },
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
    if not feature_source_qualification["verified"]:
        threshold_failures.append("feature_source_qualification_unverified")
    if not competition_report:
        threshold_failures.append("no_competition_coverage")
    elif any(item["season_coverage"]["status"] != "verified" for item in competition_report.values()):
        threshold_failures.append("season_crosswalk_unverified")

    report = {
        "schema_version": 1,
        "report_type": "veltrix_historical_source_coverage_qualification",
        "settlement_source_coverage": {
            "input_records": input_count,
            "settlement_eligible_records": len(accepted),
            "rejected_records": rejected_count,
            "settlement_eligibility_rate": len(accepted) / input_count if input_count else 0.0,
            "accepted_by_provider": dict(sorted(provider_counts.items())),
            "rejected_by_provider": dict(sorted(provider_rejected_counts.items())),
            "provider_quality": {
                provider: {
                    "input_records": provider_input_counts[provider],
                    "accepted_records": provider_counts[provider],
                    "rejected_records": provider_rejected_counts[provider],
                    "acceptance_rate": (
                        provider_counts[provider] / provider_input_counts[provider]
                        if provider_input_counts[provider] else 0.0
                    ),
                    "rejection_reasons": dict(sorted(provider_rejection_reasons[provider].items())),
                    "settlement_timestamp_provenance": dict(sorted(
                        provider_settlement_provenance[provider].items()
                    )),
                }
                for provider in sorted(set(provider_input_counts) | set(provider_counts))
            },
            "unattributed_rejections": sum(
                1 for item in rejected_records
                if isinstance(item, dict) and item.get("provider") is None
            ),
            "accepted_by_settlement_source": dict(sorted(settlement_sources.items())),
        },
        "competition_coverage": competition_report,
        "team_coverage": {
            competition: {
                "distinct_source_team_ids": len(counts),
                "source_team_id_fixture_appearances": dict(sorted(counts.items())),
                "distinct_canonical_teams": len(canonical_team_appearances[competition]),
                "canonical_team_fixture_appearances": dict(sorted(
                    canonical_team_appearances[competition].items()
                )),
                "canonical_team_crosswalk_verified": bool(
                    team_crosswalk_verified is not None
                    and team_mapping_failures[competition] == 0
                    and canonical_team_appearances[competition]
                ),
            }
            for competition, counts in sorted(team_appearances.items())
        },
        "feature_source_qualification": feature_source_qualification,
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
                or reason == "feature_source_qualification_unverified"
                or reason == "season_crosswalk_unverified"
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
