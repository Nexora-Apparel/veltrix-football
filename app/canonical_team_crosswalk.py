"""KMS-signed provider-team ID to canonical-team identity crosswalk.

Mappings are scoped by provider and competition. Team scope is explicit so
men's, women's, reserve and youth identities cannot be silently conflated.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from app.evidence_receipt_trust import (
    ReceiptTrustError, validate_current_signing_key, validate_key_arn,
)

SCHEMA = "veltrix-canonical-team-crosswalk-registry-v1"
ALGORITHM = "ECDSA_SHA_256"
MESSAGE_TYPE = "DIGEST"
TEAM_SCOPES = {
    "men_first_team", "women_first_team", "men_reserve", "women_reserve",
    "youth_men", "youth_women", "other",
}
_HEX = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_FIELDS = {"schema", "issued_at", "expires_at", "mappings"}
_MAPPING_FIELDS = {
    "provider", "competition_id", "source_team_id", "canonical_team_id",
    "team_scope", "evidence_sha256", "reviewer", "reviewed_at",
    "valid_from", "valid_until", "revoked_at",
}
_SIGNATURE_FIELDS = {"algorithm", "message_type", "key_arn", "region", "value_base64"}


class TeamCrosswalkError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise TeamCrosswalkError("team_registry_not_canonical_json") from None


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TeamCrosswalkError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TeamCrosswalkError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TeamCrosswalkError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _region(key_arn: Any) -> str:
    try:
        region, _ = validate_key_arn(key_arn)
        return region
    except ReceiptTrustError:
        raise TeamCrosswalkError("team_registry_signing_key_invalid") from None


def _unsigned(registry: Any) -> dict:
    if not isinstance(registry, dict) or set(registry) not in (
        _REGISTRY_FIELDS, _REGISTRY_FIELDS | {"signature"},
    ):
        raise TeamCrosswalkError("team_registry_shape_invalid")
    return {key: value for key, value in registry.items() if key != "signature"}


def _validate_mapping(mapping: Any) -> dict:
    if not isinstance(mapping, dict) or set(mapping) != _MAPPING_FIELDS:
        raise TeamCrosswalkError("team_mapping_shape_invalid")
    for field in ("provider", "competition_id", "source_team_id",
                  "canonical_team_id", "reviewer"):
        value = mapping.get(field)
        if not isinstance(value, str) or not value.strip():
            raise TeamCrosswalkError(f"team_mapping_{field}_invalid")
    if mapping.get("team_scope") not in TEAM_SCOPES:
        raise TeamCrosswalkError("team_mapping_scope_invalid")
    digests = mapping.get("evidence_sha256")
    if (not isinstance(digests, list) or not digests
            or any(not isinstance(value, str) or not _HEX.fullmatch(value) for value in digests)
            or len(set(digests)) != len(digests)):
        raise TeamCrosswalkError("team_mapping_evidence_invalid")
    reviewed = _time(mapping.get("reviewed_at"), "team_mapping_reviewed_at")
    valid_from = _time(mapping.get("valid_from"), "team_mapping_valid_from")
    valid_until = _time(mapping.get("valid_until"), "team_mapping_valid_until")
    if valid_until <= valid_from or reviewed > valid_from:
        raise TeamCrosswalkError("team_mapping_validity_invalid")
    revoked_value = mapping.get("revoked_at")
    revoked = _time(revoked_value, "team_mapping_revoked_at") if revoked_value is not None else None
    if revoked is not None and revoked <= valid_from:
        raise TeamCrosswalkError("team_mapping_revocation_invalid")
    return {
        **{field: mapping[field] for field in (
            "provider", "competition_id", "source_team_id",
            "canonical_team_id", "team_scope", "evidence_sha256", "reviewer",
        )},
        "reviewed_at": reviewed.isoformat().replace("+00:00", "Z"),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "revoked_at": revoked,
    }


def _validate_mapping_set(mappings: Any) -> list[dict]:
    if not isinstance(mappings, list) or not mappings:
        raise TeamCrosswalkError("team_registry_mappings_required")
    checked = []
    seen_source = set()
    canonical_scopes = {}
    for mapping in mappings:
        item = _validate_mapping(mapping)
        source_key = (item["provider"], item["competition_id"], item["source_team_id"])
        if source_key in seen_source:
            raise TeamCrosswalkError("team_registry_duplicate_source_mapping")
        seen_source.add(source_key)
        prior_scope = canonical_scopes.get(item["canonical_team_id"])
        if prior_scope is not None and prior_scope != item["team_scope"]:
            raise TeamCrosswalkError("team_registry_canonical_scope_collision")
        canonical_scopes[item["canonical_team_id"]] = item["team_scope"]
        checked.append(item)
    return checked


def sign_team_crosswalk_registry(*, kms_client: Any, key_arn: str,
                                 trusted_key_regions: dict[str, str],
                                 registry: dict) -> dict:
    region = _region(key_arn)
    try:
        validate_current_signing_key(
            signing_key_arn=key_arn, signing_region=region,
            trusted_key_regions=trusted_key_regions,
        )
    except ReceiptTrustError as exc:
        raise TeamCrosswalkError(str(exc)) from None
    unsigned = _unsigned(registry)
    if unsigned.get("schema") != SCHEMA:
        raise TeamCrosswalkError("team_registry_schema_unsupported")
    issued = _time(unsigned.get("issued_at"), "team_registry_issued_at")
    expires = _time(unsigned.get("expires_at"), "team_registry_expires_at")
    if expires <= issued:
        raise TeamCrosswalkError("team_registry_validity_invalid")
    _validate_mapping_set(unsigned.get("mappings"))
    digest = hashlib.sha256(canonical_json_bytes(unsigned)).digest()
    try:
        response = kms_client.sign(
            KeyId=key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            SigningAlgorithm=ALGORITHM,
        )
        signature = response["Signature"]
    except Exception:
        raise TeamCrosswalkError("team_registry_kms_sign_failed") from None
    if not isinstance(signature, (bytes, bytearray)) or not signature:
        raise TeamCrosswalkError("team_registry_signature_missing")
    signed = dict(unsigned)
    signed["signature"] = {
        "algorithm": ALGORITHM, "message_type": MESSAGE_TYPE,
        "key_arn": key_arn, "region": region,
        "value_base64": base64.b64encode(bytes(signature)).decode("ascii"),
    }
    return signed


def verify_team_crosswalk_registry(*, registry: Any,
                                   trusted_kms_clients: dict[str, Any],
                                   as_of: str) -> dict:
    unsigned = _unsigned(registry)
    if unsigned.get("schema") != SCHEMA:
        raise TeamCrosswalkError("team_registry_schema_unsupported")
    envelope = registry.get("signature")
    if not isinstance(envelope, dict) or set(envelope) != _SIGNATURE_FIELDS:
        raise TeamCrosswalkError("team_registry_signature_shape_invalid")
    key_arn = envelope.get("key_arn")
    if not isinstance(trusted_kms_clients, dict) or key_arn not in trusted_kms_clients:
        raise TeamCrosswalkError("team_registry_signing_key_not_trusted")
    region = _region(key_arn)
    if (envelope.get("algorithm") != ALGORITHM
            or envelope.get("message_type") != MESSAGE_TYPE
            or envelope.get("region") != region):
        raise TeamCrosswalkError("team_registry_signature_identity_invalid")
    try:
        signature = base64.b64decode(envelope.get("value_base64", ""), validate=True)
    except (ValueError, TypeError):
        raise TeamCrosswalkError("team_registry_signature_encoding_invalid") from None
    if not signature:
        raise TeamCrosswalkError("team_registry_signature_empty")
    digest = hashlib.sha256(canonical_json_bytes(unsigned)).digest()
    try:
        response = trusted_kms_clients[key_arn].verify(
            KeyId=key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            Signature=signature, SigningAlgorithm=ALGORITHM,
        )
    except Exception:
        raise TeamCrosswalkError("team_registry_kms_verify_failed") from None
    if not isinstance(response, dict) or response.get("SignatureValid") is not True:
        raise TeamCrosswalkError("team_registry_signature_invalid")

    now = _time(as_of, "team_registry_as_of")
    issued = _time(unsigned.get("issued_at"), "team_registry_issued_at")
    expires = _time(unsigned.get("expires_at"), "team_registry_expires_at")
    if expires <= issued or now < issued or now >= expires:
        raise TeamCrosswalkError("team_registry_outside_validity_window")
    resolved = {}
    for item in _validate_mapping_set(unsigned.get("mappings")):
        if (now < item["valid_from"] or now >= item["valid_until"]
                or (item["revoked_at"] is not None and now >= item["revoked_at"])):
            continue
        identity = (item["provider"], item["competition_id"], item["source_team_id"])
        resolved[identity] = {
            "canonical_team_id": item["canonical_team_id"],
            "team_scope": item["team_scope"],
            "evidence_sha256": item["evidence_sha256"],
            "reviewer": item["reviewer"],
            "reviewed_at": item["reviewed_at"],
        }
    return {
        "valid": True,
        "registry_sha256": canonical_sha256(unsigned),
        "signing_key_arn": key_arn,
        "verified_at": now.isoformat().replace("+00:00", "Z"),
        "mappings": resolved,
    }


def resolve_canonical_team(*, registry: Any, trusted_kms_clients: dict[str, Any],
                           provider: str, competition_id: str,
                           source_team_id: str, as_of: str) -> dict:
    verified = verify_team_crosswalk_registry(
        registry=registry, trusted_kms_clients=trusted_kms_clients, as_of=as_of,
    )
    identity = (provider, competition_id, source_team_id)
    mapping = verified["mappings"].get(identity)
    if mapping is None:
        raise TeamCrosswalkError("canonical_team_mapping_missing_or_inactive")
    return {
        **mapping,
        "registry_sha256": verified["registry_sha256"],
        "signing_key_arn": verified["signing_key_arn"],
    }
