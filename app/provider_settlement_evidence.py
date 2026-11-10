"""Provider-specific settlement evidence extraction.

Current documented provider payloads expose terminal status, not a wall-clock
settlement timestamp. Never infer settlement time from kickoff, match duration,
event minute, retrieval time or odds.
"""
from __future__ import annotations

from typing import Any

SETTLEMENT_MAPPING_VERSIONS = {
    "strikerapi": "strikerapi.list_games.settlement-time.v1",
    "fivedollar": "fivedollar.fixtures.settlement-time.v1",
}


class SettlementEvidenceError(ValueError):
    pass


def extract_strikerapi_settlement(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise SettlementEvidenceError("strikerapi_payload_invalid")
    status, detail = payload.get("status"), payload.get("status_detail")
    confirmed = status == "final" and detail in (None, "FT")
    return {
        "mapping_version": SETTLEMENT_MAPPING_VERSIONS["strikerapi"],
        "provider": "strikerapi",
        "terminal_status_confirmed": confirmed,
        "terminal_status_field": "status",
        "terminal_status_value": status,
        "terminal_detail_field": "status_detail" if "status_detail" in payload else None,
        "terminal_detail_value": detail,
        "settlement_at": None,
        "settlement_timestamp_field": None,
        "settlement_time_available": False,
        "unavailable_reason": "provider_payload_has_no_documented_wall_clock_settlement_timestamp",
    }


def extract_fivedollar_settlement(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise SettlementEvidenceError("fivedollar_payload_invalid")
    status, status_code = payload.get("status"), payload.get("status_code")
    confirmed = status == "finished" and status_code == "full"
    return {
        "mapping_version": SETTLEMENT_MAPPING_VERSIONS["fivedollar"],
        "provider": "fivedollar",
        "terminal_status_confirmed": confirmed,
        "terminal_status_field": "status",
        "terminal_status_value": status,
        "terminal_detail_field": "status_code" if "status_code" in payload else None,
        "terminal_detail_value": status_code,
        "settlement_at": None,
        "settlement_timestamp_field": None,
        "settlement_time_available": False,
        "unavailable_reason": "provider_payload_has_no_documented_wall_clock_settlement_timestamp",
    }


def extract_settlement_evidence(provider: str, payload: Any) -> dict:
    if provider == "strikerapi":
        return extract_strikerapi_settlement(payload)
    if provider == "fivedollar":
        return extract_fivedollar_settlement(payload)
    raise SettlementEvidenceError("settlement_provider_unsupported")


def validate_settlement_evidence(evidence: Any, *, provider: str, payload: Any) -> dict:
    expected = extract_settlement_evidence(provider, payload)
    if evidence != expected:
        raise SettlementEvidenceError("settlement_evidence_payload_binding_mismatch")
    if evidence["settlement_time_available"] is not True or not evidence["settlement_at"]:
        raise SettlementEvidenceError("settlement_timestamp_unavailable")
    return evidence
