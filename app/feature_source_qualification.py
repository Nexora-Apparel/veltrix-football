"""KMS-signed, time-bounded qualification for pre-match feature sources.

The registry qualifies a source's permitted feature domains and timestamp
semantics. It does not establish predictive quality or historical availability
without separately reviewed evidence.
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

SCHEMA = "veltrix-feature-source-qualification-registry-v1"
ALGORITHM = "ECDSA_SHA_256"
MESSAGE_TYPE = "DIGEST"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_FIELDS = {"schema", "issued_at", "expires_at", "sources"}
_SOURCE_FIELDS = {
    "source", "qualified_features", "supported_competitions",
    "observed_at_semantics", "available_at_semantics",
    "qualification_evidence_sha256", "reviewer", "qualified_at",
    "valid_from", "valid_until", "revoked_at",
}
_SIGNATURE_FIELDS = {"algorithm", "message_type", "key_arn", "region", "value_base64"}


class FeatureSourceQualificationError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise FeatureSourceQualificationError("registry_not_canonical_json") from None


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise FeatureSourceQualificationError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise FeatureSourceQualificationError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FeatureSourceQualificationError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _region(key_arn: Any) -> str:
    try:
        region, _ = validate_key_arn(key_arn)
        return region
    except ReceiptTrustError:
        raise FeatureSourceQualificationError("registry_signing_key_arn_invalid") from None


def _unsigned(registry: Any) -> dict:
    if not isinstance(registry, dict) or set(registry) not in (
        _REGISTRY_FIELDS, _REGISTRY_FIELDS | {"signature"},
    ):
        raise FeatureSourceQualificationError("registry_shape_invalid")
    return {key: value for key, value in registry.items() if key != "signature"}


def _validate_sources(sources: Any) -> list[dict]:
    if not isinstance(sources, list) or not sources:
        raise FeatureSourceQualificationError("registry_sources_required")
    checked, seen = [], set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or set(source) != _SOURCE_FIELDS:
            raise FeatureSourceQualificationError(f"source_shape_invalid:{index}")
        name = source.get("source")
        reviewer = source.get("reviewer")
        if not isinstance(name, str) or not name.strip() or name in seen:
            raise FeatureSourceQualificationError(f"source_identity_invalid:{index}")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise FeatureSourceQualificationError(f"source_reviewer_invalid:{name}")
        seen.add(name)
        features = source.get("qualified_features")
        competitions = source.get("supported_competitions")
        digests = source.get("qualification_evidence_sha256")
        if (not isinstance(features, list) or not features
                or any(not isinstance(x, str) or not x.strip() for x in features)
                or len(set(features)) != len(features)):
            raise FeatureSourceQualificationError(f"source_features_invalid:{name}")
        if (not isinstance(competitions, list) or not competitions
                or any(not isinstance(x, str) or not x.strip() for x in competitions)
                or len(set(competitions)) != len(competitions)):
            raise FeatureSourceQualificationError(f"source_competitions_invalid:{name}")
        if (not isinstance(digests, list) or not digests
                or any(not isinstance(x, str) or not _HEX.fullmatch(x) for x in digests)
                or len(set(digests)) != len(digests)):
            raise FeatureSourceQualificationError(f"source_evidence_invalid:{name}")
        for field in ("observed_at_semantics", "available_at_semantics"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                raise FeatureSourceQualificationError(f"source_timestamp_semantics_invalid:{name}:{field}")
        qualified = _time(source.get("qualified_at"), f"{name}_qualified_at")
        reviewed = _time(source.get("valid_from"), f"{name}_valid_from")
        expires = _time(source.get("valid_until"), f"{name}_valid_until")
        if reviewed < qualified or expires <= reviewed:
            raise FeatureSourceQualificationError(f"source_validity_invalid:{name}")
        revoked_value = source.get("revoked_at")
        revoked = _time(revoked_value, f"{name}_revoked_at") if revoked_value is not None else None
        if revoked is not None and revoked <= reviewed:
            raise FeatureSourceQualificationError(f"source_revocation_invalid:{name}")
        checked.append(source)
    return checked


def sign_feature_source_qualification_registry(
    *, kms_client: Any, key_arn: str, trusted_key_regions: dict[str, str],
    registry: dict,
) -> dict:
    region = _region(key_arn)
    try:
        validate_current_signing_key(
            signing_key_arn=key_arn, signing_region=region,
            trusted_key_regions=trusted_key_regions,
        )
    except ReceiptTrustError as exc:
        raise FeatureSourceQualificationError(str(exc)) from None
    if isinstance(registry, dict) and "signature" in registry:
        raise FeatureSourceQualificationError("registry_already_signed")
    unsigned = _unsigned(registry)
    if unsigned.get("schema") != SCHEMA:
        raise FeatureSourceQualificationError("registry_schema_unsupported")
    issued, expires = _time(unsigned.get("issued_at"), "registry_issued_at"), _time(
        unsigned.get("expires_at"), "registry_expires_at"
    )
    if expires <= issued:
        raise FeatureSourceQualificationError("registry_validity_invalid")
    _validate_sources(unsigned.get("sources"))
    digest = hashlib.sha256(canonical_json_bytes(unsigned)).digest()
    try:
        response = kms_client.sign(
            KeyId=key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            SigningAlgorithm=ALGORITHM,
        )
        signature = response["Signature"]
    except Exception:
        raise FeatureSourceQualificationError("registry_kms_sign_failed") from None
    if not isinstance(signature, (bytes, bytearray)) or not signature:
        raise FeatureSourceQualificationError("registry_signature_missing")
    signed = dict(unsigned)
    signed["signature"] = {
        "algorithm": ALGORITHM, "message_type": MESSAGE_TYPE,
        "key_arn": key_arn, "region": region,
        "value_base64": base64.b64encode(bytes(signature)).decode("ascii"),
    }
    return signed


def verify_feature_source_qualification_registry(
    *, registry: Any, trusted_kms_clients: dict[str, Any], as_of: str,
) -> dict:
    unsigned = _unsigned(registry)
    if unsigned.get("schema") != SCHEMA:
        raise FeatureSourceQualificationError("registry_schema_unsupported")
    envelope = registry.get("signature")
    if not isinstance(envelope, dict) or set(envelope) != _SIGNATURE_FIELDS:
        raise FeatureSourceQualificationError("registry_signature_shape_invalid")
    key_arn = envelope.get("key_arn")
    if not isinstance(trusted_kms_clients, dict) or key_arn not in trusted_kms_clients:
        raise FeatureSourceQualificationError("registry_signing_key_not_trusted")
    region = _region(key_arn)
    if (envelope.get("algorithm") != ALGORITHM or envelope.get("message_type") != MESSAGE_TYPE
            or envelope.get("region") != region):
        raise FeatureSourceQualificationError("registry_signature_identity_invalid")
    try:
        signature = base64.b64decode(envelope.get("value_base64", ""), validate=True)
    except (ValueError, TypeError):
        raise FeatureSourceQualificationError("registry_signature_encoding_invalid") from None
    if not signature:
        raise FeatureSourceQualificationError("registry_signature_empty")
    digest = hashlib.sha256(canonical_json_bytes(unsigned)).digest()
    try:
        response = trusted_kms_clients[key_arn].verify(
            KeyId=key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            Signature=signature, SigningAlgorithm=ALGORITHM,
        )
    except Exception:
        raise FeatureSourceQualificationError("registry_kms_verify_failed") from None
    if not isinstance(response, dict) or response.get("SignatureValid") is not True:
        raise FeatureSourceQualificationError("registry_signature_invalid")
    now = _time(as_of, "registry_as_of")
    issued, expires = _time(unsigned.get("issued_at"), "registry_issued_at"), _time(
        unsigned.get("expires_at"), "registry_expires_at"
    )
    if now < issued or now >= expires:
        raise FeatureSourceQualificationError("registry_outside_validity_window")
    resolved = {}
    for source in _validate_sources(unsigned.get("sources")):
        start = _time(source["valid_from"], f"{source['source']}_valid_from")
        end = _time(source["valid_until"], f"{source['source']}_valid_until")
        revoked = _time(source["revoked_at"], f"{source['source']}_revoked_at") if source["revoked_at"] else None
        if now < start or now >= end or (revoked is not None and now >= revoked):
            continue
        resolved[source["source"]] = {
            "qualified_features": list(source["qualified_features"]),
            "supported_competitions": list(source["supported_competitions"]),
            "observed_at_semantics": source["observed_at_semantics"],
            "available_at_semantics": source["available_at_semantics"],
            "qualification_evidence_sha256": list(source["qualification_evidence_sha256"]),
        }
    return {
        "valid": True, "registry_sha256": canonical_sha256(unsigned),
        "signing_key_arn": key_arn,
        "verified_at": now.isoformat().replace("+00:00", "Z"),
        "sources": resolved,
    }


def validate_feature_source(*, verified_registry: dict, source: str,
                             feature_name: str, competition_id: str) -> dict:
    if not isinstance(verified_registry, dict) or verified_registry.get("valid") is not True:
        raise FeatureSourceQualificationError("verified_registry_required")
    contract = verified_registry.get("sources", {}).get(source)
    if contract is None:
        raise FeatureSourceQualificationError(f"feature_source_not_qualified:{source}")
    if feature_name not in contract["qualified_features"]:
        raise FeatureSourceQualificationError(f"feature_not_qualified_for_source:{feature_name}:{source}")
    if competition_id not in contract["supported_competitions"]:
        raise FeatureSourceQualificationError(f"feature_source_competition_unsupported:{source}:{competition_id}")
    return {
        "registry_sha256": verified_registry["registry_sha256"],
        "signing_key_arn": verified_registry["signing_key_arn"],
        "verified_at": verified_registry["verified_at"],
        "observed_at_semantics": contract["observed_at_semantics"],
        "available_at_semantics": contract["available_at_semantics"],
        "qualification_evidence_sha256": contract["qualification_evidence_sha256"],
    }
