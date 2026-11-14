"""Manual-only 5Dollar first-observed prospective shadow capture.

Default invocation is dry-run and opens no DB connection or network request.
--execute is required for the bounded 5Dollar API + read-only staging workflow.
No production writes, publication, Telegram, schedules or settlement occur.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose, SourceApproval
from veltrix_v2.data.crosswalk_bootstrap import build_fivedollar_crosswalk_registry
from veltrix_v2.data.coverage_sql import (
    FIVEDOLLAR_CROSSWALK_BOOTSTRAP_SQL,
    validate_read_only_coverage_sql,
)
from veltrix_v2.data.fivedollar import parse_fixture_page
from veltrix_v2.data.provider_evidence_capture import capture_fivedollar_page_evidence
from veltrix_v2.data.evidence_persistence import persist_provider_evidence_report
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.data.temporal_eligibility import resolve_rights_status
from veltrix_v2.ledger.admission import admit_prospective_observed_shadow_forecasts
from veltrix_v2.ledger.jsonl_store import JsonlPaperLedgerStore
from veltrix_v2.ledger.postgres_store import PostgresPaperLedgerStore
from veltrix_v2.models.engine import predict_batch

from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target


API_BASE = "https://api.5dollarfootballapi.com/v1"
APPROVAL_ID = "approval-5dollar-community-fixture-result-2026-11"
MAX_REQUESTS = 14
MIN_REQUEST_INTERVAL_SECONDS = 3.1
USER_AGENT = "VELTRIX-FOOTBALL-2.0-READONLY-SHADOW/1.0"


APPROVAL_SQL = """
SELECT approval_id, provider, source_id, competition_scope, data_type,
       status, permitted_uses, commercial_use_allowed, terms_url, terms_version,
       evidence_uri, evidence_sha256, rights_basis, reviewed_at, reviewer_id,
       valid_from, valid_until, attribution_required, attribution_text,
       attribution_url, raw_redistribution_allowed
FROM source_approvals
WHERE approval_id = %s
""".strip()

APPROVAL_EVENTS_SQL = """
SELECT event_id, approval_id, status, evidence_uri, evidence_sha256,
       effective_at, recorded_at, reason_code
