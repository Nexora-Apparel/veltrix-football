"""Verified loader and point-in-time selector for the internal OpenPlay feature bundle.

The bundle contains derived, non-commercial features only. Raw provider assets remain
in staging and are never redistributed through this format.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


OPENPLAY_APPROVAL_ID = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=str, allow_nan=False,
    ).encode("utf-8")


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _aware_utc(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        raise ValueError(f"OPENPLAY_BUNDLE_{field}_MISSING")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"OPENPLAY_BUNDLE_{field}_NOT_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip()[:10])
    raise ValueError("OPENPLAY_BUNDLE_MATCH_DATE_INVALID")


def iter_openplay_feature_bundle(
    manifest_path: str | Path,
) -> Iterator[dict[str, Any]]:
    """Verify the complete JSONL digest and every row hash before yielding rows."""
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS_STAGING_FEATURE_BUNDLE":
        raise ValueError("OPENPLAY_BUNDLE_NOT_VALIDATED")
    if manifest.get("commercial_use_allowed") is not False or manifest.get("monetisation_prohibited") is not True:
        raise ValueError("OPENPLAY_BUNDLE_RIGHTS_POLICY_MISMATCH")
    if manifest.get("rights_approval_id") != OPENPLAY_APPROVAL_ID:
        raise ValueError("OPENPLAY_BUNDLE_APPROVAL_ID_MISMATCH")
    if (manifest.get("raw_redistribution_allowed") is not False
        or manifest.get("database_writes") != 0
        or manifest.get("timestamp_evidence_sha256") != "24a1037a948afa1759e3bc2babeb8b17b9e1e2dc3c8a8beea2e18f9b5b671279"):
        raise ValueError("OPENPLAY_BUNDLE_MANIFEST_PROVENANCE_MISMATCH")
    rows_name = manifest.get("feature_rows_file")
    if not isinstance(rows_name, str) or not rows_name or Path(rows_name).name != rows_name:
        raise ValueError("OPENPLAY_BUNDLE_ROWS_FILE_INVALID")
    rows_path = manifest_file.parent / rows_name
    digest = hashlib.sha256()
    with rows_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest.get("feature_rows_sha256"):
        raise ValueError("OPENPLAY_BUNDLE_ROWS_DIGEST_MISMATCH")

    count = 0
    with rows_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            expected = row.get("feature_sha256")
            payload = {key: value for key, value in row.items() if key != "feature_sha256"}
            if not isinstance(expected, str) or sha256_hex(canonical_json_bytes(payload)) != expected:
                raise ValueError("OPENPLAY_BUNDLE_FEATURE_HASH_MISMATCH")
            if row.get("rights_approval_id") != OPENPLAY_APPROVAL_ID:
                raise ValueError("OPENPLAY_BUNDLE_ROW_APPROVAL_MISMATCH")
            if row.get("commercial_use_allowed") is not False:
                raise ValueError("OPENPLAY_BUNDLE_ROW_COMMERCIAL_FLAG_MISMATCH")
            if row.get("point_in_time_certifiable") is not True:
                raise ValueError("OPENPLAY_BUNDLE_ROW_NOT_PIT_CERTIFIABLE")
            if row.get("source_timestamp_basis") != "documented_guarantee":
                raise ValueError("OPENPLAY_BUNDLE_ROW_TIMESTAMP_BASIS_INVALID")
            if row.get("monetisation_prohibited") is not True:
                raise ValueError("OPENPLAY_BUNDLE_ROW_MONETISATION_POLICY_MISMATCH")
            assets = row.get("asset_provenance") or {}
            required_assets = {
                "matches.parquet", "team_match_stats.parquet", "player_match_stats.parquet",
                "lineups.parquet", "shots.parquet", "cards.parquet", "formations.parquet",
                "teams.parquet", "competitions.parquet",
            }
            if not required_assets.issubset(assets):
                raise ValueError("OPENPLAY_BUNDLE_ROW_ASSET_PROVENANCE_INCOMPLETE")
            if assets["matches.parquet"].get("provider_response_id") != row.get("provider_response_id"):
                raise ValueError("OPENPLAY_BUNDLE_ROW_MATCH_RESPONSE_MISMATCH")
            crosswalks = row.get("crosswalk_provenance") or {}
            if (set(crosswalks) != {"team", "opponent", "competition"}
                or crosswalks["team"].get("provider_entity_id") != row.get("provider_team_id")
                or crosswalks["team"].get("canonical_entity_id") != row.get("canonical_team_id")
                or crosswalks["opponent"].get("provider_entity_id") != row.get("provider_opponent_id")
                or crosswalks["opponent"].get("canonical_entity_id") != row.get("canonical_opponent_id")
                or crosswalks["competition"].get("provider_entity_id") != row.get("competition_code")
                or crosswalks["competition"].get("canonical_entity_id") != row.get("canonical_competition_id")
                or crosswalks["team"].get("evidence_observation_id") != assets["teams.parquet"].get("source_observation_id")
                or crosswalks["opponent"].get("evidence_observation_id") != assets["teams.parquet"].get("source_observation_id")
                or crosswalks["competition"].get("evidence_observation_id") != assets["competitions.parquet"].get("source_observation_id")):
                raise ValueError("OPENPLAY_BUNDLE_ROW_CROSSWALK_PROVENANCE_MISMATCH")
            approval = row.get("approval_provenance") or {}
            if (approval.get("status") != "APPROVED"
                or approval.get("evidence_sha256") != "5e6bd00416f180109751e422521d76910da8b491c62507c4d9836e6700c38c46"):
                raise ValueError("OPENPLAY_BUNDLE_ROW_APPROVAL_PROVENANCE_MISMATCH")
            count += 1
            yield row
    if count != manifest.get("feature_count"):
        raise ValueError("OPENPLAY_BUNDLE_FEATURE_COUNT_MISMATCH")


def eligible_openplay_features_as_of(
    features: Iterable[Mapping[str, Any]],
    *,
    cutoff_at: datetime,
    canonical_team_id: str | None = None,
    canonical_competition_id: str | None = None,
    before_match_date: date | str | None = None,
) -> tuple[Mapping[str, Any], ...]:
    """Return only features observable before the cutoff and strictly before target day.

    The date guard is intentionally conservative: OpenPlay has match dates but
    not a canonical kickoff timestamp for every historical match. Same-day
    features are excluded to prevent ambiguous ordering against a target fixture.
    """
    cutoff = _aware_utc(cutoff_at, "CUTOFF_AT")
    target_date = _date(before_match_date) if before_match_date is not None else None
    selected = []
    for row in features:
        if canonical_team_id is not None and str(row.get("canonical_team_id")) != str(canonical_team_id):
            continue
        if canonical_competition_id is not None and str(row.get("canonical_competition_id")) != str(canonical_competition_id):
            continue
        if target_date is not None and _date(row.get("match_date")) >= target_date:
            continue
        if (row.get("point_in_time_certifiable") is not True
            or row.get("commercial_use_allowed") is not False
            or row.get("rights_approval_id") != OPENPLAY_APPROVAL_ID
            or row.get("source_timestamp_basis") != "documented_guarantee"
            or not row.get("source_observation_id")
            or not row.get("provider_response_id")):
            continue
        if cutoff <= _aware_utc(row.get("eligibility_at"), "ELIGIBILITY_AT"):
            continue
        assets = row.get("asset_provenance") or {}
        required_assets = {
            "matches.parquet", "team_match_stats.parquet", "player_match_stats.parquet",
            "lineups.parquet", "shots.parquet", "cards.parquet", "formations.parquet",
            "teams.parquet", "competitions.parquet",
        }
        if not required_assets.issubset(assets):
            continue
        if assets["matches.parquet"].get("provider_response_id") != row.get("provider_response_id"):
            continue
        crosswalks = row.get("crosswalk_provenance") or {}
        if (set(crosswalks) != {"team", "opponent", "competition"}
            or crosswalks["team"].get("provider_entity_id") != row.get("provider_team_id")
            or crosswalks["team"].get("canonical_entity_id") != row.get("canonical_team_id")
            or crosswalks["opponent"].get("provider_entity_id") != row.get("provider_opponent_id")
            or crosswalks["opponent"].get("canonical_entity_id") != row.get("canonical_opponent_id")
            or crosswalks["competition"].get("provider_entity_id") != row.get("competition_code")
            or crosswalks["competition"].get("canonical_entity_id") != row.get("canonical_competition_id")
            or crosswalks["team"].get("evidence_observation_id") != assets["teams.parquet"].get("source_observation_id")
            or crosswalks["opponent"].get("evidence_observation_id") != assets["teams.parquet"].get("source_observation_id")
            or crosswalks["competition"].get("evidence_observation_id") != assets["competitions.parquet"].get("source_observation_id")):
            continue
        # Recheck component clocks rather than trusting a single derived field.
        for field in ("source_published_at", "available_at", "recorded_at"):
            if cutoff <= _aware_utc(row.get(field), field.upper()):
                break
        else:
            crosswalks = row.get("crosswalk_provenance") or {}
            approval = row.get("approval_provenance") or {}
            mapping_valid = set(crosswalks) == {"team", "opponent", "competition"}
            for mapping in crosswalks.values():
                if (mapping.get("mapping_status") != "RESOLVED"
                    or not mapping.get("evidence_observation_id")
                    or not mapping.get("crosswalk_version_id")):
                    mapping_valid = False
                    break
                for field in ("valid_from", "recorded_at"):
                    if cutoff <= _aware_utc(mapping.get(field), "CROSSWALK_" + field.upper()):
                        mapping_valid = False
                        break
                valid_until = mapping.get("valid_until")
                if valid_until is not None and cutoff >= _aware_utc(valid_until, "CROSSWALK_VALID_UNTIL"):
                    mapping_valid = False
            for field in ("effective_at", "recorded_at", "approval_recorded_at"):
                if cutoff <= _aware_utc(approval.get(field), "APPROVAL_" + field.upper()):
                    mapping_valid = False
            approval_valid_until = approval.get("valid_until")
            if approval_valid_until is not None and cutoff >= _aware_utc(approval_valid_until, "APPROVAL_VALID_UNTIL"):
                mapping_valid = False
            if mapping_valid:
                selected.append(row)
    return tuple(sorted(
        selected,
        key=lambda row: (
            _date(row.get("match_date")),
            str(row.get("provider_match_id", "")),
            str(row.get("canonical_team_id", "")),
        ),
    ))
