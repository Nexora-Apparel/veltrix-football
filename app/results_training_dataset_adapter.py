"""Bridge results-only feature reconstruction into the PIT training dataset contract.

This adapter preserves source retrieval timestamps for every derived feature,
then delegates snapshot validation, exact fixture joins, label provenance and
chronological splits to the existing contract. It performs no model training.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from app.chronological_training_dataset import (
    assemble_chronological_training_dataset,
)
from app.point_in_time_feature_contract import (
    build_point_in_time_feature_snapshot,
)
from app.feature_source_qualification import (
    FeatureSourceQualificationError, verify_feature_source_qualification_registry,
)
from app.results_feature_reconstruction import (
    FeatureReconstructionError,
    reconstruct_pre_match_features,
)
from app.canonical_team_crosswalk import (
    TeamCrosswalkError, verify_team_crosswalk_registry,
)
from datetime import datetime, timedelta


class ResultsTrainingAdapterError(ValueError):
    pass


def build_results_history_snapshot(*, historical_matches: list[dict],
                                   target_fixture: dict,
                                   cutoff_hours: int = 6,
                                   form_window: int = 10,
                                   minimum_team_matches: int = 3,
                                   feature_source_qualification_registry: dict | None = None,
                                   trusted_kms_clients: dict | None = None,
                                   team_crosswalk_registry: dict | None = None) -> dict:
    # A target is also one of the admitted historical rows. Remove that row
    # before reconstruction; otherwise the target leaks into its own history
    # and the reconstruction contract correctly rejects the duplicate fixture.
    target_rows = [row for row in historical_matches
                   if isinstance(row, dict)
                   and row.get("fixture_id") == target_fixture.get("fixture_id")]
    if len(target_rows) > 1:
        raise ResultsTrainingAdapterError("duplicate_target_identity_rows")
    target_row = target_rows[0] if target_rows else None
    target_history = [row for row in historical_matches
                      if not isinstance(row, dict)
                      or row.get("fixture_id") != target_fixture.get("fixture_id")]

    if team_crosswalk_registry is not None:
        if not isinstance(trusted_kms_clients, dict) or not trusted_kms_clients:
            raise ResultsTrainingAdapterError("team_crosswalk_trusted_kms_clients_required")
        try:
            kickoff = datetime.fromisoformat(
                target_fixture["kickoff_at"].replace("Z", "+00:00")
            )
            if kickoff.tzinfo is None or kickoff.utcoffset() is None:
                raise ValueError("target_kickoff_timezone_missing")
            feature_as_of = (kickoff - timedelta(hours=cutoff_hours)).isoformat()
            verified_team_registry = verify_team_crosswalk_registry(
                registry=team_crosswalk_registry,
                trusted_kms_clients=trusted_kms_clients,
                as_of=feature_as_of,
            )
        except (TeamCrosswalkError, KeyError, TypeError, ValueError) as exc:
            raise ResultsTrainingAdapterError(
                f"team_crosswalk_registry_rejected_at_feature_cutoff:{exc}"
            ) from None

        def pair_is_valid(row):
            if not isinstance(row, dict):
                return False
            evidence = row.get("team_identity_evidence")
            if not isinstance(evidence, dict):
                return False
            if (evidence.get("registry_sha256") != verified_team_registry["registry_sha256"]
                    or evidence.get("signing_key_arn") != verified_team_registry["signing_key_arn"]):
                return False
            home_source = row.get("home_team_source_id")
            away_source = row.get("away_team_source_id")
            home = verified_team_registry["mappings"].get(
                (row.get("provider"), row.get("competition_id"), home_source)
            )
            away = verified_team_registry["mappings"].get(
                (row.get("provider"), row.get("competition_id"), away_source)
            )
            return bool(
                home and away
                and home["canonical_team_id"] == row.get("home_team_id")
                and away["canonical_team_id"] == row.get("away_team_id")
                and home["canonical_team_id"] != away["canonical_team_id"]
                and home["team_scope"] == away["team_scope"]
                and home["team_scope"] == evidence.get("team_scope")
            )

        if target_row is None or not pair_is_valid(target_row):
            raise ResultsTrainingAdapterError(
                "target_team_identity_not_valid_at_feature_cutoff"
            )
        target_history = [row for row in target_history if pair_is_valid(row)]

    reconstructed = reconstruct_pre_match_features(
        historical_matches=target_history,
        target_fixture=target_fixture,
        cutoff_hours=cutoff_hours,
        form_window=form_window,
        minimum_team_matches=minimum_team_matches,
    )
    source = reconstructed["provenance"]["source_provenance"]
    snapshot_features = []
    for name, value in sorted(reconstructed["features"].items()):
        snapshot_features.append({
            "name": name,
            "value": value,
            "source": source["source"],
            "source_id": source["source_id"],
            "observed_at": source["observed_at"],
            "available_at": source["available_at"],
            "retrieved_at": source["retrieved_at"],
            "payload_sha256": source["payload_sha256"],
        })
    verified_source_registry = None
    if feature_source_qualification_registry is not None:
        if not isinstance(trusted_kms_clients, dict) or not trusted_kms_clients:
            raise ResultsTrainingAdapterError("feature_source_trusted_kms_clients_required")
        try:
            verified_source_registry = verify_feature_source_qualification_registry(
                registry=feature_source_qualification_registry,
                trusted_kms_clients=trusted_kms_clients,
                as_of=reconstructed["feature_as_of"],
            )
        except FeatureSourceQualificationError as exc:
            raise ResultsTrainingAdapterError(
                f"feature_source_registry_rejected:{exc}"
            ) from None
    return build_point_in_time_feature_snapshot(
        fixture_id=reconstructed["fixture_id"],
        prediction_as_of=reconstructed["feature_as_of"],
        features=snapshot_features,
        verified_source_registry=verified_source_registry,
        competition_id=reconstructed["competition_id"],
    )


def assemble_results_history_dataset(*, historical_matches: list[dict],
                                      target_fixtures: list[dict],
                                      settled_labels: list[dict],
                                      split_policy: dict,
                                      cutoff_hours: int = 6,
                                      form_window: int = 10,
                                      minimum_team_matches: int = 3,
                                      feature_source_qualification_registry: dict | None = None,
                                      trusted_kms_clients: dict | None = None,
                                      team_crosswalk_registry: dict | None = None) -> dict:
    if not isinstance(target_fixtures, list) or not isinstance(settled_labels, list):
        raise ResultsTrainingAdapterError("targets_and_labels_must_be_arrays")
    snapshots = []
    withheld = []
    for index, target in enumerate(target_fixtures):
        try:
            snapshot = build_results_history_snapshot(
                historical_matches=historical_matches,
                target_fixture=target,
                cutoff_hours=cutoff_hours,
                form_window=form_window,
                minimum_team_matches=minimum_team_matches,
                feature_source_qualification_registry=feature_source_qualification_registry,
                trusted_kms_clients=trusted_kms_clients,
                team_crosswalk_registry=team_crosswalk_registry,
            )
            snapshots.append(snapshot)
        except (FeatureReconstructionError, ValueError, KeyError) as exc:
            fixture_id = target.get("fixture_id") if isinstance(target, dict) else None
            withheld.append({
                "fixture_id": fixture_id or f"target-index-{index}",
                "reason": str(exc)[:160],
            })

    admitted_ids = {snapshot["fixture_id"] for snapshot in snapshots}
    selected_labels = [
        label for label in settled_labels
        if isinstance(label, dict) and label.get("fixture_id") in admitted_ids
    ]
    label_ids = {
        label.get("fixture_id") for label in settled_labels
        if isinstance(label, dict)
    }
    targets_without_labels = sorted(admitted_ids - label_ids)
    labels_without_admitted_targets = sorted(label_ids - admitted_ids)
    if targets_without_labels:
        raise ResultsTrainingAdapterError(
            f"admitted_targets_missing_settled_labels:{len(targets_without_labels)}"
        )

    dataset = assemble_chronological_training_dataset(
        snapshots=snapshots,
        settled_labels=selected_labels,
        split_policy=split_policy,
    )
    reasons = Counter(item["reason"].split(":", 1)[0] for item in withheld)
    return {
        "dataset": dataset,
        "feature_reconstruction": {
            "target_fixture_count": len(target_fixtures),
            "snapshot_count": len(snapshots),
            "snapshots": snapshots,
            "withheld_count": len(withheld),
            "withheld_by_reason": dict(sorted(reasons.items())),
            "withheld": withheld,
            "labels_without_admitted_targets": labels_without_admitted_targets,
            "model_training_started": False,
            "database_writes": 0,
            "prediction_publications": 0,
        },
    }