FROM source_approval_status_events
WHERE approval_id = %s
ORDER BY effective_at, recorded_at, event_id
""".strip()


def _rows_as_dicts(cursor) -> list[dict[str, object]]:
    names = [column.name for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _approval_from_rows(
    approval_row: dict[str, object],
    events: list[dict[str, object]],
    *,
    rights_evaluated_at: datetime,
) -> SourceApproval:
    if not events:
        raise PermissionError("SOURCE_APPROVAL_STATUS_EVENT_MISSING")
    resolution = resolve_rights_status(
        approval_row, events, rights_evaluated_at=rights_evaluated_at
    )
    if resolution.reason_code or resolution.status != "APPROVED":
        raise PermissionError(
            resolution.reason_code or "FIVEDOLLAR_SOURCE_NOT_APPROVED_AT_USE_TIME"
        )
    permitted = approval_row.get("permitted_uses")
    if not isinstance(permitted, (list, tuple)):
        raise ValueError("FIVEDOLLAR_APPROVAL_PURPOSES_INVALID")
    return SourceApproval(
        approval_id=str(approval_row["approval_id"]),
        provider=str(approval_row["provider"]),
        source_id=str(approval_row["source_id"]),
        competition_scope=str(approval_row["competition_scope"]),
        data_type=str(approval_row["data_type"]),
        status=ApprovalStatus(resolution.status),
        permitted_uses=frozenset(DataUsePurpose(str(value)) for value in permitted),
        commercial_use_allowed=bool(approval_row["commercial_use_allowed"]),
        terms_url=approval_row.get("terms_url"),
        terms_version=approval_row.get("terms_version"),
        evidence_uri=approval_row.get("evidence_uri"),
        evidence_sha256=approval_row.get("evidence_sha256"),
        rights_basis=approval_row.get("rights_basis"),
        reviewed_at_utc=approval_row.get("reviewed_at"),
        reviewer_id=approval_row.get("reviewer_id"),
        valid_from_utc=approval_row["valid_from"],
        valid_until_utc=approval_row.get("valid_until"),
        attribution_required=bool(approval_row.get("attribution_required")),
        attribution_text=approval_row.get("attribution_text"),
        attribution_url=approval_row.get("attribution_url"),
        raw_redistribution_allowed=bool(approval_row.get("raw_redistribution_allowed")),
    )


def _read_staging_context(dsn: str, *, require_paper_ledger: bool = False):
    validate_staging_dsn_target(dsn)
    validate_read_only_coverage_sql()
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PSYCOPG3_REQUIRED") from exc

    with psycopg.connect(dsn, autocommit=False) as connection:
        # First SQL statement; all following statements are SELECT-only.
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '20000ms'")
        identity = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner"):
            raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")

        approval_rows = _rows_as_dicts(connection.execute(APPROVAL_SQL, (APPROVAL_ID,)))
        if len(approval_rows) != 1:
            raise ValueError("FIVEDOLLAR_APPROVAL_RECORD_NOT_UNIQUE")
        event_rows = _rows_as_dicts(connection.execute(APPROVAL_EVENTS_SQL, (APPROVAL_ID,)))
        rights_evaluated_at = datetime.now(timezone.utc)
        approval = _approval_from_rows(
            approval_rows[0], event_rows, rights_evaluated_at=rights_evaluated_at
        )
        if require_paper_ledger:
            ledger_table_exists = connection.execute(
                "SELECT to_regclass('public.paper_ledger_events') IS NOT NULL"
            ).fetchone()[0]
            if not ledger_table_exists:
                raise RuntimeError("PAPER_LEDGER_STAGING_MIGRATION_REQUIRED")
        crosswalk_rows = _rows_as_dicts(
            connection.execute(FIVEDOLLAR_CROSSWALK_BOOTSTRAP_SQL)
        )
        crosswalk_verified_at = datetime.now(timezone.utc)
        registry = build_fivedollar_crosswalk_registry(
            crosswalk_rows, verified_at=crosswalk_verified_at
        )
        return approval, registry


def _refresh_approval(dsn: str) -> tuple[SourceApproval, datetime]:
    validate_staging_dsn_target(dsn)
    import psycopg

    with psycopg.connect(dsn, autocommit=False) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '10000ms'")
        identity = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner"):
            raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")
        rows = _rows_as_dicts(connection.execute(APPROVAL_SQL, (APPROVAL_ID,)))
        events = _rows_as_dicts(connection.execute(APPROVAL_EVENTS_SQL, (APPROVAL_ID,)))
        if len(rows) != 1:
            raise ValueError("FIVEDOLLAR_APPROVAL_RECORD_NOT_UNIQUE")
        rights_evaluated_at = datetime.now(timezone.utc)
        return (
            _approval_from_rows(rows[0], events, rights_evaluated_at=rights_evaluated_at),
            rights_evaluated_at,
        )


def _approved_competition_ids(approval: SourceApproval, registry) -> list[str]:
    scope = {
        value.strip()
        for value in approval.competition_scope.split(",")
        if value.strip()
    }
    if not scope or "*" in scope:
        raise PermissionError("FIVEDOLLAR_COMPETITION_SCOPE_INVALID")
    return sorted(scope.intersection(registry.competition_crosswalks), key=int)


def _hash_files(paths: tuple[str, ...]) -> str:
    rows = []
    for name in paths:
        content_hash = sha256(Path(name).read_bytes()).hexdigest()
        rows.append({"path": name, "sha256": content_hash})
    payload = json.dumps(
        rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _persist_paper_predictions_to_staging(
    dsn: str, predictions: list
) -> dict[str, object]:
    """Idempotently append one atomic batch to the allowlisted staging ledger."""
    validate_staging_dsn_target(dsn)
    import psycopg

    host = urlparse(dsn).hostname or ""
    with psycopg.connect(dsn, autocommit=False) as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner"):
            raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")
        store = PostgresPaperLedgerStore(
            connection,
            ledger_id="veltrix-v2-prospective-observed",
            write_enabled=True,
            environment="staging",
            database_name=identity[0],
            host=host,
            role=identity[1],
        )
        if predictions:
            appended, duplicates, ledger = store.append_predictions_idempotent(predictions)
        else:
            ledger = store.load()
            appended, duplicates = [], 0
        if not ledger.verify_chain():
            raise ValueError("PAPER_LEDGER_CHAIN_VERIFICATION_FAILED")
        return {
            "events_appended": len(appended),
            "duplicate_predictions_skipped": duplicates,
            "ledger_event_count": len(ledger.events),
            "ledger_head_sha256": (
                ledger.events[-1].event_sha256 if ledger.events else None
            ),
            "chain_verified": True,
        }


def _request_parameters(
    *, competition_id: str, status: str, start_at: datetime, end_at: datetime, page: int
) -> dict[str, object]:
    return {
        "start_time": int(start_at.timestamp()),
        "end_time": int(end_at.timestamp()),
        "status": status,
        "order": "desc" if status == "finished" else "asc",
        "page": page,
        "per_page": 100,
    }


def _request_page(
    api_key: str,
    *,
    competition_id: str,
    status: str,
    start_at: datetime,
    end_at: datetime,
    page: int,
    pacing_state: dict[str, float | None],
    before_request,
) -> tuple[bytes, dict[str, str], datetime, datetime, int]:
    last_request_started = pacing_state.get("last_started")
    if last_request_started is not None:
        delay = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_request_started)
        if delay > 0:
            time.sleep(delay)
    before_request()
    requested_at = datetime.now(timezone.utc)
    pacing_state["last_started"] = time.monotonic()
    params = _request_parameters(
        competition_id=competition_id, status=status,
        start_at=start_at, end_at=end_at, page=page,
    )
    endpoint = f"/leagues/{competition_id}/fixtures"
    url = f"{API_BASE}{endpoint}?{urlencode(params)}"
    request = Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read()
            headers = {str(k): str(v) for k, v in response.headers.items()}
            http_status = int(response.status)
    except HTTPError as exc:
        if exc.code == 403:
            raise PermissionError("FIVEDOLLAR_COMPETITION_NOT_ENTITLED") from None
        if exc.code == 429:
            raise RuntimeError("FIVEDOLLAR_RATE_LIMITED_NO_RETRY") from None
        if exc.code == 401:
            raise PermissionError("FIVEDOLLAR_API_KEY_REJECTED") from None
        raise RuntimeError(f"FIVEDOLLAR_HTTP_{exc.code}") from None
    except URLError:
        raise RuntimeError("FIVEDOLLAR_NETWORK_ERROR_NO_RETRY") from None
    retrieved_at = datetime.now(timezone.utc)
    if not raw:
        raise RuntimeError("FIVEDOLLAR_EMPTY_RESPONSE")
    return raw, headers, requested_at, retrieved_at, http_status


def _persist_capture_report_to_staging(
    dsn: str, capture_report, *, http_status: int,
    request_params: dict[str, object],
    response_headers: dict[str, str],
) -> dict[str, int]:
    validate_staging_dsn_target(dsn)
    import psycopg

    parsed = urlparse(dsn)
    host = parsed.hostname or ""
    with psycopg.connect(dsn, autocommit=False) as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner"):
            raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")
        return persist_provider_evidence_report(
            connection,
            capture_report,
            capture_report.captures,
            write_enabled=True,
            environment="staging",
            database_name=identity[0],
            host=host,
            role=identity[1],
            http_status=http_status,
            request_params=request_params,
            response_headers=response_headers,
        )


def _capture_page(
    raw: bytes,
    headers: dict[str, str],
    *,
    competition_id: str,
    status: str,
    request_id: str,
    requested_at: datetime,
    retrieved_at: datetime,
    http_status: int,
    request_params: dict[str, object],
    registry,
    out_dir: Path,
    staging_dsn: str,
    persist_staging: bool,
) -> tuple[list, dict[str, object]]:
    parsed = parse_fixture_page(
        raw,
        headers=headers,
        retrieved_at_utc=retrieved_at,
        rights_approval_id=APPROVAL_ID,
    )
    page_path = out_dir / "raw" / f"{competition_id}_{status}_page_1.json"

    page_info: dict[str, object] = {
        "competition_id": competition_id,
        "status_filter": status,
        "request_id": request_id,
        "endpoint": f"/leagues/{competition_id}/fixtures",
        "requested_at": requested_at.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "http_status": http_status,
        "request_params": request_params,
        "raw_response_sha256": sha256(raw).hexdigest(),
        "raw_response_bytes": len(raw),
        "page": parsed.page,
        "per_page": parsed.per_page,
        "has_more": parsed.has_more,
        "quota_limit": parsed.quota_limit,
        "quota_remaining": parsed.quota_remaining,
        "fixture_rows": len(parsed.fixtures),
    }

    if status == "finished":
        finished_fixtures = [
            fixture for fixture in parsed.fixtures
            if fixture.status.value == "FINISHED"
        ]
        if not finished_fixtures:
            page_info.update({
                "capture_observations": 0,
                "first_observed_observations": 0,
                "no_finished_rows": True,
                "point_in_time_certifiable": False,
            })
            return [], page_info
        current_approval, recorded_at = _refresh_approval(staging_dsn)
        for purpose in (DataUsePurpose.STORAGE, DataUsePurpose.MODEL_TRAINING):
            decision = evaluate_source_use(
                current_approval, purpose, at_utc=recorded_at, commercial=True
            )
            if not decision.allowed:
                raise PermissionError(decision.reason_code)
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_bytes(raw)
        page_info["raw_artifact"] = str(page_path)
        capture = capture_fivedollar_page_evidence(
            raw,
            parsed,
            endpoint=page_info["endpoint"],
            request_id=request_id,
            requested_at=requested_at,
            recorded_at=recorded_at,
            crosswalks=registry.fixture_crosswalks,
            rights_approval=current_approval,
            prospective_observed=True,
        )
        persistence = (
            _persist_capture_report_to_staging(
                staging_dsn, capture, http_status=http_status,
                request_params=request_params, response_headers=headers,
            )
            if persist_staging else None
        )
        converted = []
        rejected: dict[str, int] = {}
        for index, evidence in enumerate(capture.observations):
            try:
                converted.append(evidence.to_first_observed_match_observation(
                    manifest_sha256=capture.manifest.manifest_sha256,
                    evidence_sha256=capture.manifest.item_evidence_sha256[index],
                ))
            except (ValueError, IndexError) as exc:
                reason = str(exc)[:120]
                rejected[reason] = rejected.get(reason, 0) + 1
        page_info.update({
            "capture_manifest_sha256": capture.manifest.manifest_sha256,
            "capture_observations": len(capture.observations),
            "first_observed_observations": len(converted),
            "rejected_observations": rejected,
            "point_in_time_certifiable": False,
            "persisted_to_staging": persistence,
        })
        return converted, page_info

    current_approval, recorded_at = _refresh_approval(staging_dsn)
    for purpose in (DataUsePurpose.STORAGE, DataUsePurpose.CACHE):
        decision = evaluate_source_use(
            current_approval, purpose, at_utc=recorded_at, commercial=True
        )
        if not decision.allowed:
            raise PermissionError(decision.reason_code)
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_bytes(raw)
    page_info["raw_artifact"] = str(page_path)

    targets = []
    rejected_targets: dict[str, int] = {}
    for fixture in parsed.fixtures:
        try:
            targets.append(registry.to_prediction_target(fixture))
        except (ValueError, TypeError) as exc:
            reason = str(exc)[:120]
            rejected_targets[reason] = rejected_targets.get(reason, 0) + 1
    page_info.update({
        "mapped_targets": len(targets),
        "rejected_targets": rejected_targets,
    })
    return targets, page_info


def _build_public_summary(summary: dict[str, object]) -> dict[str, object]:
    """Explicit allowlist projection; never expose IDs, hashes, odds or probabilities."""
    allowed = (
        "status", "provider", "requests_used", "request_cap",
        "crosswalk_registry", "captured_first_observed_rows",
        "mapped_upcoming_targets", "forecast_count",
        "admitted_shadow_predictions", "persisted_capture_pages",
        "persisted_shadow_ledger_events", "paper_ledger_persisted_to_staging",
        "paper_ledger_chain_verified", "duplicate_predictions_skipped",
        "evidence_persisted_to_staging", "publication_status",
        "settlement_status", "database_writes",
    )
    return {
        **{key: summary[key] for key in allowed if key in summary},
        "telegram_delivery": False,
        "schedule_activation": False,
        "public_publication": False,
    }


def run_capture(
    *,
    api_key: str,
    staging_dsn: str,
    history_days: int,
    upcoming_days: int,
    max_fixtures: int,
    out_dir: Path,
    persist_staging: bool = False,
) -> dict[str, object]:
    if not api_key.strip():
        raise ValueError("FIVEDOLLAR_API_KEY_MISSING")
    if not 1 <= history_days <= 90 or not 1 <= upcoming_days <= 14:
        raise ValueError("CAPTURE_WINDOW_OUT_OF_RANGE")
    if not 1 <= max_fixtures <= 25:
        raise ValueError("MAX_FIXTURES_OUT_OF_RANGE")

    approval, registry = _read_staging_context(
        staging_dsn, require_paper_ledger=persist_staging
    )
    initial_time = datetime.now(timezone.utc)
    for purpose in (DataUsePurpose.COLLECTION, DataUsePurpose.CACHE, DataUsePurpose.MODEL_TRAINING):
        decision = evaluate_source_use(approval, purpose, at_utc=initial_time, commercial=True)
        if not decision.allowed:
            raise PermissionError(decision.reason_code)

    competition_ids = _approved_competition_ids(approval, registry)
    if not competition_ids:
        raise ValueError("NO_APPROVED_COMPETITIONS_HAVE_VERIFIED_CROSSWALKS")

    now = datetime.now(timezone.utc)
    history_start = now - timedelta(days=history_days)
    upcoming_end = now + timedelta(days=upcoming_days)
    observations = []
    targets = []
    page_manifests = []
    request_count = 0
    pacing_state: dict[str, float | None] = {"last_started": None}
    skipped_competitions = []

    for competition_id in competition_ids:
        if request_count >= MAX_REQUESTS:
            raise RuntimeError("FIVEDOLLAR_REQUEST_CAP_REACHED")
        def check_collection_rights():
            current, evaluated_at = _refresh_approval(staging_dsn)
            decision = evaluate_source_use(
                current, DataUsePurpose.COLLECTION,
                at_utc=evaluated_at, commercial=True,
            )
            if not decision.allowed:
                raise PermissionError(decision.reason_code)
            return evaluated_at

        request_id = f"{os.getenv('GITHUB_RUN_ID', 'manual')}-{competition_id}-finished-1"
        request_count += 1
        try:
            raw, headers, requested_at, retrieved_at, http_status = _request_page(
                api_key, competition_id=competition_id, status="finished",
                start_at=history_start, end_at=now, page=1,
                pacing_state=pacing_state,
                before_request=check_collection_rights,
            )
        except PermissionError as exc:
            if str(exc) == "FIVEDOLLAR_COMPETITION_NOT_ENTITLED":
                skipped_competitions.append({"competition_id": competition_id, "reason": str(exc)})
                continue
            raise
        result_rows, info = _capture_page(
            raw, headers, competition_id=competition_id, status="finished",
            request_id=request_id, requested_at=requested_at, retrieved_at=retrieved_at,
            http_status=http_status,
            request_params=_request_parameters(
                competition_id=competition_id, status="finished",
                start_at=history_start, end_at=now, page=1,
            ),
            registry=registry, out_dir=out_dir,
            staging_dsn=staging_dsn,
            persist_staging=persist_staging,
        )
        observations.extend(result_rows)
        page_manifests.append(info)
        quota_remaining = info.get("quota_remaining")
        if isinstance(quota_remaining, int):
            planned_remaining = MAX_REQUESTS - request_count
            if planned_remaining > 0 and quota_remaining < planned_remaining:
                raise RuntimeError("FIVEDOLLAR_QUOTA_BELOW_BOUNDED_REQUEST_PLAN")

        if request_count >= MAX_REQUESTS:
            break
        def check_scheduled_collection_rights():
            current, evaluated_at = _refresh_approval(staging_dsn)
            decision = evaluate_source_use(
                current, DataUsePurpose.COLLECTION,
                at_utc=evaluated_at, commercial=True,
            )
            if not decision.allowed:
                raise PermissionError(decision.reason_code)
            return evaluated_at
        request_id = f"{os.getenv('GITHUB_RUN_ID', 'manual')}-{competition_id}-scheduled-1"
        request_count += 1
        try:
            raw, headers, requested_at, retrieved_at, http_status = _request_page(
                api_key, competition_id=competition_id, status="scheduled",
                start_at=now, end_at=upcoming_end, page=1,
                pacing_state=pacing_state,
                before_request=check_scheduled_collection_rights,
            )
        except PermissionError as exc:
            if str(exc) == "FIVEDOLLAR_COMPETITION_NOT_ENTITLED":
                skipped_competitions.append({"competition_id": competition_id, "reason": str(exc)})
                continue
            raise
        target_rows, info = _capture_page(
            raw, headers, competition_id=competition_id, status="scheduled",
            request_id=request_id, requested_at=requested_at, retrieved_at=retrieved_at,
            http_status=http_status,
            request_params=_request_parameters(
                competition_id=competition_id, status="scheduled",
                start_at=now, end_at=upcoming_end, page=1,
            ),
            registry=registry, out_dir=out_dir,
            staging_dsn=staging_dsn,
            persist_staging=persist_staging,
        )
        targets.extend(target_rows)
        page_manifests.append(info)
        quota_remaining = info.get("quota_remaining")
        if isinstance(quota_remaining, int):
            planned_remaining = MAX_REQUESTS - request_count
            if quota_remaining < max(1, planned_remaining):
                raise RuntimeError("FIVEDOLLAR_QUOTA_BELOW_BOUNDED_REQUEST_PLAN")

    # Stable deduplication; conflicting duplicates are rejected rather than selected.
    observation_by_fixture = {}
    for observation in observations:
        previous = observation_by_fixture.get(observation.fixture_id)
        if previous is not None and previous != observation:
            raise ValueError("OBSERVED_HISTORY_DUPLICATE_CONFLICT")
        observation_by_fixture[observation.fixture_id] = observation
    observations = list(observation_by_fixture.values())

    target_by_fixture = {}
    for target in targets:
        previous = target_by_fixture.get(target.fixture_id)
        if previous is not None and previous != target:
            raise ValueError("TARGET_FIXTURE_DUPLICATE_CONFLICT")
        target_by_fixture[target.fixture_id] = target
    targets = sorted(target_by_fixture.values(), key=lambda item: (item.kickoff_at, item.fixture_id))
    targets = targets[:max_fixtures]

    cutoff_at = datetime.now(timezone.utc)
    forecast_report = predict_batch(
        observations, targets, cutoff_at=cutoff_at, max_fixtures=max_fixtures
    )
    forecasted_at = datetime.now(timezone.utc)
    current_approval, recorded_at = _refresh_approval(staging_dsn)

    model_hash = _hash_files((
        "veltrix_v2/models/poisson.py",
        "veltrix_v2/models/engine.py",
    ))
    feature_hash = _hash_files((
        "docs/VELTRIX_V2_PHASE4_PREMATCH_FEATURE_TAXONOMY_2026-11-13.md",
        "veltrix_v2/data/temporal_eligibility.py",
        "veltrix_v2/data/provider_evidence_capture.py",
    ))
    admission = admit_prospective_observed_shadow_forecasts(
        forecast_report,
        targets,
        observations,
        source_approvals={current_approval.approval_id: current_approval},
        forecasted_at=forecasted_at,
        recorded_at=recorded_at,
        model_artifact_sha256=model_hash,
        feature_set_sha256=feature_hash,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "paper" / "observed_shadow_ledger.jsonl"
    local_store = JsonlPaperLedgerStore(ledger_path)
    ledger_events = [
        local_store.append_prediction(prediction) for prediction in admission.admitted
    ]
    staging_ledger = (
        _persist_paper_predictions_to_staging(staging_dsn, admission.admitted)
        if persist_staging else None
    )

    benchmarking_allowed = DataUsePurpose.BENCHMARKING in current_approval.permitted_uses
    persisted_capture_pages = sum(
        1 for page in page_manifests if page.get("persisted_to_staging")
    )
    summary = {
        "status": "SHADOW_CAPTURE_COMPLETE" if admission.admitted else "NO_ADMISSIBLE_SHADOW_FORECASTS",
        "provider": "5DollarFootballAPI",
        "approval_id": current_approval.approval_id,
        "competition_scope": competition_ids,
        "requests_used": request_count,
        "request_cap": MAX_REQUESTS,
        "history_days": history_days,
        "upcoming_days": upcoming_days,
        "max_fixtures": max_fixtures,
        "crosswalk_registry": registry.summary(),
        "captured_first_observed_rows": len(observations),
        "mapped_upcoming_targets": len(targets),
        "forecast_count": forecast_report.forecast_count,
        "skipped_no_history": forecast_report.skipped_no_history,
        "skipped_invalid_targets": forecast_report.skipped_invalid_targets,
        "admitted_shadow_predictions": len(admission.admitted),
        "rejected_admissions": [
            {"fixture_id": item.fixture_id, "reason_code": item.reason_code}
            for item in admission.rejected
        ],
        "persisted_shadow_ledger_events": (
            int(staging_ledger["events_appended"]) if staging_ledger else 0
        ),
        "ledger_events": [
            {"event_type": event.event_type, "fixture_id": event.fixture_id,
             "model_version": event.model_version, "event_sha256": event.event_sha256}
            for event in ledger_events
        ],
        "ledger_path": str(ledger_path),
        "paper_ledger_persisted_to_staging": bool(
            staging_ledger and staging_ledger["ledger_event_count"] > 0
        ),
        "paper_ledger_chain_verified": bool(
            staging_ledger and staging_ledger["chain_verified"]
        ),
        "duplicate_predictions_skipped": (
            int(staging_ledger["duplicate_predictions_skipped"])
            if staging_ledger else 0
        ),
        "staging_paper_ledger": staging_ledger,
        "model_artifact_sha256": model_hash,
        "feature_set_sha256": feature_hash,
        "page_manifests": page_manifests,
        "skipped_competitions": skipped_competitions,
        "point_in_time_certifiable": False,
        "publication_status": "LOCKED_PROSPECTIVE_OBSERVED_SHADOW_ONLY",
        "settlement_status": (
            "BENCHMARKING_RIGHTS_APPROVED" if benchmarking_allowed
            else "LOCKED_BENCHMARKING_RIGHTS_NOT_APPROVED"
        ),
        "attribution": {
            "required": current_approval.attribution_required,
            "text": current_approval.attribution_text,
            "url": current_approval.attribution_url,
        },
        "raw_redistribution_allowed": current_approval.raw_redistribution_allowed,
        "persisted_capture_pages": persisted_capture_pages,
        "evidence_persisted_to_staging": persisted_capture_pages > 0,
        "database_writes": (
            persisted_capture_pages > 0
            or bool(staging_ledger and staging_ledger["events_appended"] > 0)
        ),
        "telegram_delivery": False,
        "schedule_activation": False,
        "public_publication": False,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    public_summary = _build_public_summary(summary)
    (out_dir / "public_summary.json").write_text(
        json.dumps(public_summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual 5Dollar prospective shadow capture")
    parser.add_argument("--execute", action="store_true",
                        help="perform bounded provider requests and read-only staging queries")
    parser.add_argument("--history-days", type=int, default=90)
    parser.add_argument("--upcoming-days", type=int, default=14)
    parser.add_argument("--max-fixtures", type=int, default=25)
    parser.add_argument("--out", default="artifacts/5dollar-shadow")
    parser.add_argument("--persist-staging", action="store_true",
                        help="append raw capture evidence to the allowlisted staging database")
    args = parser.parse_args()

    if not args.execute:
        print(json.dumps({
            "mode": "DRY_RUN",
            "would_connect_to_database": False,
            "would_call_provider": False,
            "provider": "5DollarFootballAPI",
            "request_cap": MAX_REQUESTS,
            "max_fixtures": min(max(args.max_fixtures, 1), 25),
            "history_days": args.history_days,
            "upcoming_days": args.upcoming_days,
            "manual_only": True,
            "publication": "DISABLED",
            "persist_staging": args.persist_staging,
        }, indent=2))
        return 0

    api_key = os.environ.get("FIVEDOLLARFOOTBALL_API_KEY", "")
    staging_dsn = os.environ.get("VELTRIX_STAGING_DATABASE_URL", "")
    result = run_capture(
        api_key=api_key,
        staging_dsn=staging_dsn,
        history_days=args.history_days,
        upcoming_days=args.upcoming_days,
        max_fixtures=args.max_fixtures,
        out_dir=Path(args.out),
        persist_staging=args.persist_staging,
    )
    print(json.dumps({
        "status": result["status"],
        "requests_used": result["requests_used"],
        "captured_first_observed_rows": result["captured_first_observed_rows"],
        "mapped_upcoming_targets": result["mapped_upcoming_targets"],
        "admitted_shadow_predictions": result["admitted_shadow_predictions"],
        "publication_status": result["publication_status"],
        "settlement_status": result["settlement_status"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
