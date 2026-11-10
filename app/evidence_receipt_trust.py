"""Out-of-band allowlist for KMS receipt-signing trust and key rotation."""
from __future__ import annotations

import json
import re
from typing import Any

from app.evidence_receipt_signing import (
    ReceiptSignatureError, verify_receipt_signature,
)

_KEY_ARN = re.compile(
    r"^arn:aws:kms:([a-z0-9-]+):(\d{12}):key/([A-Za-z0-9-]+)$"
)


class ReceiptTrustError(ValueError):
    pass


def validate_key_arn(key_arn: Any) -> tuple[str, str]:
    if not isinstance(key_arn, str):
        raise ReceiptTrustError("trusted_kms_key_arn_invalid")
    match = _KEY_ARN.fullmatch(key_arn)
    if not match:
        raise ReceiptTrustError("trusted_kms_key_arn_invalid")
    return match.group(1), match.group(2)


def parse_trusted_key_regions(*, registry_json: str | None,
                              legacy_key_arn: str | None = None,
                              legacy_region: str | None = None) -> dict[str, str]:
    """Parse explicit ARN->region trust configuration; never trusts receipt input."""
    if registry_json:
        try:
            parsed = json.loads(registry_json)
        except (TypeError, ValueError):
            raise ReceiptTrustError("trusted_kms_key_registry_json_invalid") from None
        if not isinstance(parsed, dict) or not parsed:
            raise ReceiptTrustError("trusted_kms_key_registry_empty")
        registry: dict[str, str] = {}
        for key_arn, region in parsed.items():
            arn_region, _ = validate_key_arn(key_arn)
            if not isinstance(region, str) or region != arn_region:
                raise ReceiptTrustError("trusted_kms_key_region_mismatch")
            registry[key_arn] = region
        return registry
    if not legacy_key_arn or not legacy_region:
        raise ReceiptTrustError("trusted_kms_key_configuration_missing")
    arn_region, _ = validate_key_arn(legacy_key_arn)
    if legacy_region != arn_region:
        raise ReceiptTrustError("trusted_kms_key_region_mismatch")
    return {legacy_key_arn: legacy_region}


def validate_current_signing_key(*, signing_key_arn: str,
                                 signing_region: str,
                                 trusted_key_regions: dict[str, str]) -> None:
    arn_region, _ = validate_key_arn(signing_key_arn)
    if signing_key_arn not in trusted_key_regions:
        raise ReceiptTrustError("current_signing_key_not_in_trust_registry")
    if trusted_key_regions[signing_key_arn] != arn_region or signing_region != arn_region:
        raise ReceiptTrustError("current_signing_key_region_mismatch")


def verify_receipt_with_trusted_clients(*, receipt: dict,
                                        trusted_kms_clients: dict[str, Any]) -> str:
    """Select a KMS client only from configured trusted keys, never receipt ARNs."""
    if not isinstance(receipt, dict):
        raise ReceiptTrustError("receipt_shape_invalid")
    envelope = receipt.get("signature")
    key_arn = envelope.get("key_arn") if isinstance(envelope, dict) else None
    if not isinstance(key_arn, str) or key_arn not in trusted_kms_clients:
        raise ReceiptTrustError("receipt_signing_key_not_trusted")
    try:
        verify_receipt_signature(
            kms_client=trusted_kms_clients[key_arn],
            trusted_key_arn=key_arn,
            receipt=receipt,
        )
    except ReceiptSignatureError:
        raise ReceiptTrustError("receipt_signature_verification_failed") from None
    return key_arn
