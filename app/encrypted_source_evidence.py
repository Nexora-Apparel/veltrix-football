"""Authenticated encrypted sidecar for raw provider evidence.

Raw payloads never enter the sanitized acquisition report. The sidecar is an
AES-256-GCM envelope bound to the exact report digest, run and date window.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.source_payload_provenance import (
    canonical_payload_sha256,
    validate_source_payload_evidence,
)

_HEX = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA = "veltrix-encrypted-source-evidence-v1"


class EncryptedEvidenceError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise EncryptedEvidenceError("evidence_not_canonical_json") from None


def _key(value: str | bytes) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True) if isinstance(value, str) else value
    except (ValueError, TypeError):
        raise EncryptedEvidenceError("encryption_key_invalid_base64") from None
    if not isinstance(raw, bytes) or len(raw) != 32:
        raise EncryptedEvidenceError("encryption_key_must_be_32_bytes")
    return raw


def _binding(report: dict) -> dict:
    digest = report.get("report_sha256")
    run_ids = {r.get("run_id") for r in report.get("records", []) if isinstance(r, dict)}
    run_ids.update(q.get("source", {}).get("run_id") for q in report.get("quarantine", [])
                   if isinstance(q, dict) and isinstance(q.get("source"), dict))
    window = report.get("window")
    if not isinstance(digest, str) or not _HEX.fullmatch(digest):
        raise EncryptedEvidenceError("report_digest_invalid")
    if len(run_ids) != 1 or not isinstance(next(iter(run_ids)), str):
        raise EncryptedEvidenceError("report_run_binding_ambiguous")
    if not isinstance(window, dict):
        raise EncryptedEvidenceError("report_window_missing")
    return {"report_sha256": digest, "run_id": next(iter(run_ids)), "window": window}


def build_source_evidence(observations: list[dict], report: dict) -> list[dict]:
    """Pair original observations to normalized accepted rows without guessing."""
    records = report.get("records")
    if not isinstance(observations, list) or not isinstance(records, list):
        raise EncryptedEvidenceError("evidence_inputs_invalid")
    raw_by_key = {}
    for item in observations:
        if not isinstance(item, dict) or not isinstance(item.get("row"), dict):
            raise EncryptedEvidenceError("raw_observation_invalid")
        options = item.get("options") or {}
        row = item["row"]
        league = row.get("league") or {}
        key = (item.get("provider"), str(league.get("id", "")), str(row.get("id", "")))
        if key in raw_by_key:
            raise EncryptedEvidenceError("duplicate_raw_observation")
        raw_by_key[key] = (row, options)

    evidence = []
    for record in records:
        key = (record.get("provider"), str(record.get("competition_key", "")),
               str(record.get("source_id", "")))
        match = raw_by_key.pop(key, None)
        if match is None:
            raise EncryptedEvidenceError("accepted_record_raw_payload_missing")
        payload, options = match
        item = {
            "provider": record["provider"],
            "endpoint": record["endpoint"],
            "source_id": record["source_id"],
            "run_id": record["run_id"],
            "retrieved_at": record["retrieved_at"],
            "payload": payload,
            "payload_sha256": canonical_payload_sha256(payload),
            "normalized_record": record,
            "normalized_record_sha256": canonical_payload_sha256(record),
        }
        if options.get("run_id") != record["run_id"] or options.get("endpoint") != record["endpoint"]:
            raise EncryptedEvidenceError("raw_observation_metadata_mismatch")
        validate_source_payload_evidence(item)
        if item["payload_sha256"] != record["payload_sha256"]:
            raise EncryptedEvidenceError("normalizer_payload_hash_mismatch")
        evidence.append(item)
    if len(evidence) != len(records):
        raise EncryptedEvidenceError("evidence_coverage_mismatch")
    return evidence


def encrypt_source_evidence(evidence: list[dict], *, report: dict,
                            key: str | bytes, nonce: bytes | None = None) -> tuple[bytes, dict]:
    """Return encrypted JSON envelope bytes and a plaintext-safe manifest."""
    binding = _binding(report)
    if not isinstance(evidence, list) or len(evidence) != len(report.get("records", [])):
        raise EncryptedEvidenceError("evidence_count_mismatch")
    for item in evidence:
        validated = validate_source_payload_evidence(item)
        if validated["run_id"] != binding["run_id"]:
            raise EncryptedEvidenceError("evidence_run_binding_mismatch")
    aes_key = _key(key)
    import os
    nonce = nonce or os.urandom(12)
    if not isinstance(nonce, bytes) or len(nonce) != 12:
        raise EncryptedEvidenceError("gcm_nonce_must_be_12_bytes")
    plaintext = _canonical({"schema": _SCHEMA, "binding": binding, "evidence": evidence})
    aad = _canonical({"schema": _SCHEMA, "binding": binding})
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, aad)
    envelope = {
        "schema": _SCHEMA,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    encoded = _canonical(envelope)
    manifest = {
        "schema": _SCHEMA,
        "report_sha256": binding["report_sha256"],
        "run_id": binding["run_id"],
        "window": binding["window"],
        "evidence_count": len(evidence),
        "ciphertext_sha256": hashlib.sha256(encoded).hexdigest(),
        "encryption": "AES-256-GCM",
        "plaintext_in_report": False,
    }
    return encoded, manifest


def decrypt_and_verify_source_evidence(envelope_bytes: bytes, *, report: dict,
                                       manifest: dict, key: str | bytes) -> list[dict]:
    binding = _binding(report)
    if not isinstance(manifest, dict) or manifest.get("schema") != _SCHEMA:
        raise EncryptedEvidenceError("manifest_invalid")
    if (manifest.get("report_sha256") != binding["report_sha256"]
            or manifest.get("run_id") != binding["run_id"]
            or manifest.get("window") != binding["window"]):
        raise EncryptedEvidenceError("manifest_report_binding_mismatch")
    if not isinstance(envelope_bytes, bytes) or hashlib.sha256(envelope_bytes).hexdigest() != manifest.get("ciphertext_sha256"):
        raise EncryptedEvidenceError("ciphertext_digest_mismatch")
    try:
        envelope = json.loads(envelope_bytes)
        if set(envelope) != {"schema", "nonce", "ciphertext"} or envelope["schema"] != _SCHEMA:
            raise ValueError()
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
        aad = _canonical({"schema": _SCHEMA, "binding": binding})
        plaintext = AESGCM(_key(key)).decrypt(nonce, ciphertext, aad)
        decoded = json.loads(plaintext)
    except Exception:
        raise EncryptedEvidenceError("encrypted_evidence_authentication_failed") from None
    if decoded.get("schema") != _SCHEMA or decoded.get("binding") != binding:
        raise EncryptedEvidenceError("decrypted_binding_mismatch")
    evidence = decoded.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != manifest.get("evidence_count"):
        raise EncryptedEvidenceError("decrypted_evidence_count_mismatch")
    expected = {(r["provider"], r["competition_key"], r["source_id"]): r
                for r in report.get("records", [])}
    seen = set()
    for item in evidence:
        result = validate_source_payload_evidence(item)
        normalized = item["normalized_record"]
        key_tuple = (result["provider"], normalized["competition_key"], result["source_id"])
        if key_tuple in seen or key_tuple not in expected or normalized != expected[key_tuple]:
            raise EncryptedEvidenceError("decrypted_record_binding_mismatch")
        seen.add(key_tuple)
    if seen != set(expected):
        raise EncryptedEvidenceError("decrypted_evidence_coverage_incomplete")
    return evidence


def assert_sanitized_report_has_no_raw_payload(report: dict) -> None:
    """Reject raw source payload fields anywhere in the public report tree."""
    forbidden = {"payload", "raw_payload", "raw_row", "source_payload"}
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if forbidden.intersection(value):
                raise EncryptedEvidenceError("raw_payload_leaked_into_sanitized_report")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(report)
