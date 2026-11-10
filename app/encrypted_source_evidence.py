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
    SourcePayloadProvenanceError,
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
    if not run_ids and isinstance(report.get("run_id"), str):
        run_ids.add(report["run_id"])
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
    """Build complete encrypted evidence for accepted and quarantined inputs."""
    records = report.get("records")
    quarantine = report.get("quarantine")
    if (not isinstance(observations, list) or not isinstance(records, list)
            or not isinstance(quarantine, list)):
        raise EncryptedEvidenceError("evidence_inputs_invalid")
    raw_by_key: dict[tuple[str, str, str], list[tuple[int, dict, dict]]] = {}
    for index, item in enumerate(observations):
        if not isinstance(item, dict) or not isinstance(item.get("row"), dict):
            continue
        options = item.get("options") or {}
        row = item["row"]
        league = row.get("league") or {}
        key = (item.get("provider"), str(league.get("id", "")), str(row.get("id", "")))
        raw_by_key.setdefault(key, []).append((index, row, options))

    evidence: list[dict] = []
    accepted_indexes: set[int] = set()
    for record in records:
        key = (record.get("provider"), str(record.get("competition_key", "")),
               str(record.get("source_id", "")))
        matches = raw_by_key.get(key, [])
        if len(matches) != 1:
            raise EncryptedEvidenceError("accepted_record_raw_payload_missing_or_ambiguous")
        input_index, payload, options = matches.pop()
        accepted_indexes.add(input_index)
        normalized_record = {
            field: value for field, value in record.items() if field != "source_evidence"
        }
        item = {
            "kind": "accepted",
            "input_index": input_index,
            "provider": record["provider"],
            "endpoint": record["endpoint"],
            "source_id": record["source_id"],
            "run_id": record["run_id"],
            "retrieved_at": record["retrieved_at"],
            "payload": payload,
            "payload_sha256": canonical_payload_sha256(payload),
            "normalized_record": normalized_record,
            "normalized_record_sha256": canonical_payload_sha256(normalized_record),
        }
        if options.get("run_id") != record["run_id"] or options.get("endpoint") != record["endpoint"]:
            raise EncryptedEvidenceError("raw_observation_metadata_mismatch")
        validate_source_payload_evidence({
            key: value for key, value in item.items()
            if key not in {"kind", "input_index"}
        })
        if item["payload_sha256"] != record["payload_sha256"]:
            raise EncryptedEvidenceError("normalizer_payload_hash_mismatch")
        evidence.append(item)

    quarantined_indexes: set[int] = set()
    for quarantine_item in quarantine:
        if not isinstance(quarantine_item, dict):
            raise EncryptedEvidenceError("quarantine_record_invalid")
        input_index = quarantine_item.get("input_index")
        if (isinstance(input_index, bool) or not isinstance(input_index, int)
                or input_index < 0 or input_index >= len(observations)
                or input_index in quarantined_indexes or input_index in accepted_indexes):
            raise EncryptedEvidenceError("quarantine_input_index_invalid")
        observation = observations[input_index]
        if isinstance(observation, dict):
            provider = observation.get("provider")
            payload = observation.get("row")
            options = observation.get("options") or {}
        else:
            provider, payload, options = None, observation, {}
        try:
            payload_digest = canonical_payload_sha256(payload)
        except SourcePayloadProvenanceError:
            raise EncryptedEvidenceError("quarantine_payload_not_canonical_json") from None
        source_summary = quarantine_item.get("source")
        if isinstance(source_summary, dict) and source_summary.get("payload_sha256") not in (None, payload_digest):
            raise EncryptedEvidenceError("quarantine_payload_hash_binding_mismatch")
        entry = {
            "kind": "quarantined",
            "input_index": input_index,
            "provider": provider if isinstance(provider, str) else "unknown",
            "endpoint": options.get("endpoint") if isinstance(options, dict) else None,
            "run_id": options.get("run_id") if isinstance(options, dict) else None,
            "retrieved_at": options.get("retrieved_at") if isinstance(options, dict) else None,
            "payload": payload,
            "payload_sha256": payload_digest,
            "quarantine_reason": quarantine_item.get("reason"),
            "source_summary": source_summary,
        }
        if entry["run_id"] is None:
            entry["run_id"] = report.get("run_id")
        if entry["retrieved_at"] is None:
            entry["retrieved_at"] = report.get("retrieved_at")
        evidence.append(entry)
        quarantined_indexes.add(input_index)

    expected_indexes = set(range(len(observations)))
    if accepted_indexes | quarantined_indexes != expected_indexes:
        raise EncryptedEvidenceError("encrypted_evidence_input_coverage_incomplete")
    if accepted_indexes & quarantined_indexes:
        raise EncryptedEvidenceError("encrypted_evidence_input_coverage_overlap")
    evidence.sort(key=lambda item: item["input_index"])
    return evidence


