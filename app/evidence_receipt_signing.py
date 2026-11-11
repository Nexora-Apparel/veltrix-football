"""Independent AWS KMS signatures for private evidence archive receipts.

The KMS asymmetric signing key is a separate trust identity from the AES-GCM
raw-evidence encryption key. Receipt signatures cover canonical JSON with the
signature envelope omitted.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

SCHEMA_V2 = "veltrix-evidence-archive-receipt-v2"
SIGNING_ALGORITHM = "ECDSA_SHA_256"
MESSAGE_TYPE = "DIGEST"


class ReceiptSignatureError(ValueError):
    pass


def canonical_receipt_payload(receipt: dict) -> bytes:
    if not isinstance(receipt, dict):
        raise ReceiptSignatureError("receipt_payload_invalid")
    payload = {key: value for key, value in receipt.items() if key != "signature"}
    try:
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ReceiptSignatureError("receipt_payload_not_canonical_json") from None


def sign_receipt(*, kms_client: Any, key_arn: str, receipt: dict) -> dict:
    if not isinstance(key_arn, str) or not key_arn.startswith("arn:") or ":key/" not in key_arn:
        raise ReceiptSignatureError("receipt_signing_key_arn_invalid")
    payload = canonical_receipt_payload(receipt)
    digest = hashlib.sha256(payload).digest()
    try:
        response = kms_client.sign(
            KeyId=key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            SigningAlgorithm=SIGNING_ALGORITHM,
        )
        signature = response["Signature"]
    except Exception:
        raise ReceiptSignatureError("receipt_kms_sign_failed") from None
    if not isinstance(signature, (bytes, bytearray)) or not signature:
        raise ReceiptSignatureError("receipt_kms_signature_missing")
    signed = dict(receipt)
    signed["signature"] = {
        "algorithm": SIGNING_ALGORITHM,
        "message_type": MESSAGE_TYPE,
        "key_arn": key_arn,
        "value_base64": base64.b64encode(bytes(signature)).decode("ascii"),
    }
    return signed


def verify_receipt_signature(*, kms_client: Any, trusted_key_arn: str, receipt: dict) -> None:
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA_V2:
        raise ReceiptSignatureError("receipt_signature_schema_unsupported")
    envelope = receipt.get("signature")
    if not isinstance(envelope, dict):
        raise ReceiptSignatureError("receipt_signature_missing")
    if (envelope.get("algorithm") != SIGNING_ALGORITHM
            or envelope.get("message_type") != MESSAGE_TYPE
            or envelope.get("key_arn") != trusted_key_arn
            or not isinstance(trusted_key_arn, str)
            or not trusted_key_arn.startswith("arn:")
            or ":key/" not in trusted_key_arn):
        raise ReceiptSignatureError("receipt_signature_identity_invalid")
    try:
        signature = base64.b64decode(envelope.get("value_base64", ""), validate=True)
    except (ValueError, TypeError):
        raise ReceiptSignatureError("receipt_signature_encoding_invalid") from None
    if not signature:
        raise ReceiptSignatureError("receipt_signature_empty")
    digest = hashlib.sha256(canonical_receipt_payload(receipt)).digest()
    try:
        result = kms_client.verify(
            KeyId=trusted_key_arn, Message=digest, MessageType=MESSAGE_TYPE,
            Signature=signature, SigningAlgorithm=SIGNING_ALGORITHM,
        )
    except Exception:
        raise ReceiptSignatureError("receipt_kms_verify_failed") from None
    if result.get("SignatureValid") is not True:
        raise ReceiptSignatureError("receipt_signature_verification_failed")
