"""Evidence-checked offline daily fixture selection artifact builder."""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from app.daily_fixture_selection import select_daily_fixtures
from app.provider_acquisition_artifact import validate_acquisition_report
from app.provider_qualification_evidence import STRIKERAPI_COMPETITIONS, verify_attestation_signature


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SelectionArtifactError(ValueError):
    pass


def _canonical_hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def qualified_sources_from_registry(registry: Any) -> dict[str, list[str]]:
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise SelectionArtifactError("qualification_registry_schema_invalid")
    entries = registry.get("sources")
    if not isinstance(entries, list):
        raise SelectionArtifactError("qualification_registry_sources_invalid")

    qualified: dict[str, set[str]] = {}
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SelectionArtifactError(f"qualification_entry_invalid:{index}")
        provider = entry.get("provider")
        competition = entry.get("competition_key")
        provider_policies = {
            "strikerapi": {
                "workflow_path": ".github/workflows/verify-strikerapi-17-competitions.yml",
                "head_branch": "phase-3/strikerapi-readonly-qualification",
                "artifact_name": "strikerapi-17-competition-coverage",
            },
            "fivedollar": {
                "workflow_path": ".github/workflows/qualify-fivedollar-competitions.yml",
                "dispatch_ref": "main",
                "checkout_ref": "phase-3/budget-aware-acquisition-contract",
                "artifact_name": "fivedollar-competition-qualification",
            },
        }
        policy = provider_policies.get(provider) if isinstance(provider, str) else None
        if policy is None:
            raise SelectionArtifactError(f"qualification_provider_not_supported:{index}")
        run_id = entry.get("qualification_run_id")
        artifact_hash = entry.get("artifact_sha256")
        evidence_ref = entry.get("evidence_ref")
        if not isinstance(provider, str) or not provider.strip():
            raise SelectionArtifactError(f"qualification_provider_missing:{index}")
        if (not isinstance(competition, (str, int)) or isinstance(competition, bool)
                or not str(competition).strip()):
            raise SelectionArtifactError(f"qualification_competition_missing:{index}")
        if provider == "fivedollar" and (not str(competition).isdigit() or int(competition) <= 0):
            raise SelectionArtifactError(f"qualification_competition_invalid:{index}")
        if provider == "strikerapi" and str(competition) not in STRIKERAPI_COMPETITIONS:
            raise SelectionArtifactError(f"qualification_competition_invalid:{index}")
        if entry.get("qualification_status") != "qualified":
            raise SelectionArtifactError(f"source_not_qualified:{index}")
        attestation = entry.get("review_attestation")
        if not isinstance(attestation, dict):
            raise SelectionArtifactError(f"qualification_reviewer_attestation_missing:{index}")
        if attestation.get("attestation_version") != 1 or attestation.get("review_status") != "qualified":
            raise SelectionArtifactError(f"qualification_reviewer_attestation_invalid:{index}")
        signing_key = os.getenv("VELTRIX_QUALIFICATION_ATTESTATION_KEY", "")
        if not verify_attestation_signature(attestation, signing_key):
            raise SelectionArtifactError(f"qualification_reviewer_attestation_signature_invalid:{index}")
        if attestation.get("repository") != "Nexora-Apparel/veltrix-football":
            raise SelectionArtifactError(f"qualification_attestation_repository_invalid:{index}")
        if attestation.get("event") != "workflow_dispatch":
            raise SelectionArtifactError(f"qualification_attestation_event_invalid:{index}")
        if attestation.get("workflow_path") != policy["workflow_path"]:
            raise SelectionArtifactError(f"qualification_attestation_workflow_invalid:{index}")
        if provider == "fivedollar":
            if (attestation.get("dispatch_ref") != policy["dispatch_ref"]
                    or attestation.get("checkout_ref") != policy["checkout_ref"]):
                raise SelectionArtifactError(f"qualification_attestation_ref_invalid:{index}")
            for field in ("dispatch_sha", "checkout_sha"):
                value = attestation.get(field)
                if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
                    raise SelectionArtifactError(f"qualification_attestation_commit_invalid:{index}")
            if attestation.get("dispatch_sha") != attestation.get("head_sha"):
                raise SelectionArtifactError(f"qualification_attestation_dispatch_sha_mismatch:{index}")
        elif attestation.get("head_branch") != policy["head_branch"]:
            raise SelectionArtifactError(f"qualification_attestation_branch_invalid:{index}")
        if attestation.get("artifact_name") != policy["artifact_name"]:
            raise SelectionArtifactError(f"qualification_attestation_artifact_name_invalid:{index}")
        if not isinstance(attestation.get("reviewer"), str) or not attestation["reviewer"].strip():
            raise SelectionArtifactError(f"qualification_attestation_reviewer_missing:{index}")
        if not isinstance(attestation.get("reviewed_at"), str) or not attestation["reviewed_at"].strip():
            raise SelectionArtifactError(f"qualification_attestation_review_time_missing:{index}")
        if not isinstance(attestation.get("head_sha"), str) or not re.fullmatch(r"[0-9a-f]{40}", attestation["head_sha"]):
            raise SelectionArtifactError(f"qualification_attestation_commit_invalid:{index}")
        if not isinstance(attestation.get("artifact_id"), int) or isinstance(attestation.get("artifact_id"), bool):
            raise SelectionArtifactError(f"qualification_attestation_artifact_id_invalid:{index}")
        if attestation.get("local_archive_sha256") != artifact_hash or attestation.get("github_artifact_digest") != artifact_hash:
            raise SelectionArtifactError(f"qualification_attestation_artifact_hash_mismatch:{index}")
        if not isinstance(attestation.get("local_report_sha256"), str) or not _SHA256.fullmatch(attestation["local_report_sha256"]):
            raise SelectionArtifactError(f"qualification_attestation_report_hash_invalid:{index}")
        coverage = attestation.get("coverage")
        if not isinstance(coverage, dict):
            raise SelectionArtifactError(f"qualification_attestation_scope_invalid:{index}")
        coverage_keys = coverage.get("competition_keys")
        if (coverage.get("provider") != provider.lower()
                or not isinstance(coverage_keys, list)
                or any(not isinstance(key, str) or (provider == "fivedollar" and not key.isdigit())
                       or (provider == "strikerapi" and key not in STRIKERAPI_COMPETITIONS)
                       for key in coverage_keys)
                or len(coverage_keys) != len(set(coverage_keys))
                or coverage.get("competition_count") != len(coverage_keys)
                or str(competition) not in coverage_keys
                or coverage.get("pagination_complete") is not True
                or coverage.get("invalid_rows") != 0 or coverage.get("duplicate_rows") != 0
                or coverage.get("missing_team_ids", 0) != 0):
            raise SelectionArtifactError(f"qualification_attestation_scope_invalid:{index}")
        if provider == "fivedollar":
            for field in ("source_rows", "accepted_rows"):
                value = coverage.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise SelectionArtifactError(f"qualification_attestation_scope_invalid:{index}")
        elif provider == "strikerapi":
            final_rows = coverage.get("final_rows_by_competition")
            if (not isinstance(final_rows, dict)
                    or isinstance(final_rows.get(str(competition)), bool)
                    or not isinstance(final_rows.get(str(competition)), int)
                    or final_rows[str(competition)] <= 0):
                raise SelectionArtifactError(f"qualification_attestation_scope_invalid:{index}")
        expected_evidence_ref = (
            f"https://github.com/{attestation.get('repository')}/actions/runs/"
            f"{attestation.get('workflow_run_id')}/artifacts/{attestation.get('artifact_id')}"
        )
        if evidence_ref != expected_evidence_ref:
            raise SelectionArtifactError(f"qualification_evidence_ref_invalid:{index}")
        if not isinstance(run_id, str) or not run_id.strip():
            raise SelectionArtifactError(f"qualification_run_id_missing:{index}")
        if attestation.get("workflow_run_id") != run_id:
            raise SelectionArtifactError(f"qualification_attestation_run_mismatch:{index}")
        if not isinstance(artifact_hash, str) or not _SHA256.fullmatch(artifact_hash):
            raise SelectionArtifactError(f"qualification_artifact_hash_invalid:{index}")
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise SelectionArtifactError(f"qualification_evidence_ref_missing:{index}")
        if entry.get("pagination_complete") is not True:
            raise SelectionArtifactError(f"qualification_pagination_incomplete:{index}")
        for field in ("invalid_rows", "duplicate_rows", "missing_team_ids"):
            value = entry.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value != 0:
                raise SelectionArtifactError(f"qualification_{field}_nonzero:{index}")
        identity = (provider, str(competition))
        if identity in seen:
            raise SelectionArtifactError(f"duplicate_qualification_entry:{index}")
        seen.add(identity)
        qualified.setdefault(provider, set()).add(str(competition))

    return {provider: sorted(keys) for provider, keys in sorted(qualified.items())}


