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
