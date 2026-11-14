"""Fail-closed V2 publication certification verifier.

The verifier is pure and offline. Trust in artifact attestations and provider
rights is injected by the deployment; absent callbacks or evidence always deny
publication. It does not create predictions or certify missing observations.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, ReportIdentity, verify_report_identity


CERTIFICATION_MANIFEST_SCHEMA = "VELTRIX_V2_CERTIFICATION_MANIFEST_V1"
_PUBLIC_RELEASE_MODES = frozenset({"RESTRICTED_PUBLIC", "FULL_PUBLIC"})
_HASH = re.compile(r"^[0-9a-f]{64}$")
MIN_WALK_FORWARD_MATCHES = 1000
MIN_PROSPECTIVE_SETTLED_SELECTIONS = 300
MIN_PROSPECTIVE_DATES = 90
MIN_TIMESTAMPED_ODDS_COVERAGE = 0.98


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def verify_publication_authorization(
    report: Mapping[str, Any],
    manifest_bytes: bytes,
    attestation_verifier: Callable[[bytes, str], bool],
    rights_verifier: Callable[[Mapping[str, Any]], bool],
    evidence_reader: Callable[[str], bytes],
) -> bool:
    """Return True only when every published fixture/market has certified evidence."""
    try:
        if not isinstance(report, Mapping) or not isinstance(manifest_bytes, bytes):
            return False
        if not manifest_bytes or len(manifest_bytes) > 8_000_000:
            return False
        if (
            not callable(attestation_verifier)
            or not callable(rights_verifier)
            or not callable(evidence_reader)
        ):
            return False

        identity = verify_report_identity(report)
        if report.get("schema") != REPORT_SCHEMA:
            return False
        if report.get("release_mode") not in _PUBLIC_RELEASE_MODES:
            return False

        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if attestation_verifier(manifest_bytes, manifest_sha256) is not True:
            return False

        manifest = json.loads(manifest_bytes.decode("utf-8"))
        if not isinstance(manifest, dict):
            return False
        if manifest.get("manifest_schema") != CERTIFICATION_MANIFEST_SCHEMA:
            return False
        if manifest.get("report_id") != identity.report_id:
            return False
        if manifest.get("report_sha256") != identity.report_sha256:
            return False

        records = manifest.get("certifications")
        predictions = report.get("predictions")
        if not isinstance(records, list) or not records:
            return False
        if not isinstance(predictions, list) or not predictions:
            return False

        indexed: dict[tuple[str, str], Mapping[str, Any]] = {}
        for record in records:
            if not isinstance(record, Mapping):
                return False
            competition_id = record.get("competition_id")
            market = record.get("market")
            if not isinstance(competition_id, str) or not competition_id.strip():
                return False
            if not isinstance(market, str) or not market.strip():
                return False
            key = (competition_id, market)
            if key in indexed:
                return False
            indexed[key] = record

        for fixture in predictions:
            if not isinstance(fixture, Mapping):
                return False
            if fixture.get("publication_status") != "PUBLISHED":
                return False
            competition_id = fixture.get("competition_id")
            model_build_id = fixture.get("model_build_id")
            markets = fixture.get("certified_markets")
            if not isinstance(competition_id, str) or not competition_id.strip():
                return False
            if not isinstance(model_build_id, str) or not model_build_id.strip():
                return False
            if not isinstance(markets, list) or not markets:
                return False
            if len(markets) != len(set(markets)):
                return False

            for market in markets:
                if not isinstance(market, str) or not market.strip():
                    return False
                record = indexed.get((competition_id, market))
                if record is None or record.get("model_build_id") != model_build_id:
                    return False

                integer_gates = (
                    ("walk_forward_matches", MIN_WALK_FORWARD_MATCHES),
                    ("prospective_settled_selections", MIN_PROSPECTIVE_SETTLED_SELECTIONS),
                    ("distinct_dates", MIN_PROSPECTIVE_DATES),
                )
                for field, minimum in integer_gates:
                    value = record.get(field)
                    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                        return False

                odds_coverage = record.get("timestamped_odds_coverage")
                net_roi = record.get("net_roi")
                roi_lower = record.get("roi_ci95_lower")
                if not _finite_number(odds_coverage) or float(odds_coverage) < MIN_TIMESTAMPED_ODDS_COVERAGE:
                    return False
                if not _finite_number(net_roi) or float(net_roi) <= 0:
                    return False
                if not _finite_number(roi_lower) or float(roi_lower) <= 0:
                    return False

                if market == "1X2":
                    brier = record.get("brier_score")
                    bookmaker_brier = record.get("bookmaker_brier_score")
                    log_loss = record.get("log_loss")
                    bookmaker_log_loss = record.get("bookmaker_log_loss")
                    if not all(_finite_number(value) for value in (
                        brier, bookmaker_brier, log_loss, bookmaker_log_loss
                    )):
                        return False
                    if float(brier) >= float(bookmaker_brier):
                        return False
                    if float(log_loss) >= float(bookmaker_log_loss):
                        return False

                if record.get("status") != "CERTIFIED":
                    return False
                if not isinstance(record.get("rights_approval_id"), str) or not record["rights_approval_id"].strip():
                    return False
                rights_evaluated_at = record.get("rights_evaluated_at")
                if not isinstance(rights_evaluated_at, str):
                    return False
                try:
                    parsed_rights_time = datetime.fromisoformat(rights_evaluated_at.replace("Z", "+00:00"))
                except ValueError:
                    return False
                if parsed_rights_time.tzinfo is None or parsed_rights_time.utcoffset() is None:
                    return False
                for uri_field, hash_field in (
                    ("evidence_uri", "evidence_sha256"),
                    ("rights_evidence_uri", "rights_evidence_sha256"),
                ):
                    evidence_uri = record.get(uri_field)
                    evidence_hash = record.get(hash_field)
                    if not isinstance(evidence_uri, str) or not evidence_uri.strip():
                        return False
                    parsed_uri = urlsplit(evidence_uri)
                    if parsed_uri.scheme not in {"https", "s3", "gs"} or not parsed_uri.netloc:
                        return False
                    if parsed_uri.username or parsed_uri.password or parsed_uri.query or parsed_uri.fragment:
                        return False
                    if not isinstance(evidence_hash, str) or not _HASH.fullmatch(evidence_hash):
                        return False
                    evidence_bytes = evidence_reader(evidence_uri)
                    if not isinstance(evidence_bytes, bytes):
                        return False
                    if hashlib.sha256(evidence_bytes).hexdigest() != evidence_hash:
                        return False
                if rights_verifier(record) is not True:
                    return False

        return True
    except Exception:
        return False


def build_publication_verifier(
    manifest_bytes: bytes,
    attestation_verifier: Callable[[bytes, str], bool],
    rights_verifier: Callable[[Mapping[str, Any]], bool],
    evidence_reader: Callable[[str], bytes],
) -> Callable[[Mapping[str, Any], ReportIdentity], bool]:
    """Create the callback contract used by website and Telegram consumers."""
    def verifier(report: Mapping[str, Any], identity: ReportIdentity) -> bool:
        try:
            if verify_report_identity(report) != identity:
                return False
            return verify_publication_authorization(
                report, manifest_bytes, attestation_verifier, rights_verifier, evidence_reader
            )
        except (KeyError, TypeError, ValueError):
            return False

    return verifier