def build_daily_selection_artifact(*, acquisition_report: dict,
                                   qualification_registry: dict,
                                   target_date: str, as_of: str,
                                   max_fixtures: int = 25) -> dict:
    integrity = validate_acquisition_report(acquisition_report)
    qualified_sources = qualified_sources_from_registry(qualification_registry)
    selection = select_daily_fixtures(
        records=acquisition_report["records"],
        target_date=target_date,
        as_of=as_of,
        qualified_sources=qualified_sources,
        max_fixtures=max_fixtures,
    )
    registry_hash = _canonical_hash(qualification_registry)
    artifact = {
        "schema_version": 1,
        "artifact_type": "veltrix_daily_fixture_selection",
        "source_acquisition_report_sha256": integrity["report_sha256"],
        "qualification_registry_sha256": registry_hash,
        "selection": selection,
        "side_effects": {
            "provider_requests": 0,
            "database_writes": 0,
            "imports": 0,
            "prediction_publications": 0,
        },
    }
    artifact["selection_sha256"] = _canonical_hash(artifact)
    return artifact


def validate_daily_selection_artifact(artifact: Any) -> dict:
    if not isinstance(artifact, dict) or artifact.get("schema_version") != 1:
        raise SelectionArtifactError("selection_artifact_schema_invalid")
    if artifact.get("artifact_type") != "veltrix_daily_fixture_selection":
        raise SelectionArtifactError("selection_artifact_type_invalid")
    supplied = artifact.get("selection_sha256")
    if not isinstance(supplied, str) or not _SHA256.fullmatch(supplied):
        raise SelectionArtifactError("selection_artifact_hash_invalid")
    unhashed = dict(artifact)
    unhashed.pop("selection_sha256", None)
    if _canonical_hash(unhashed) != supplied:
        raise SelectionArtifactError("selection_artifact_hash_mismatch")
    selection = artifact.get("selection")
    if not isinstance(selection, dict) or not isinstance(selection.get("selected"), list):
        raise SelectionArtifactError("selection_payload_invalid")
    selected_count = selection.get("selected_count")
    if selected_count != len(selection["selected"]):
        raise SelectionArtifactError("selection_count_mismatch")
    if isinstance(selection.get("maximum_fixtures"), bool) or not isinstance(selection.get("maximum_fixtures"), int) or not 1 <= selection["maximum_fixtures"] <= 25:
        raise SelectionArtifactError("selection_cap_invalid")
    if selected_count > selection["maximum_fixtures"]:
        raise SelectionArtifactError("selection_cap_exceeded")
    policy = selection.get("policy")
    if not isinstance(policy, dict) or policy.get("synthetic_fixtures") != 0 or policy.get("database_writes") != 0 or policy.get("prediction_publications") != 0:
        raise SelectionArtifactError("selection_policy_boundary_invalid")
    side_effects = artifact.get("side_effects")
    if not isinstance(side_effects, dict) or any(
        side_effects.get(key) != 0
        for key in ("provider_requests", "database_writes", "imports", "prediction_publications")
    ):
        raise SelectionArtifactError("selection_side_effect_boundary_invalid")
    return {
        "valid": True,
        "selection_sha256": supplied,
        "selected_count": selected_count,
        "maximum_fixtures": selection["maximum_fixtures"],
    }