def encrypt_source_evidence(evidence: list[dict], *, report: dict,
                            key: str | bytes, nonce: bytes | None = None) -> tuple[bytes, dict]:
    """Return encrypted JSON envelope bytes and a plaintext-safe manifest."""
    binding = _binding(report)
    expected_count = report.get("quality", {}).get("input_count")
    if (isinstance(expected_count, bool) or not isinstance(expected_count, int)
            or not isinstance(evidence, list) or len(evidence) != expected_count):
        raise EncryptedEvidenceError("evidence_count_mismatch")
    for item in evidence:
        if not isinstance(item, dict) or item.get("kind") not in {"accepted", "quarantined"}:
            raise EncryptedEvidenceError("evidence_entry_kind_invalid")
        if item.get("run_id") != binding["run_id"]:
            raise EncryptedEvidenceError("evidence_run_binding_mismatch")
        if item["kind"] == "accepted":
            validated = validate_source_payload_evidence({
                key: value for key, value in item.items()
                if key not in {"kind", "input_index"}
            })
            if validated["run_id"] != binding["run_id"]:
                raise EncryptedEvidenceError("evidence_run_binding_mismatch")
        else:
            if canonical_payload_sha256(item.get("payload")) != item.get("payload_sha256"):
                raise EncryptedEvidenceError("quarantine_payload_digest_mismatch")
            if not isinstance(item.get("quarantine_reason"), str):
                raise EncryptedEvidenceError("quarantine_reason_missing")
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
        "accepted_count": sum(1 for item in evidence if item.get("kind") == "accepted"),
        "quarantined_count": sum(1 for item in evidence if item.get("kind") == "quarantined"),
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
    expected_total = report.get("quality", {}).get("input_count")
    if (not isinstance(evidence, list) or len(evidence) != manifest.get("evidence_count")
            or len(evidence) != expected_total):
        raise EncryptedEvidenceError("decrypted_evidence_count_mismatch")
    expected = {(r["provider"], r["competition_key"], r["source_id"]): {
        key: value for key, value in r.items() if key != "source_evidence"
    } for r in report.get("records", [])}
    expected_quarantine = {item["input_index"]: item for item in report.get("quarantine", [])}
    seen_accepted = set()
    seen_quarantine = set()
    seen_indexes = set()
    for item in evidence:
        if not isinstance(item, dict) or item.get("kind") not in {"accepted", "quarantined"}:
            raise EncryptedEvidenceError("decrypted_evidence_entry_invalid")
        index = item.get("input_index")
        if isinstance(index, bool) or not isinstance(index, int) or index in seen_indexes:
            raise EncryptedEvidenceError("decrypted_evidence_input_index_invalid")
        seen_indexes.add(index)
        if item["kind"] == "accepted":
            result = validate_source_payload_evidence({
                key: value for key, value in item.items()
                if key not in {"kind", "input_index"}
            })
            normalized = item["normalized_record"]
            key_tuple = (result["provider"], normalized["competition_key"], result["source_id"])
            if key_tuple in seen_accepted or key_tuple not in expected or normalized != expected[key_tuple]:
                raise EncryptedEvidenceError("decrypted_record_binding_mismatch")
            seen_accepted.add(key_tuple)
        else:
            quarantine_item = expected_quarantine.get(index)
            if (quarantine_item is None or item.get("quarantine_reason") != quarantine_item.get("reason")
                    or item.get("source_summary") != quarantine_item.get("source")
                    or canonical_payload_sha256(item.get("payload")) != item.get("payload_sha256")):
                raise EncryptedEvidenceError("decrypted_quarantine_binding_mismatch")
            seen_quarantine.add(index)
    if (seen_accepted != set(expected) or seen_quarantine != set(expected_quarantine)
            or seen_indexes != set(range(expected_total))):
        raise EncryptedEvidenceError("decrypted_evidence_coverage_incomplete")
    if manifest.get("accepted_count") != len(seen_accepted) or manifest.get("quarantined_count") != len(seen_quarantine):
        raise EncryptedEvidenceError("decrypted_evidence_manifest_counts_mismatch")
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
