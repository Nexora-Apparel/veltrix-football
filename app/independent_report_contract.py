"""Fail-closed contract for publicly visible independent-model predictions.

Legacy daily reports are never publishable. A report must carry the independent
portfolio identity and an authorization artifact emitted by the release gate.
"""
from __future__ import annotations

import re
from typing import Any

REPORT_SCHEMA = "VELTRIX_INDEPENDENT_PREDICTION_REPORT_V1"
MODEL_PORTFOLIO_ID = "veltrix-independent-market-portfolio-v1"
_CERTIFICATE_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def is_publishable_independent_report(report: Any) -> bool:
    """Return true only for a report carrying explicit independent release authorization."""
    if not isinstance(report, dict):
        return False
    if (
        report.get("report_schema") != REPORT_SCHEMA
        or report.get("model_portfolio_id") != MODEL_PORTFOLIO_ID
        or report.get("legacy_model_dependency") is not False
        or report.get("publication_allowed") is not True
    ):
        return False
    certificate = report.get("release_certificate")
    if not isinstance(certificate, dict):
        return False
    return (
        certificate.get("status") == "CERTIFIED"
        and certificate.get("publication_authorized") is True
        and certificate.get("signature_verified") is True
        and isinstance(certificate.get("certificate_sha256"), str)
        and _CERTIFICATE_DIGEST.fullmatch(certificate["certificate_sha256"]) is not None
        and certificate.get("model_portfolio_id") == MODEL_PORTFOLIO_ID
    )


def is_value_betting_authorized_report(report: Any) -> bool:
    """Require a separate signed, market-specific value-betting authorization."""
    if not is_publishable_independent_report(report):
        return False
    if report.get("value_betting_authorized") is not True:
        return False
    certificate = report.get("value_validation_certificate")
    if not isinstance(certificate, dict):
        return False
    approved = certificate.get("approved_markets")
    allowed_markets = {
        "1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5"
    }
    return (
        certificate.get("status") == "CERTIFIED"
        and certificate.get("alerts_enabled") is True
        and certificate.get("signature_verified") is True
        and isinstance(certificate.get("certificate_sha256"), str)
        and _CERTIFICATE_DIGEST.fullmatch(certificate["certificate_sha256"]) is not None
        and isinstance(approved, list)
        and bool(approved)
        and set(approved).issubset(allowed_markets)
    )


def is_independent_paper_ledger(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("ledger_schema") == "VELTRIX_INDEPENDENT_PAPER_LEDGER_V1"
        and value.get("model_portfolio_id") == MODEL_PORTFOLIO_ID
        and value.get("legacy_model_dependency") is False
        and value.get("model_status") == "PAPER_TRACKING_ONLY"
    )


def is_independent_model_validation(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("validation_schema") == "VELTRIX_INDEPENDENT_MODEL_VALIDATION_V1"
        and value.get("model_portfolio_id") == MODEL_PORTFOLIO_ID
        and value.get("legacy_model_dependency") is False
        and isinstance(value.get("dataset"), dict)
    )
