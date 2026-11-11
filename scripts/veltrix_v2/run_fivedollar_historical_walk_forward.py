#!/usr/bin/env python3
"""Run a bounded 5Dollar rolling-window multi-market diagnostic walk-forward.

The provider's raw match records remain in memory and are never written to the
artifact. The output contains aggregate derived metrics and source hashes only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from veltrix_v2.evaluation.calibration import (
    HeldOutFold1X2, diagnose_1x2_calibration,
)
from veltrix_v2.evaluation.binary_calibration import (
    HeldOutBinaryFold, diagnose_binary_calibration,
)
from veltrix_v2.evaluation.multi_competition_walk_forward import (
    run_multi_competition_walk_forward,
)
from veltrix_v2.ingestion.fivedollar_history import load_fivedollar_finished_matches

BASE = "https://api.5dollarfootballapi.com/v1"
TOP_LEAGUE_RULES = (
    ("england", "premier league"),
    ("france", "ligue 1"),
    ("germany", "bundesliga"),
    ("italy", "serie a"),
    ("spain", "la liga"),
)


class RequestBudget:
    def __init__(self, maximum: int, api_key: str):
        self.maximum = maximum
        self.api_key = api_key
        self.actual = 0
        self.remaining_header: int | None = None
        self._last_request_at: float | None = None

    def get(self, endpoint: str, params: dict[str, object]) -> dict:
        if self.actual >= self.maximum:
            raise RuntimeError("FIVEDOLLAR_REQUEST_BUDGET_EXHAUSTED")
        if self.remaining_header is not None and self.remaining_header <= 0:
            raise RuntimeError("FIVEDOLLAR_PROVIDER_QUOTA_EXHAUSTED")
        if self._last_request_at is not None:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < 3.2:
                time.sleep(3.2 - elapsed)
        self._last_request_at = time.monotonic()
        query = urlencode({key: value for key, value in params.items() if value is not None})
        url = f"{BASE}/{endpoint.lstrip('/')}" + (f"?{query}" if query else "")
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "VELTRIX-FOOTBALL/2.0-historical-evaluation",
            },
            method="GET",
        )
        self.actual += 1
        try:
            with urlopen(request, timeout=25) as response:
                body = response.read()
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining and str(remaining).isdigit():
                    self.remaining_header = int(remaining)
        except HTTPError as error:
            if error.code == 429:
                raise RuntimeError("FIVEDOLLAR_RATE_LIMITED") from None
            if error.code == 403:
                raise RuntimeError("FIVEDOLLAR_PLAN_OR_PERMISSION_DENIED") from None
            if error.code == 401:
                raise RuntimeError("FIVEDOLLAR_AUTHENTICATION_FAILED") from None
            raise RuntimeError(f"FIVEDOLLAR_HTTP_{error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("FIVEDOLLAR_NETWORK_ERROR") from None
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("FIVEDOLLAR_INVALID_JSON") from None
        if not isinstance(payload, dict) or payload.get("success") != 1:
            raise RuntimeError("FIVEDOLLAR_RESPONSE_UNSUCCESSFUL")
        return payload



def _history_limit_for_plan(plan: object) -> int:
    if not isinstance(plan, str):
        raise RuntimeError("FIVEDOLLAR_ACCOUNT_PLAN_MISSING")
    normalized = plan.strip().casefold()
    if normalized == "free":
        return 90
    if normalized in {"community", "education", "pro", "ultra", "business"}:
        return 365
    raise RuntimeError("FIVEDOLLAR_ACCOUNT_PLAN_UNRECOGNIZED")


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip())


def _is_target_league(name: str) -> bool:
    normalized = _norm(name)
    if any(country in normalized for country in ("argentina", "brazil", "nigeria")):
        return True
    return any(country in normalized and league in normalized for country, league in TOP_LEAGUE_RULES)


def _select_leagues(budget: RequestBudget) -> tuple[list[dict], bool]:
    selected: list[dict] = []
    page = 1
    complete = False
    while page <= 5:
        payload = budget.get("leagues", {"page": page, "per_page": 100})
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("FIVEDOLLAR_LEAGUE_CATALOGUE_INVALID")
        for row in rows:
            if not isinstance(row, dict):
                continue
            league_id = row.get("id")
            name = row.get("name")
            if not isinstance(name, str) or not isinstance(league_id, (int, str)):
                continue
            if _is_target_league(name):
                selected.append({"id": str(league_id), "name": name})
        pagination = payload.get("pagination") or {}
        if not isinstance(pagination, dict):
            raise RuntimeError("FIVEDOLLAR_CATALOGUE_PAGINATION_INVALID")
        if pagination.get("has_more") is not True:
            complete = True
            break
        page += 1
    # Keep one canonical top-flight record per named league. Community country
    # packs may expose both top flight and second division; retain both.
    unique = {(row["id"], row["name"]): row for row in selected}
    selected = sorted(unique.values(), key=lambda row: (row["name"].casefold(), row["id"]))
    if not complete:
        raise RuntimeError("FIVEDOLLAR_CATALOGUE_PAGINATION_INCOMPLETE")
    top_found = {
        (country, league)
        for row in selected
        for country, league in TOP_LEAGUE_RULES
        if country in _norm(row["name"]) and league in _norm(row["name"])
    }
    if len(top_found) < 5:
        raise RuntimeError("FIVEDOLLAR_TOP_FIVE_COMPETITION_SCOPE_INCOMPLETE")
    if len(selected) > 8:
        raise RuntimeError("FIVEDOLLAR_TARGET_COMPETITION_SCOPE_EXCEEDS_BUDGET")
    return selected, complete


def _fetch_finished_rows(
    budget: RequestBudget,
    leagues: list[dict],
    *,
    start: datetime,
    end: datetime,
    max_pages: int,
) -> tuple[list[dict], dict[str, dict], bool]:
    all_rows: list[dict] = []
    by_competition: dict[str, dict] = {}
    complete = True
    for league in leagues:
        league_id = league["id"]
        page = 1
        pages = 0
        source_rows = 0
        pagination_complete = False
        while pages < max_pages:
            payload = budget.get(
                f"leagues/{league_id}/fixtures",
                {
                    "start_time": int(start.timestamp()),
                    "end_time": int(end.timestamp()),
                    "status": "finished",
                    "page": page,
                    "per_page": 100,
                },
            )
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise RuntimeError("FIVEDOLLAR_FIXTURE_PAGE_INVALID")
            all_rows.extend(row for row in rows if isinstance(row, dict))
            source_rows += len(rows)
            pages += 1
            pagination = payload.get("pagination") or {}
            if not isinstance(pagination, dict):
                raise RuntimeError("FIVEDOLLAR_FIXTURE_PAGINATION_INVALID")
            if pagination.get("has_more") is not True:
                pagination_complete = True
                break
            page += 1
        by_competition[f"5dollar:{league_id}"] = {
            "competition_name": league["name"],
            "pages_fetched": pages,
            "source_rows": source_rows,
            "pagination_complete": pagination_complete,
        }
        complete = complete and pagination_complete
    return all_rows, by_competition, complete


def _choose_schedule(matches, minimum_train: int = 40):
    scopes = sorted({(row.competition_key, row.season) for row in matches})
    min_kickoff = min(row.kickoff_utc for row in matches)
    max_kickoff = max(row.kickoff_utc for row in matches)
    best = None
    for warmup_days in (45, 60, 75, 90, 105, 120):
        first_start = min_kickoff + timedelta(days=warmup_days)
        for window_days in (7, 10, 14, 21, 30, 45, 60, 75, 90):
            n_splits = min(9, int((max_kickoff - first_start).total_seconds() // (window_days * 86400)))
            if n_splits < 3:
                continue
            test_total = 0
            valid = True
            for competition_key, season in scopes:
                scope = [row for row in matches if row.competition_key == competition_key and row.season == season]
                for fold_index in range(n_splits):
                    start = first_start + timedelta(days=fold_index * window_days)
                    end = start + timedelta(days=window_days)
                    train_count = sum(
                        row.kickoff_utc < start and row.available_at_utc <= start
                        for row in scope
                    )
                    test_count = sum(start <= row.kickoff_utc < end for row in scope)
                    if train_count < minimum_train or test_count == 0:
                        valid = False
                        break
                    test_total += test_count
                if not valid:
                    break
            if valid:
                candidate = (test_total, n_splits, -window_days, first_start, window_days)
                if best is None or candidate[:3] > best[:3]:
                    best = candidate
    if best is None:
        raise RuntimeError("NO_VALID_CHRONOLOGICAL_FOLD_SCHEDULE")
    return best[3], timedelta(days=best[4]), best[1], best[0]


def _score(report):
    if report is None:
        return None
    return {
        "sample_size": report.sample_size,
        "multiclass_brier": report.multiclass_brier,
        "log_loss": report.log_loss,
        "ranked_probability_score": report.ranked_probability_score,
    }


def _wilson(successes: int, total: int) -> tuple[float, float] | None:
    if total <= 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _one_x_two_accuracy(evaluation):
    forecasts = [
        forecast
        for scope in evaluation.scope_reports
        for fold in scope.folds
        for forecast in fold.forecasts_1x2
    ]
    outcomes = {
        outcome.fixture_id: outcome.outcome
        for scope in evaluation.scope_reports
        for fold in scope.folds
        for outcome in fold.outcomes_1x2
    }
    hits = 0
    for forecast in forecasts:
        predicted = max(
            (("HOME", forecast.p_home), ("DRAW", forecast.p_draw), ("AWAY", forecast.p_away)),
            key=lambda item: item[1],
        )[0]
        hits += int(predicted == outcomes[forecast.fixture_id])
    interval = _wilson(hits, len(forecasts))
    return {
        "sample_size": len(forecasts),
        "correct": hits,
        "accuracy": hits / len(forecasts) if forecasts else None,
        "accuracy_target_80pct_met": (hits / len(forecasts) >= 0.80) if forecasts else False,
        "accuracy_ci95": list(interval) if interval is not None else None,
    }


def _binary_score(report):
    if report is None:
        return None
    return {
        "sample_size": report.sample_size,
        "eligible_fixture_count": report.eligible_fixture_count,
        "forecast_count": report.forecast_count,
        "abstention_count": report.abstention_count,
        "coverage": report.coverage,
        "hit_rate": report.hit_rate,
        "hit_rate_ci95": [report.hit_rate_ci95_lower, report.hit_rate_ci95_upper],
        "brier_score": report.brier_score,
        "log_loss": report.log_loss,
    }


def run(args) -> dict:
    key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FIVEDOLLAR_API_KEY_MISSING")
    retrieved = datetime.now(timezone.utc).replace(microsecond=0)
    budget = RequestBudget(args.max_requests, key)
    status_payload = budget.get("status", {})
    status_data = status_payload.get("data")
    if not isinstance(status_data, dict):
        raise RuntimeError("FIVEDOLLAR_ACCOUNT_STATUS_INVALID")
    provider_plan = status_data.get("plan")
    plan_history_limit_days = _history_limit_for_plan(provider_plan)
    base_plan = {
        "provider_plan": provider_plan,
        "plan_history_limit_days": plan_history_limit_days,
        "requested_history_days": args.days,
        "requests_used": budget.actual,
        "provider_requests_remaining_header": budget.remaining_header,
    }
    if args.days > plan_history_limit_days:
        return {
            "report_version": 1,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "5DollarFootballAPI",
            **base_plan,
            "status": "BLOCKED_PLAN_HISTORY_LIMIT",
            "reason": f"Account plan {provider_plan} allows at most {plan_history_limit_days} history days.",
            "raw_rows_in_report": False,
            "raw_rows_persisted": False,
            "prospective_validation": "NOT_STARTED",
            "bookmaker_benchmark": "NOT_EVALUATED",
            "roi_certification": "NOT_EVALUATED",
            "telegram_publication": "NOT_AUTHORIZED",
        }
    start = retrieved - timedelta(days=args.days)
    leagues, catalogue_complete = _select_leagues(budget)
    rows, competition_summary, data_complete = _fetch_finished_rows(
        budget, leagues, start=start, end=retrieved, max_pages=args.max_pages,
    )
    history = load_fivedollar_finished_matches(rows, retrieved_at_utc=retrieved)
    manifest = history.manifest
    history_span = (
        datetime.fromisoformat(manifest.last_kickoff_utc)
        - datetime.fromisoformat(manifest.first_kickoff_utc)
    ).days
    base = {
        "report_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "5DollarFootballAPI",
        "source_response_sha256": manifest.source_response_sha256,
        "retrieved_at_utc": manifest.retrieved_at_utc,
        **base_plan,
        "observed_history_span_days": history_span,
        "raw_rows_in_report": False,
        "raw_rows_persisted": False,
        "source_rows": len(rows),
        "accepted_matches": len(history.matches),
        "competition_count": len(leagues),
        "competitions": [
            {"competition_key": key, **value}
            for key, value in sorted(competition_summary.items())
        ],
        "catalogue_complete": catalogue_complete,
        "fixture_pagination_complete": data_complete,
        "skipped_not_finished": manifest.skipped_not_finished,
        "skipped_recent_embargo": manifest.skipped_recent_embargo,
        "invalid_rows": manifest.invalid_rows,
        "duplicate_fixture_ids": manifest.duplicate_fixture_ids,
        "availability_basis": manifest.availability_basis,
        "point_in_time_certifiable": False,
        "model_training_approved": manifest.model_training_approved,
        "attribution_required": manifest.attribution_required,
        "raw_redistribution_allowed": manifest.raw_redistribution_allowed,
        "requests_used": budget.actual,
        "provider_requests_remaining_header": budget.remaining_header,
        "market_results": None,
        "prospective_validation": "NOT_STARTED",
        "bookmaker_benchmark": "NOT_EVALUATED",
        "roi_certification": "NOT_EVALUATED",
        "telegram_publication": "NOT_AUTHORIZED",
    }
    if history_span < args.min_history_days:
        return {
            **base,
            "status": "BLOCKED_INSUFFICIENT_HISTORY",
            "reason": f"Observed history {history_span} days; requires {args.min_history_days}. Activate Community Access.",
        }
    if not catalogue_complete or not data_complete:
        return {
            **base,
            "status": "BLOCKED_INCOMPLETE_PROVIDER_PAGINATION",
            "reason": "Not all target competition pages were retrieved within the bounded request budget.",
        }
    if manifest.invalid_rows or manifest.duplicate_fixture_ids:
        return {
            **base,
            "status": "REVIEW_REQUIRED_DATA_QUALITY",
            "reason": "Invalid or duplicate source rows detected; no model evaluation run.",
        }
    if len(history.matches) < args.min_training_rows:
        return {
            **base,
            "status": "BLOCKED_INSUFFICIENT_MATCH_ROWS",
            "reason": f"Accepted rows {len(history.matches)}; requires {args.min_training_rows}.",
        }

    first_start, test_window, n_splits, scheduled_test_rows = _choose_schedule(history.matches)
    scopes = sorted({(row.competition_key, row.season) for row in history.matches})
    evaluation = run_multi_competition_walk_forward(
        history.matches,
        competition_seasons=scopes,
        first_test_start_utc=first_start,
        test_window=test_window,
        n_splits=n_splits,
        embargo=timedelta(0),
        minimum_training_matches=40,
        minimum_team_matches=1,
        max_iterations=args.max_iterations,
        recency_half_life_days=180.0,
        ridge=0.05,
        rho=0.0,
        total_line=2.5,
        model_version=f"veltrix-v2-5dollar-rolling{args.days}d-0.2",
    )
    calibration_folds = []
    for scope_index, scope_report in enumerate(evaluation.scope_reports, start=1):
        for fold in scope_report.folds:
            calibration_folds.append(HeldOutFold1X2(
                fold_number=scope_index * 100 + fold.fold_number,
                test_fixture_count=fold.test_fixture_count,
                forecasts=fold.forecasts_1x2,
                outcomes=fold.outcomes_1x2,
            ))
    calibration = (
        diagnose_1x2_calibration(calibration_folds, bin_count=10)
        if any(fold.forecasts for fold in calibration_folds) else None
    )

    btts_calibration_folds = []
    totals_calibration_folds = []
    for scope_index, scope_report in enumerate(evaluation.scope_reports, start=1):
        for fold in scope_report.folds:
            fold_number = scope_index * 100 + fold.fold_number
            btts_calibration_folds.append(HeldOutBinaryFold(
                fold_number=fold_number,
                market="BTTS",
                test_fixture_count=fold.test_fixture_count,
                forecasts=fold.btts_forecasts,
                outcomes=fold.btts_outcomes,
            ))
            totals_calibration_folds.append(HeldOutBinaryFold(
                fold_number=fold_number,
                market="TOTALS",
                test_fixture_count=fold.test_fixture_count,
                forecasts=fold.totals_forecasts,
                outcomes=fold.totals_outcomes,
            ))
    btts_calibration = (
        diagnose_binary_calibration(btts_calibration_folds, bin_count=10)
        if any(fold.forecasts for fold in btts_calibration_folds) else None
    )
    totals_calibration = (
        diagnose_binary_calibration(totals_calibration_folds, bin_count=10)
        if any(fold.forecasts for fold in totals_calibration_folds) else None
    )

    def binary_calibration_summary(report):
        if report is None:
            return {"status": "NOT_AVAILABLE_NO_HELD_OUT_FORECASTS"}
        return {
            "status": "DIAGNOSTICS_ONLY_NOT_CALIBRATED",
            "market": report.market,
            "fold_count": report.fold_count,
            "test_fixture_count": report.test_fixture_count,
            "forecast_count": report.forecast_count,
            "abstentions": report.abstentions,
            "coverage": report.coverage,
            "brier_score": report.calibration.brier_score,
            "expected_calibration_error": report.calibration.expected_calibration_error,
            "maximum_calibration_error": report.calibration.maximum_calibration_error,
            "reliability_bins": [
                {
                    "lower_bound": row.lower_bound,
                    "upper_bound": row.upper_bound,
                    "sample_count": row.sample_count,
                    "mean_predicted_probability": row.mean_predicted_probability,
                    "observed_frequency": row.observed_frequency,
                    "absolute_calibration_gap": row.absolute_calibration_gap,
                }
                for row in report.calibration.bins
            ],
        }

    market_results = {
        "1X2": {**(_score(evaluation.aggregate_1x2) or {}), **_one_x_two_accuracy(evaluation)},
        "BTTS": _binary_score(evaluation.aggregate_btts),
        "OU_2_5": _binary_score(evaluation.aggregate_totals),
    }
    sample_sizes = {
        "1X2": market_results["1X2"]["sample_size"] if market_results["1X2"] else 0,
        "BTTS": market_results["BTTS"]["sample_size"] if market_results["BTTS"] else 0,
        "OU_2_5": market_results["OU_2_5"]["sample_size"] if market_results["OU_2_5"] else 0,
    }
    sample_gate = all(value >= args.min_test_sample for value in sample_sizes.values())
    return {
        **base,
        "status": "HISTORICAL_SAMPLE_GATE_PASS" if sample_gate else "HISTORICAL_SAMPLE_GATE_FAIL",
        "model_version": f"veltrix-v2-5dollar-rolling{args.days}d-0.2",
        "fold_schedule": {
            "first_test_start_utc": first_start.isoformat(),
            "test_window_days": test_window.days,
            "fold_count_per_competition": n_splits,
            "scheduled_test_rows": scheduled_test_rows,
            "actual_test_fixtures": evaluation.total_test_fixtures,
        },
        "model_diagnostics": {
            "converged_folds": evaluation.converged_folds,
            "total_folds": evaluation.total_folds,
            "convergence_rate": evaluation.model_convergence_rate,
            "forecast_count": evaluation.total_forecasts,
            "abstentions": evaluation.total_abstentions,
            "coverage": evaluation.coverage_1x2.coverage,
        },
        "market_results": market_results,
        "market_sample_sizes": sample_sizes,
        "market_sample_gate": sample_gate,
        "calibration_1x2": (
            {"status": "NOT_AVAILABLE_NO_HELD_OUT_FORECASTS"}
            if calibration is None else {
                "status": "DIAGNOSTICS_ONLY_NOT_CALIBRATED",
                "fold_count": calibration.fold_count,
                "sample_size": calibration.forecast_count,
                "coverage": calibration.coverage,
                "classes": [
                    {
                        "class": row.outcome_class,
                        "sample_size": row.sample_size,
                        "brier_score": row.brier_score,
                        "ece": row.expected_calibration_error,
                        "max_calibration_error": row.maximum_calibration_error,
                        "non_empty_bins": len(row.bins),
                    }
                    for row in calibration.classes
                ],
            }
        ),
        "calibration_btts": binary_calibration_summary(btts_calibration),
        "calibration_totals_ou_2_5": binary_calibration_summary(totals_calibration),
        "prospective_validation": "NOT_STARTED",
        "bookmaker_benchmark": "NOT_EVALUATED",
        "roi_certification": "NOT_EVALUATED",
        "telegram_publication": "NOT_AUTHORIZED",
        "certification_note": "Historical research only. Four-day result-availability lag is a conservative proxy, not a source-published timestamp; prospective 90-day validation and 300 settled selections remain mandatory.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--max-requests", type=int, default=30)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--min-training-rows", type=int, default=200)
    parser.add_argument("--min-test-sample", type=int, default=1000)
    parser.add_argument("--max-iterations", type=int, default=6000)
    parser.add_argument("--output", default="v2_historical_walk_forward_summary.json")
    args = parser.parse_args()
    if not 60 <= args.days <= 365:
        parser.error("--days must be between 60 and 365")
    if not 1 <= args.max_requests <= 60:
        parser.error("--max-requests must be between 1 and 60")
    if not 1 <= args.max_pages <= 5:
        parser.error("--max-pages must be between 1 and 5")
    if not 60 <= args.min_history_days <= args.days:
        parser.error("--min-history-days must be between 60 and --days")
    if args.days > 90 and args.min_history_days < 300:
        parser.error("12-month history runs require --min-history-days of at least 300")
    if args.min_training_rows < 40 or args.min_test_sample < 1:
        parser.error("sample thresholds are invalid")
    output = Path(args.output)
    try:
        report = run(args)
    except (RuntimeError, ValueError) as exc:
        report = {
            "report_version": 1,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "5DollarFootballAPI",
            "status": "FAILED_CLOSED",
            "reason": str(exc)[:240],
            "raw_rows_in_report": False,
            "raw_rows_persisted": False,
            "prospective_validation": "NOT_STARTED",
            "bookmaker_benchmark": "NOT_EVALUATED",
            "roi_certification": "NOT_EVALUATED",
            "telegram_publication": "NOT_AUTHORIZED",
        }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"VELTRIX_V2_HISTORICAL: {report.get('status')}; "
        f"accepted={report.get('accepted_matches', 0)}; "
        f"history_days={report.get('observed_history_span_days', 0)}; "
        f"requests={report.get('requests_used', 0)}"
    )
    print(f"SUMMARY_FILE: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
