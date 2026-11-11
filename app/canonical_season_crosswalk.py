"""KMS-signed, reviewed provider-season to canonical-season crosswalk.

A source season label is never promoted to canonical identity by inference.
Every mapping is scoped by provider and competition and binds review evidence.
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

SCHEMA = "veltrix-canonical-season-crosswalk-registry-v1"
ALGORITHM = "ECDSA_SHA_256"
MESSAGE_TYPE = "DIGEST"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_FIELDS = {"schema", "issued_at", "expires_at", "mappings"}
_MAPPING_FIELDS = {
    "provider", "competition_id", "source_season", "canonical_season_id",
    "evidence_sha256", "reviewer", "reviewed_at", "valid_from", "valid_until",
    "revoked_at",
}
_SIGNATURE_FIELDS = {"algorithm", "message_type", "key_arn", "region", "value_base64"}


class SeasonCrosswalkError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise SeasonCrosswalkError("season_registry_not_canonical_json") from None


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SeasonCrosswalkError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SeasonCrosswalkError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SeasonCrosswalkError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _key_region(key_arn: Any) -> str:
    try:
        region, _ = validate_key_arn(key_arn)
        return region
    except ReceiptTrustError:
        raise SeasonCrosswalkError("season_registry_signing_key_invalid") from None


def _unsigned(registry: Any) -> dict:
    if not isinstance(registry, dict):
        raise SeasonCrosswalkError("season_registry_shape_invalid")
    if set(registry) not in (_REGISTRY_FIELDS, _REGISTRY_FIELDS | {"signature"}):
        raise SeasonCrosswalkError("season_registry_shape_invalid")
    return {key: value for key, value in registry.items() if key != "signature"}


def _validate_mapping(mapping: Any) -> dict:
    if not isinstance(mapping, dict) or set(mapping) != _MAPPING_FIELDS:
        raise SeasonCrosswalkError("season_mapping_shape_invalid")
    for field in ("provider", "competition_id", "source_season",
                  "canonical_season_id", "reviewer"):
        value = mapping.get(field)
        if not isinstance(value, str) or not value.strip():
            raise SeasonCrosswalkError(f"season_mapping_{field}_invalid")
    digests = mapping.get("evidence_sha256")
    if (not isinstance(digests, list) or not digests
            or any(not isinstance(value, str) or not _HEX.fullmatch(value) for value in digests)
            or len(set(digests)) != len(digests)):
        raise SeasonCrosswalkError("season_mapping_evidence_invalid")
    reviewed = _time(mapping.get("reviewed_at"), "season_mapping_reviewed_at")
    valid_from = _time(mapping.get("valid_from"), "season_mapping_valid_from")
    valid_until = _time(mapping.get("valid_until"), "season_mapping_valid_until")
    if valid_until <= valid_from or reviewed > valid_from:
        raise SeasonCrosswalkError("season_mapping_validity_invalid")
    revoked_value = mapping.get("revoked_at")
    revoked = _time(revoked_value, "season_mapping_revoked_at") if revoked_value is not None else None
    if revoked is not None and revoked <= valid_from:
        raise SeasonCrosswalkError("season_mapping_revocation_invalid")
    return {
        "provider": mapping["provider"],
        "competition_id": mapping["competition_id"],
        "source_season": mapping["source_season"],
        "canonical_season_id": mapping["canonical_season_id"],
        "evidence_sha256": list(digests),
        "reviewer": mapping["reviewer"],
        "reviewed_at": reviewed.isoformat().replace("+00:00", "Z"),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "revoked_at": revoked,
    }


def sign_season_crosswalk_registry(*, kms_client: Any, key_arn: str,
                                   trusted_key_regions: dict[str, str],
                                   registry: dict) -> dict:
    region = _key_region(key_arn)
    try:
        validate_current_signing_key(
            signing_key_arn=key_arn, signing_region=region,
            trusted_key_regions=trusted_key_regions,
        )
    except ReceiptTrustError as exc:
        raise SeasonCrosswalkError(str(exc)) from None
    if isinstance(registry, dict) and "signature" in registry:
        raise SeasonCrosswalkError("season_registry_already_signed")
    unsigned = _unsigned(registry)
    if unsigned.get("schema") != SCHEMA:
        raise SeasonCrosswalkError("season_registry_schema_unsupported")
    issued = _time(unsigned.get("issued_at"), "season_registry_issued_at")
    expires = _time(unsigned.get("expires_at"), "season_registry_expires_at")
    if expires <= issued:
        raise SeasonCrosswalkError("season_registry_validity_invalid")
    mappings = unsigned.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise SeasonCrosswalkError("season_registry_mappings_required")
    seen = set()
    for mapping in mappings:
        checked = _validate_mapping(mapping)
        identity = (checked["provider"], checked["competition_id"], checked["source_season"])
        if identity in seen:
            raise SeasonCrosswalkError("season_registry_duplicate_source_mapping")
        seen.add(identity)
    digest = hashlib.sha256(canonical_json_bytes(unsigned)).digest()
    try:
        response = kms_client.sign(
            KeyId=key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            SigningAlgorithm=ALGORITHM,
        )
        signature = response["Signature"]
    except Exception:
        raise SeasonCrosswalkError("season_registry_kms_sign_failed") from None
    if not isinstance(signature, (bytes, bytearray)) or not signature:
        raise SeasonCrosswalkError("season_registry_signature_missing")
    signed = dict(unsigned)
    signed["signature"] = {
        "algorithm": ALGORITHM, "message_type": MESSAGE_TYPE,
        "key_arn": key_arn, "region": region,
        "value_base64": base64.b64encode(bytes(signature)).decode("ascii"),
    }
    return signed


def verify_season_crosswalk_registry(*, registry: Any,
                                     trusted_kms_clients: dict[str, Any],
                                     as_of: str) -> dict:
    unsigned = _unsigned(registry)
    if unsigned.get("schema") != SCHEMA:
        raise SeasonCrosswalkError("season_registry_schema_unsupported")
    envelope = registry.get("signature") if isinstance(registry, dict) else None
    if not isinstance(envelope, dict) or set(envelope) != _SIGNATURE_FIELDS:
        raise SeasonCrosswalkError("season_registry_signature_shape_invalid")
    key_arn = envelope.get("key_arn")
    if not isinstance(trusted_kms_clients, dict) or key_arn not in trusted_kms_clients:
        raise SeasonCrosswalkError("season_registry_signing_key_not_trusted")
    region = _key_region(key_arn)
    if (envelope.get("algorithm") != ALGORITHM
            or envelope.get("message_type") != MESSAGE_TYPE
            or envelope.get("region") != region):
        raise SeasonCrosswalkError("season_registry_signature_identity_invalid")
    try:
        signature = base64.b64decode(envelope.get("value_base64", ""), validate=True)
    except (ValueError, TypeError):
        raise SeasonCrosswalkError("season_registry_signature_encoding_invalid") from None
    if not signature:
        raise SeasonCrosswalkError("season_registry_signature_empty")
    digest = hashlib.sha256(canonical_json_bytes(unsigned)).digest()
    try:
        response = trusted_kms_clients[key_arn].verify(
            KeyId=key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            Signature=signature, SigningAlgorithm=ALGORITHM,
        )
    except Exception:
        raise SeasonCrosswalkError("season_registry_kms_verify_failed") from None
    if not isinstance(response, dict) or response.get("SignatureValid") is not True:
        raise SeasonCrosswalkError("season_registry_signature_invalid")

    now = _time(as_of, "season_registry_as_of")
    issued = _time(unsigned.get("issued_at"), "season_registry_issued_at")
    expires = _time(unsigned.get("expires_at"), "season_registry_expires_at")
    if expires <= issued or now < issued or now >= expires:
        raise SeasonCrosswalkError("season_registry_outside_validity_window")
    mappings = unsigned.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise SeasonCrosswalkError("season_registry_mappings_required")
    resolved = {}
    for mapping in mappings:
        checked = _validate_mapping(mapping)
        identity = (checked["provider"], checked["competition_id"], checked["source_season"])
        if identity in resolved:
            raise SeasonCrosswalkError("season_registry_duplicate_source_mapping")
        revoked = checked["revoked_at"]
        if (now < checked["valid_from"] or now >= checked["valid_until"]
                or (revoked is not None and now >= revoked)):
            continue
        resolved[identity] = {
            "canonical_season_id": checked["canonical_season_id"],
            "evidence_sha256": checked["evidence_sha256"],
            "reviewer": checked["reviewer"],
            "reviewed_at": checked["reviewed_at"],
        }
    return {
        "valid": True,
        "registry_sha256": canonical_sha256(unsigned),
        "signing_key_arn": key_arn,
        "verified_at": now.isoformat().replace("+00:00", "Z"),
        "mappings": resolved,
    }


def resolve_canonical_season(*, registry: Any, trusted_kms_clients: dict[str, Any],
                             provider: str, competition_id: str,
                             source_season: str, as_of: str) -> dict:
    verified = verify_season_crosswalk_registry(
        registry=registry, trusted_kms_clients=trusted_kms_clients, as_of=as_of,
    )
    identity = (provider, competition_id, source_season)
    mapping = verified["mappings"].get(identity)
    if mapping is None:
        raise SeasonCrosswalkError("canonical_season_mapping_missing_or_inactive")
    return {
        **mapping,
        "registry_sha256": verified["registry_sha256"],
        "signing_key_arn": verified["signing_key_arn"],
    }
