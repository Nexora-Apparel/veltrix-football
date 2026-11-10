"""Signed, time-bounded registry for qualified settlement timestamp sources.

Registry authenticity is anchored to an out-of-band KMS key allowlist. A
contract's qualification digest is recomputed from its qualification record;
callers cannot make an arbitrary contract trusted by setting status=qualified.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from app.evidence_receipt_trust import validate_key_arn

SCHEMA = "veltrix-settlement-source-qualification-registry-v1"
ALGORITHM = "ECDSA_SHA_256"
MESSAGE_TYPE = "DIGEST"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_FIELDS = {
    "source_id", "qualification_status", "timestamp_field",
    "timestamp_semantics", "supported_competitions",
    "qualification_evidence_sha256", "qualified_at",
}
_ENTRY_FIELDS = {
    "qualification_record", "qualification_record_sha256",
    "valid_from", "valid_until", "revoked_at",
}
_REGISTRY_FIELDS = {"schema", "issued_at", "expires_at", "sources"}
_SIGNATURE_FIELDS = {"algorithm", "message_type", "key_arn", "region", "value_base64"}


class SourceQualificationRegistryError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise SourceQualificationRegistryError("registry_not_canonical_json") from None


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SourceQualificationRegistryError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SourceQualificationRegistryError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceQualificationRegistryError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _record_contract(record: Any) -> dict:
    if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
        raise SourceQualificationRegistryError("qualification_record_shape_invalid")
    if not isinstance(record["source_id"], str) or not record["source_id"].strip():
        raise SourceQualificationRegistryError("qualification_source_id_invalid")
    if record["qualification_status"] != "qualified":
        raise SourceQualificationRegistryError("qualification_record_not_qualified")
    if not isinstance(record["timestamp_field"], str) or not record["timestamp_field"].strip():
        raise SourceQualificationRegistryError("qualification_timestamp_field_invalid")
    if record["timestamp_semantics"] != "final_whistle":
        raise SourceQualificationRegistryError("qualification_timestamp_semantics_unsupported")
    competitions = record["supported_competitions"]
    if (not isinstance(competitions, list) or not competitions
            or any(not isinstance(x, str) or not x.strip() for x in competitions)
            or len(set(competitions)) != len(competitions)):
        raise SourceQualificationRegistryError("qualification_competitions_invalid")
    digests = record["qualification_evidence_sha256"]
    if (not isinstance(digests, list) or not digests
            or any(not isinstance(x, str) or not _HEX.fullmatch(x) for x in digests)
            or len(set(digests)) != len(digests)):
        raise SourceQualificationRegistryError("qualification_evidence_digests_invalid")
    _time(record["qualified_at"], "qualified_at")
    digest = canonical_sha256(record)
    return {
        "source_id": record["source_id"],
        "qualification_status": "qualified",
        "qualification_digest": digest,
        "timestamp_field": record["timestamp_field"],
        "timestamp_semantics": record["timestamp_semantics"],
        "supported_competitions": list(record["supported_competitions"]),
    }


def _unsigned_registry(registry: dict) -> dict:
    if not isinstance(registry, dict):
        raise SourceQualificationRegistryError("registry_shape_invalid")
    fields = set(registry)
    if fields not in (_REGISTRY_FIELDS, _REGISTRY_FIELDS | {"signature"}):
        raise SourceQualificationRegistryError("registry_shape_invalid")
    return {k: v for k, v in registry.items() if k != "signature"}


def sign_source_qualification_registry(*, kms_client: Any, key_arn: str,
                                       registry: dict) -> dict:
    region, _ = validate_key_arn(key_arn)
    unsigned = _unsigned_registry(registry)
    if unsigned.get("schema") != SCHEMA:
        raise SourceQualificationRegistryError("registry_schema_unsupported")
    digest = hashlib.sha256(canonical_json_bytes(unsigned)).digest()
    try:
        response = kms_client.sign(
            KeyId=key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            SigningAlgorithm=ALGORITHM,
        )
        signature = response["Signature"]
    except Exception:
        raise SourceQualificationRegistryError("registry_kms_sign_failed") from None
    if not isinstance(signature, (bytes, bytearray)) or not signature:
        raise SourceQualificationRegistryError("registry_signature_missing")
    signed = dict(unsigned)
    signed["signature"] = {
        "algorithm": ALGORITHM,
        "message_type": MESSAGE_TYPE,
        "key_arn": key_arn,
        "region": region,
        "value_base64": base64.b64encode(bytes(signature)).decode("ascii"),
    }
    return signed


def verify_source_qualification_registry(*, registry: Any,
                                         trusted_kms_clients: dict[str, Any],
                                         as_of: str) -> dict:
    unsigned = _unsigned_registry(registry)
    if unsigned.get("schema") != SCHEMA:
        raise SourceQualificationRegistryError("registry_schema_unsupported")
    envelope = registry.get("signature") if isinstance(registry, dict) else None
    if not isinstance(envelope, dict):
        raise SourceQualificationRegistryError("registry_signature_missing")
    if set(envelope) != _SIGNATURE_FIELDS:
        raise SourceQualificationRegistryError("registry_signature_shape_invalid")
    key_arn = envelope.get("key_arn")
    if not isinstance(trusted_kms_clients, dict) or key_arn not in trusted_kms_clients:
        raise SourceQualificationRegistryError("registry_signing_key_not_trusted")
    region, _ = validate_key_arn(key_arn)
    if (envelope.get("algorithm") != ALGORITHM
            or envelope.get("message_type") != MESSAGE_TYPE
            or envelope.get("region") != region):
        raise SourceQualificationRegistryError("registry_signature_identity_invalid")
    try:
        signature = base64.b64decode(envelope.get("value_base64", ""), validate=True)
    except (ValueError, TypeError):
        raise SourceQualificationRegistryError("registry_signature_encoding_invalid") from None
    if not signature:
        raise SourceQualificationRegistryError("registry_signature_empty")
    digest = hashlib.sha256(canonical_json_bytes(unsigned)).digest()
    try:
        verified = trusted_kms_clients[key_arn].verify(
            KeyId=key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            Signature=signature, SigningAlgorithm=ALGORITHM,
        )
    except Exception:
        raise SourceQualificationRegistryError("registry_kms_verify_failed") from None
    if verified.get("SignatureValid") is not True:
        raise SourceQualificationRegistryError("registry_signature_invalid")

    now = _time(as_of, "as_of")
    issued = _time(unsigned.get("issued_at"), "registry_issued_at")
    expires = _time(unsigned.get("expires_at"), "registry_expires_at")
    if expires <= issued or now < issued or now >= expires:
        raise SourceQualificationRegistryError("registry_outside_validity_window")
    entries = unsigned.get("sources")
    if not isinstance(entries, list) or not entries:
        raise SourceQualificationRegistryError("registry_sources_required")
    contracts = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _ENTRY_FIELDS:
            raise SourceQualificationRegistryError("registry_entry_shape_invalid")
        record = entry["qualification_record"]
        contract = _record_contract(record)
        if entry["qualification_record_sha256"] != canonical_sha256(record):
            raise SourceQualificationRegistryError("qualification_record_digest_mismatch")
        if not isinstance(entry["valid_from"], str):
            raise SourceQualificationRegistryError("source_valid_from_invalid")
        valid_from = _time(entry["valid_from"], "source_valid_from")
        valid_until = _time(entry["valid_until"], "source_valid_until")
        if valid_until <= valid_from:
            raise SourceQualificationRegistryError("source_validity_window_invalid")
        qualified_at = _time(record["qualified_at"], "qualified_at")
        if qualified_at > valid_from:
            raise SourceQualificationRegistryError("source_active_before_qualification")
        if entry["revoked_at"] is not None:
            revoked = _time(entry["revoked_at"], "source_revoked_at")
            if revoked <= valid_from:
                raise SourceQualificationRegistryError("source_revocation_timestamp_invalid")
        else:
            revoked = None
        if now < valid_from or now >= valid_until or (revoked and now >= revoked):
            continue
        source_id = contract["source_id"]
        if source_id in contracts:
            raise SourceQualificationRegistryError("registry_duplicate_source_id")
        contracts[source_id] = contract
    return {
        "valid": True,
        "registry_sha256": canonical_sha256(unsigned),
        "signing_key_arn": key_arn,
        "verified_at": now.isoformat().replace("+00:00", "Z"),
        "contracts": contracts,
    }


def resolve_qualified_settlement_source(*, registry: Any, source_id: str,
                                        competition_id: str,
                                        trusted_kms_clients: dict[str, Any],
                                        as_of: str) -> dict:
    verified = verify_source_qualification_registry(
        registry=registry, trusted_kms_clients=trusted_kms_clients, as_of=as_of,
    )
    contract = verified["contracts"].get(source_id)
    if contract is None:
        raise SourceQualificationRegistryError("settlement_source_not_qualified_or_inactive")
    if competition_id not in contract["supported_competitions"]:
        raise SourceQualificationRegistryError("competition_not_qualified_for_timestamp_source")
    return {
        "contract": contract,
        "registry_sha256": verified["registry_sha256"],
        "signing_key_arn": verified["signing_key_arn"],
        "verified_at": verified["verified_at"],
    }
