#!/usr/bin/env python3
"""One-year, read-only 5Dollar historical fixture/result qualification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import sys

# Direct execution sets sys.path[0] to scripts/, not the repository root.
# Add the checkout root so the sibling veltrix_v2 package resolves in CI.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from veltrix_v2.data.batch import assess_history_batch
from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose, SourceApproval
from veltrix_v2.data.fivedollar import FixturePageError, parse_fixture_page

BASE = "https://api.5dollarfootballapi.com/v1"
PROVIDER = "5DollarFootballAPI"
SOURCE_ID = "5dollarfootballapi"
REQUEST_BUDGET = 40
PER_PAGE = 100
PACE_SECONDS = 4.0
EXPECTED_COMPETITIONS = {
    "3118717965": "Brazil Serie A",
    "522514093": "Brazil Serie B",
    "4160026622": "England Premier League",
    "3614399544": "France Ligue 1",
    "686337048": "Germany Bundesliga I",
    "3405541143": "Italy Serie A",
    "4212821298": "Spain La Liga",
}
TERMS_REVIEW_PATH = Path(__file__).resolve().parents[1] / "docs/legal/5dollar-terms-review-2026-11-12.md"
TERMS_REVIEW_URI = "https://github.com/Nexora-Apparel/veltrix-football/blob/main/docs/legal/5dollar-terms-review-2026-11-12.md"
TERMS_URL = "https://5dollarfootballapi.com/terms"
ATTRIBUTION = "Football data by 5DollarFootballAPI"
ATTRIBUTION_URL = "https://5dollarfootballapi.com"


class ProbeFailure(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _hash(report: dict) -> str:
    body = dict(report)
    body.pop("report_sha256", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _request(path: str, api_key: str):
    request = Request(
        BASE + path,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "VELTRIX-Phase2-History-DryRun/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=25) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())
    except (URLError, TimeoutError, OSError):
        raise ProbeFailure("NETWORK_ERROR") from None


def _parse_json(raw: bytes, status: int) -> dict:
    if status != 200:
        raise ProbeFailure(f"HTTP_{status}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeFailure("INVALID_JSON") from None
    if not isinstance(value, dict) or value.get("success") not in (1, True):
        raise ProbeFailure("UNSUCCESSFUL_RESPONSE")
    return value


def _country_pack(status_data: dict):
    candidates = (
        status_data.get("country_pack_code"),
        status_data.get("community_country_code"),
        status_data.get("country_code"),
    )
    community = status_data.get("community")
    if isinstance(community, dict):
        candidates = candidates + (community.get("country_code"), community.get("country_pack_code"))
    for item in candidates:
        if isinstance(item, str) and item.strip():
            return item.strip()[:40]
    return None


def _safe_headers(headers: dict) -> dict:
    allowed = ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After")
    result = {}
    for name in allowed:
        value = next((v for k, v in headers.items() if str(k).casefold() == name.casefold()), None)
        if value is not None:
            result[name.lower()] = str(value)[:100]
    return result


def _source_approval(now: datetime) -> SourceApproval:
    if not TERMS_REVIEW_PATH.is_file():
        raise ProbeFailure("TERMS_REVIEW_EVIDENCE_MISSING")
    evidence_hash = hashlib.sha256(TERMS_REVIEW_PATH.read_bytes()).hexdigest()
    reviewed = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)
    return SourceApproval(
        approval_id="approval-5dollar-community-fixture-result-2026-11",
        provider=PROVIDER,
        source_id=SOURCE_ID,
        competition_scope=",".join(sorted(EXPECTED_COMPETITIONS)),
        data_type="fixture_result",
        status=ApprovalStatus.APPROVED,
        permitted_uses=frozenset({
            DataUsePurpose.COLLECTION,
            DataUsePurpose.STORAGE,
            DataUsePurpose.HISTORICAL_IMPORT,
            DataUsePurpose.MODEL_TRAINING,
            DataUsePurpose.CACHE,
            DataUsePurpose.PUBLIC_DISPLAY,
        }),
        commercial_use_allowed=True,
        terms_url=TERMS_URL,
        terms_version="October 2026",
        evidence_uri=TERMS_REVIEW_URI,
        evidence_sha256=evidence_hash,
        rights_basis="TERMS",
        reviewed_at_utc=reviewed,
        reviewer_id="VELTRIX_PHASE2_REVIEW",
        valid_from_utc=reviewed,
        attribution_required=True,
        attribution_text=ATTRIBUTION,
        attribution_url=ATTRIBUTION_URL,
        raw_redistribution_allowed=False,
    )


def run_probe(api_key: str, *, now: datetime | None = None, request_fn=_request, sleep=time.sleep) -> dict:
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    end = checked_at
    start = end - timedelta(days=365)
    request_count = 0
    last_headers = {}
    approval = _source_approval(checked_at)
    all_fixtures = []
    pages_by_comp = Counter()
    fixtures_by_comp = Counter()
    pagination_complete = True
    failure = None
    status_summary = {}
    competition_summary = []

    def call(path: str):
        nonlocal request_count, last_headers
        if request_count >= REQUEST_BUDGET:
            raise ProbeFailure("REQUEST_BUDGET_EXHAUSTED")
        if request_count:
            sleep(PACE_SECONDS)
        try:
            status, raw, headers = request_fn(path, api_key)
        finally:
            request_count += 1
        last_headers = _safe_headers(headers)
        payload = _parse_json(raw, status)
        return payload, headers, raw

    if not api_key.strip():
        failure = "MISSING_SECRET"
    else:
        try:
            status_payload, status_headers, status_raw = call("/status")
            status_data = status_payload.get("data")
            if not isinstance(status_data, dict):
                raise ProbeFailure("STATUS_SCHEMA_INVALID")
            limits = status_data.get("limits") if isinstance(status_data.get("limits"), dict) else {}
            status_summary = {
                "plan": str(status_data.get("plan") or "not_reported").casefold(),
                "rate_limit_hour": _integer(limits.get("rate_limit")),
                "burst_per_minute": _integer(limits.get("burst_per_minute")),
                "usage_today": (status_data.get("usage") or {}).get("today")
                    if isinstance(status_data.get("usage"), dict) else None,
                "country_pack_code": _country_pack(status_data),
                "quota_headers": _safe_headers(status_headers),
                "response_sha256": hashlib.sha256(status_raw).hexdigest(),
            }
            if status_summary["plan"] != "community":
                raise ProbeFailure("UNEXPECTED_PLAN")
            if status_summary["rate_limit_hour"] != 300 or status_summary["burst_per_minute"] != 20:
                raise ProbeFailure("ACCOUNT_QUOTA_PROFILE_MISMATCH")
            remaining = _integer(status_summary["quota_headers"].get("x-ratelimit-remaining"))
            if remaining is None or remaining < REQUEST_BUDGET + 2:
                raise ProbeFailure("INSUFFICIENT_REMAINING_QUOTA_FOR_BOUNDED_PROBE")

            leagues_payload, league_headers, leagues_raw = call("/leagues")
            league_rows = leagues_payload.get("data")
            if isinstance(league_rows, dict):
                league_rows = league_rows.get("leagues")
            if not isinstance(league_rows, list):
                raise ProbeFailure("LEAGUE_CATALOGUE_INVALID")
            league_pagination = leagues_payload.get("pagination")
            if not isinstance(league_pagination, dict) or not isinstance(league_pagination.get("has_more"), bool):
                raise ProbeFailure("LEAGUE_CATALOGUE_PAGINATION_INCOMPLETE")
            if league_pagination["has_more"]:
                raise ProbeFailure("LEAGUE_CATALOGUE_HAS_UNQUALIFIED_EXTRA_PAGES")
            observed = {}
            observed_countries = {}
            for row in league_rows:
                if isinstance(row, dict) and row.get("id") is not None:
                    competition_id = str(row["id"])
                    observed[competition_id] = str(row.get("name") or "unknown")
                    country = row.get("country")
                    if isinstance(country, dict):
                        country = country.get("name") or country.get("code")
                    observed_countries[competition_id] = str(country or "not_reported")
            if observed != EXPECTED_COMPETITIONS:
                raise ProbeFailure("ACCOUNT_COMPETITION_ALLOWLIST_CHANGED")
            core_countries = {"England", "France", "Germany", "Italy", "Spain"}
            extra_countries = sorted({
                country for country in observed_countries.values()
                if country not in core_countries and country != "not_reported"
            })
            status_summary["catalogue_sha256"] = hashlib.sha256(leagues_raw).hexdigest()
            status_summary["catalogue_count"] = len(observed)
            status_summary["competition_countries"] = observed_countries
            status_summary["country_pack_country_inferred"] = extra_countries
            status_summary["country_pack_inference_basis"] = (
                "country values outside the five named top-league countries; not a status-endpoint entitlement field"
            )
            status_summary["catalogue_quota_headers"] = _safe_headers(league_headers)

            start_epoch, end_epoch = int(start.timestamp()), int(end.timestamp())
            for competition_id, competition_name in sorted(EXPECTED_COMPETITIONS.items()):
                page = 1
                comp_fixtures = []
                comp_pages = 0
                while True:
                    params = {
                        "status": "finished",
                        "start_time": start_epoch,
                        "end_time": end_epoch,
                        "per_page": PER_PAGE,
                        "page": page,
                    }
                    path = f"/leagues/{competition_id}/fixtures?{urlencode(params)}"
                    payload, headers, raw = call(path)
                    parsed = parse_fixture_page(
                        raw,
                        headers=headers,
                        retrieved_at_utc=checked_at,
                        rights_approval_id=approval.approval_id,
                    )
                    if parsed.page != page or parsed.per_page != PER_PAGE:
                        raise ProbeFailure("FIXTURE_PAGINATION_RESPONSE_MISMATCH")
                    if any(row.provider_competition_id != competition_id for row in parsed.fixtures):
                        raise ProbeFailure("FIXTURE_COMPETITION_SCOPE_MISMATCH")
                    if any(row.kickoff_at_utc < start or row.kickoff_at_utc > end for row in parsed.fixtures):
                        raise ProbeFailure("FIXTURE_OUTSIDE_REQUESTED_DATE_WINDOW")
                    comp_fixtures.extend(parsed.fixtures)
                    all_fixtures.extend(parsed.fixtures)
                    comp_pages += 1
                    if not parsed.has_more:
                        break
                    if not parsed.fixtures:
                        raise ProbeFailure("EMPTY_PAGE_WITH_MORE_RESULTS")
                    page += 1
                pages_by_comp[competition_id] = comp_pages
                fixtures_by_comp[competition_id] = len(comp_fixtures)
                comp_statuses = Counter(row.status.value for row in comp_fixtures)
                comp_summary = {
                    "competition_id": competition_id,
                    "competition": competition_name,
                    "pages": comp_pages,
                    "fixtures": len(comp_fixtures),
                    "finished_with_valid_scores": comp_statuses.get("FINISHED", 0),
                    "unsettled_or_invalid": len(comp_fixtures) - comp_statuses.get("FINISHED", 0),
                    "first_kickoff_utc": min((row.kickoff_at_utc for row in comp_fixtures), default=None).isoformat()
                        if comp_fixtures else None,
                    "last_kickoff_utc": max((row.kickoff_at_utc for row in comp_fixtures), default=None).isoformat()
                        if comp_fixtures else None,
                    "season_keys": sorted({row.season_key for row in comp_fixtures if row.season_key}),
                    "response_quota_remaining": _integer(last_headers.get("x-ratelimit-remaining")),
                }
                competition_summary.append(comp_summary)
                if not comp_fixtures:
                    raise ProbeFailure(f"NO_HISTORICAL_FIXTURES:{competition_id}")
        except ProbeFailure as exc:
            failure = exc.code
            pagination_complete = False
        except FixturePageError as exc:
            failure = str(exc)
            pagination_complete = False

    assessment = assess_history_batch(
        all_fixtures,
        approval,
        evaluated_at_utc=checked_at,
        request_count=request_count,
        request_budget=REQUEST_BUDGET,
    )
    duplicates = assessment.report.duplicate_provider_fixture_ids
    invalid_rows = assessment.report.rejected_count + assessment.report.quarantined_count
    qualified = (
        failure is None
        and pagination_complete
        and len(competition_summary) == len(EXPECTED_COMPETITIONS)
        and len(all_fixtures) > 0
        and invalid_rows == 0
        and not duplicates
        and all(item["fixtures"] > 0 for item in competition_summary)
    )
    report = {
        "schema_version": 1,
        "provider": PROVIDER,
        "mode": "read_only_365_day_historical_fixture_result_qualification",
        "checked_at_utc": checked_at.isoformat(),
        "window": {"start_utc": start.isoformat(), "end_utc": end.isoformat(), "days": 365},
        "account": status_summary,
        "source_rights": {
            "approval_id": approval.approval_id,
            "status": approval.status.value,
            "terms_version": approval.terms_version,
            "terms_url": approval.terms_url,
            "evidence_uri": approval.evidence_uri,
            "evidence_sha256": approval.evidence_sha256,
            "permitted_uses": sorted(item.value for item in approval.permitted_uses),
            "attribution_required": approval.attribution_required,
            "raw_redistribution_allowed": approval.raw_redistribution_allowed,
        },
        "competition_results": competition_summary,
        "fixture_count": len(all_fixtures),
        "importable_count": assessment.report.importable_count,
        "rejected_count": assessment.report.rejected_count,
        "quarantined_count": assessment.report.quarantined_count,
        "duplicate_fixture_ids": list(duplicates),
        "pagination_complete": pagination_complete and len(competition_summary) == len(EXPECTED_COMPETITIONS),
        "page_count_by_competition": dict(pages_by_comp),
        "source_manifest_sha256": assessment.report.source_manifest_sha256,
        "availability_policy": {
            "basis": "provider_finished_status_conservative_4d",
            "point_in_time_certifiable": False,
            "usage": "settled target labels only; not certified pre-match feature availability",
        },
        "request_count": request_count,
        "request_budget": REQUEST_BUDGET,
        "last_quota_headers": last_headers,
        "status": "QUALIFIED" if qualified else "NOT_QUALIFIED",
        "failure_reason": failure,
        "side_effects": {
            "database_writes": 0,
            "imports": 0,
            "prediction_changes": 0,
            "telegram_messages": 0,
            "deployments": 0,
        },
    }
    report["report_sha256"] = _hash(report)
    return report


def _integer(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def validate_report(report: dict) -> None:
    if report.get("provider") != PROVIDER or report.get("mode") != "read_only_365_day_historical_fixture_result_qualification":
        raise ValueError("REPORT_SCOPE_INVALID")
    if report.get("request_count", 0) > REQUEST_BUDGET or report.get("request_budget") != REQUEST_BUDGET:
        raise ValueError("REPORT_REQUEST_BUDGET_INVALID")
    if report.get("side_effects") != {
        "database_writes": 0, "imports": 0, "prediction_changes": 0,
        "telegram_messages": 0, "deployments": 0,
    }:
        raise ValueError("REPORT_SIDE_EFFECTS_INVALID")
    if report.get("report_sha256") != _hash(report):
        raise ValueError("REPORT_SHA256_INVALID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/phase2/fivedollar-history-dry-run.json")
    args = parser.parse_args()
    report = run_probe(os.getenv("FIVEDOLLARFOOTBALL_API_KEY", ""))
    validate_report(report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "PHASE2_HISTORY_DRY_RUN: "
        f"status={report['status']} "
        f"fixtures={report['fixture_count']} "
        f"importable={report['importable_count']} "
        f"pages={sum(report['page_count_by_competition'].values())} "
        f"requests={report['request_count']}/{REQUEST_BUDGET} "
        f"failure={report['failure_reason']} "
        f"sha256={report['report_sha256']}"
    )
    return 0 if report["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
