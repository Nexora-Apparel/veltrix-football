"""Deterministic V2 certification-manifest builder.

This module computes evaluation metrics from immutable walk-forward and
prospective evidence. It does not fetch providers, write databases, sign
attestations, or publish reports. A record is marked CERTIFIED only when the
numeric gates pass and an injected rights verifier approves the exact record;
the publication verifier still requires a separate artifact attestation and
re-reads every evidence object by URI/hash.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import random
from statistics import mean
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from veltrix_v2.evaluation.publication_certification import (
    CERTIFICATION_MANIFEST_SCHEMA,
    MIN_PROSPECTIVE_DATES,
    MIN_PROSPECTIVE_SETTLED_SELECTIONS,
    MIN_TIMESTAMPED_ODDS_COVERAGE,
    MIN_WALK_FORWARD_MATCHES,
)
from veltrix_v2.evaluation.walk_forward import FixtureEvaluation, WalkForwardReport
from veltrix_v2.reporting.report_identity import verify_report_identity


UTC = timezone.utc
WAT = ZoneInfo("Africa/Lagos")
SUPPORTED_MARKETS = ("1X2", "BTTS", "TOTALS_2_5")
HASH_LENGTH = 64
MIN_RECENT_BENCHMARK_MATCHES = 100


def _parse_aware(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == HASH_LENGTH
        and all(char in "0123456789abcdef" for char in value.casefold())
    )


def _valid_uri(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"https", "s3", "gs"}
        and bool(parsed.netloc)
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def _fixture_set_sha256(fixture_ids: Iterable[str]) -> str:
    canonical = json.dumps(sorted(set(fixture_ids)), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _probability_metrics(probabilities: Mapping[str, float], outcome: str, market: str) -> tuple[float, float]:
    keys = {
        "1X2": ("home", "draw", "away"),
        "BTTS": ("yes", "no"),
        "TOTALS_2_5": ("over", "under"),
    }[market]
    allowed_outcomes = {
        "1X2": {"HOME", "DRAW", "AWAY"},
        "BTTS": {"YES", "NO"},
        "TOTALS_2_5": {"OVER", "UNDER"},
    }[market]
    if set(probabilities) != set(keys) or outcome not in allowed_outcomes:
        raise ValueError("CERTIFICATION_MARKET_VECTOR_INVALID")
    values = [float(probabilities[key]) for key in keys]
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("CERTIFICATION_MARKET_PROBABILITY_INVALID")
    if abs(sum(values) - 1.0) > 1e-8:
        raise ValueError("CERTIFICATION_MARKET_PROBABILITY_NOT_NORMALISED")
    actual_key = {
        "HOME": "home", "DRAW": "draw", "AWAY": "away",
        "YES": "yes", "NO": "no", "OVER": "over", "UNDER": "under",
    }[outcome]
    brier = (
        sum((probabilities[key] - (1.0 if key == actual_key else 0.0)) ** 2 for key in keys)
        if market == "1X2"
        else (probabilities[actual_key] - 1.0) ** 2
    )
    log_loss = -math.log(max(1e-15, float(probabilities[actual_key])))
    return float(brier), float(log_loss)


def _de_vig(odds: Mapping[str, Any]) -> dict[str, float] | None:
    keys = ("home", "draw", "away")
    if not isinstance(odds, Mapping) or set(odds) != set(keys):
        return None
    values = [odds[key] for key in keys]
    if any(not _finite(value) or float(value) <= 1.0 for value in values):
        return None
    implied = [1.0 / float(value) for value in values]
    total = sum(implied)
    if not math.isfinite(total) or total <= 0:
        return None
    return {key: value / total for key, value in zip(keys, implied)}


def _bookmaker_consensus(
    fixture: FixtureEvaluation,
    quotes: Iterable[Mapping[str, Any]],
) -> dict[str, float] | None:
    latest_by_bookmaker: dict[str, tuple[datetime, dict[str, float]]] = {}
    for quote in quotes:
        if not isinstance(quote, Mapping):
            continue
        if quote.get("fixture_id") != fixture.fixture_id:
            continue
        if quote.get("competition_id") != fixture.competition_id:
            continue
        source = str(quote.get("source_provider", quote.get("provider", ""))).strip().casefold()
        if source.replace(" ", "") not in {"theoddsapi", "theoddsapi.com"}:
            continue
        if quote.get("quote_timestamp_basis") != "PROVIDER_OBSERVED_AT":
            continue
        quote_at = _parse_aware(quote.get("quote_at"))
        kickoff = _parse_aware(fixture.kickoff_at)
        cutoff = _parse_aware(fixture.cutoff_at)
        if quote_at is None or kickoff is None or cutoff is None or quote_at >= kickoff or quote_at > cutoff:
            continue
        if not _valid_hash(quote.get("evidence_sha256")):
            continue
        bookmaker = quote.get("bookmaker")
        if not isinstance(bookmaker, str) or not bookmaker.strip():
            continue
        probabilities = _de_vig(quote.get("odds"))
        if probabilities is None:
            continue
        previous = latest_by_bookmaker.get(bookmaker)
        if previous is None or quote_at > previous[0]:
            latest_by_bookmaker[bookmaker] = (quote_at, probabilities)
    if not latest_by_bookmaker:
        return None
    return {
        key: mean(row[1][key] for row in latest_by_bookmaker.values())
        for key in ("home", "draw", "away")
    }


def _fixture_outcome(row: FixtureEvaluation, market: str) -> str:
    if market == "1X2":
        return row.actual_1x2
    if market == "BTTS":
        return "YES" if row.actual_home_goals > 0 and row.actual_away_goals > 0 else "NO"
    total = row.actual_home_goals + row.actual_away_goals
    return "OVER" if total >= 3 else "UNDER"


def _fixture_probabilities(row: FixtureEvaluation, market: str) -> dict[str, float]:
    if market == "1X2":
        return {
            "home": row.model_home_win,
            "draw": row.model_draw,
            "away": row.model_away_win,
        }
    if market == "BTTS":
        return {"yes": row.model_btts_yes, "no": 1.0 - row.model_btts_yes}
    return {"over": row.model_over_2_5, "under": 1.0 - row.model_over_2_5}


def _metrics(rows: Iterable[tuple[FixtureEvaluation, Mapping[str, float]]], market: str) -> tuple[float, float] | None:
    scored = []
    for fixture, probabilities in rows:
        brier, log_loss = _probability_metrics(probabilities, _fixture_outcome(fixture, market), market)
        scored.append((brier, log_loss))
    if not scored:
        return None
    return mean(row[0] for row in scored), mean(row[1] for row in scored)


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _roi_metrics(rows: list[Mapping[str, Any]], *, bootstrap_samples: int, seed: int) -> tuple[int, int, float, float, float, list[str]]:
    valid = []
    seen_ids = set()
    blockers = []
    for row in rows:
        if not isinstance(row, Mapping) or row.get("prospective") is not True or row.get("settled") is not True:
            continue
        selection_id = row.get("selection_id")
        kickoff = _parse_aware(row.get("kickoff_at"))
        stake = row.get("stake")
        net_profit = row.get("net_profit_after_fees_and_slippage")
        if (
            not isinstance(selection_id, str) or not selection_id.strip() or selection_id in seen_ids
            or kickoff is None or not _finite(stake) or float(stake) <= 0
            or not _finite(net_profit)
        ):
            blockers.append("PROSPECTIVE_SELECTION_ROW_INVALID")
            continue
        seen_ids.add(selection_id)
        quote_at = _parse_aware(row.get("quote_at"))
        cutoff = _parse_aware(row.get("prediction_cutoff_at"))
        quote_valid = (
            row.get("quote_timestamp_basis") == "PROVIDER_OBSERVED_AT"
            and str(row.get("quote_source", "")).strip().casefold().replace(" ", "") in {"theoddsapi", "theoddsapi.com"}
            and quote_at is not None
            and cutoff is not None
            and quote_at < kickoff
            and quote_at <= cutoff
            and _valid_hash(row.get("quote_evidence_sha256"))
        )
        valid.append({
            "selection_id": selection_id,
            "kickoff": kickoff,
            "stake": float(stake),
            "net_profit": float(net_profit),
            "quote_valid": quote_valid,
        })
    count = len(valid)
    dates = sorted({item["kickoff"].astimezone(WAT).date().isoformat() for item in valid})
    total_stake = sum(item["stake"] for item in valid)
    total_profit = sum(item["net_profit"] for item in valid)
    net_roi = total_profit / total_stake if total_stake > 0 else 0.0
    coverage = sum(1 for item in valid if item["quote_valid"]) / count if count else 0.0
    if len(dates) < 2 or bootstrap_samples < 100:
        roi_lower = 0.0
    else:
        by_date: dict[str, list[dict[str, float]]] = defaultdict(list)
        for item in valid:
            date_key = item["kickoff"].astimezone(WAT).date().isoformat()
            by_date[date_key].append({"stake": item["stake"], "profit": item["net_profit"]})
        rng = random.Random(seed)
        estimates = []
        for _ in range(bootstrap_samples):
            sampled_dates = [dates[rng.randrange(len(dates))] for _ in dates]
            stake = sum(row["stake"] for date_key in sampled_dates for row in by_date[date_key])
            profit = sum(row["profit"] for date_key in sampled_dates for row in by_date[date_key])
            if stake > 0:
                estimates.append(profit / stake)
        roi_lower = _percentile(estimates, 0.025)
    return count, len(dates), coverage, net_roi, roi_lower, blockers


def _evidence_blockers(evidence: Mapping[str, Any], *, market: str) -> list[str]:
    blockers = []
    for field in ("evidence_uri", "rights_evidence_uri"):
        if not _valid_uri(evidence.get(field)):
            blockers.append(f"{field.upper()}_INVALID")
    for field in (
        "evidence_sha256", "rights_evidence_sha256",
        "model_artifact_sha256", "feature_set_sha256",
    ):
        if not _valid_hash(evidence.get(field)):
            blockers.append(f"{field.upper()}_INVALID")
    if market == "1X2":
        if not _valid_uri(evidence.get("bookmaker_baseline_evidence_uri")):
            blockers.append("BOOKMAKER_EVIDENCE_URI_INVALID")
        if not _valid_hash(evidence.get("bookmaker_baseline_evidence_sha256")):
            blockers.append("BOOKMAKER_EVIDENCE_HASH_INVALID")
    if not isinstance(evidence.get("rights_approval_id"), str) or not evidence["rights_approval_id"].strip():
        blockers.append("RIGHTS_APPROVAL_ID_MISSING")
    if not isinstance(evidence.get("provider_id"), str) or not evidence["provider_id"].strip():
        blockers.append("PROVIDER_ID_MISSING")
    if not isinstance(evidence.get("provider_scope"), str) or not evidence["provider_scope"].strip():
        blockers.append("PROVIDER_SCOPE_MISSING")
    rights_time = _parse_aware(evidence.get("rights_evaluated_at"))
    if rights_time is None:
        blockers.append("RIGHTS_EVALUATED_AT_INVALID")
    if evidence.get("point_in_time_certifiable") is not True:
        blockers.append("POINT_IN_TIME_EVIDENCE_NOT_CERTIFIABLE")
    if evidence.get("revision_history_complete") is not True:
        blockers.append("REVISION_HISTORY_INCOMPLETE")
    if evidence.get("paper_ledger_chain_verified") is not True:
        blockers.append("PAPER_LEDGER_CHAIN_UNVERIFIED")
    if market == "1X2" and str(evidence.get("bookmaker_baseline_source", "")).strip() != "The Odds API":
        blockers.append("BOOKMAKER_BASELINE_SOURCE_NOT_APPROVED")
    return blockers


def _record_for_market(
    *,
    competition_id: str,
    market: str,
    model_build_id: str,
    walk_forward_rows: list[FixtureEvaluation],
    prospective_rows: list[Mapping[str, Any]],
    bookmaker_quotes: list[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    rights_verifier: Callable[[Mapping[str, Any]], bool] | None,
    recent_window_days: int,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    blockers = _evidence_blockers(evidence, market=market)
    market_selections = [
        row for row in prospective_rows
        if isinstance(row, Mapping)
        and row.get("competition_id") == competition_id
        and row.get("market") == market
        and row.get("model_build_id") == model_build_id
        and row.get("prospective") is True
        and row.get("settled") is True
    ]
    selection_count, distinct_dates, odds_coverage, net_roi, roi_lower, selection_blockers = _roi_metrics(
        market_selections, bootstrap_samples=bootstrap_samples, seed=seed
    )
    blockers.extend(selection_blockers)
    if len(walk_forward_rows) < MIN_WALK_FORWARD_MATCHES:
        blockers.append("WALK_FORWARD_SAMPLE_BELOW_1000")
    if selection_count < MIN_PROSPECTIVE_SETTLED_SELECTIONS:
        blockers.append("PROSPECTIVE_SETTLED_SELECTIONS_BELOW_300")
    if distinct_dates < MIN_PROSPECTIVE_DATES:
        blockers.append("PROSPECTIVE_DATES_BELOW_90")
    if odds_coverage < MIN_TIMESTAMPED_ODDS_COVERAGE:
        blockers.append("TIMESTAMPED_ODDS_COVERAGE_BELOW_98_PERCENT")
    if net_roi <= 0:
        blockers.append("NET_ROI_NOT_POSITIVE")
    if roi_lower <= 0:
        blockers.append("ROI_CI95_LOWER_NOT_POSITIVE")
    if not market_selections:
        blockers.append("PROSPECTIVE_EVIDENCE_MISSING")

    scored_rows: list[tuple[FixtureEvaluation, Mapping[str, float]]] = []
    bookmaker_rows: list[tuple[FixtureEvaluation, Mapping[str, float]]] = []
    for fixture in walk_forward_rows:
        model_probabilities = _fixture_probabilities(fixture, market)
        if market == "1X2":
            bookmaker_probabilities = _bookmaker_consensus(fixture, bookmaker_quotes)
            if bookmaker_probabilities is None:
                continue
            bookmaker_rows.append((fixture, bookmaker_probabilities))
        scored_rows.append((fixture, model_probabilities))

    if market == "1X2":
        # Compare the model and bookmaker on exactly the same fixture set.
        matched_ids = {fixture.fixture_id for fixture, _ in bookmaker_rows}
        scored_rows = [(fixture, probabilities) for fixture, probabilities in scored_rows if fixture.fixture_id in matched_ids]
        bookmaker_fixture_hash = _fixture_set_sha256(matched_ids)
        if matched_ids != {row.fixture_id for row in walk_forward_rows}:
            blockers.append("BOOKMAKER_FIXTURE_SET_MISMATCH")
        if len(scored_rows) < MIN_WALK_FORWARD_MATCHES:
            blockers.append("BOOKMAKER_MATCHED_SAMPLE_BELOW_1000")
        model_metrics = _metrics(scored_rows, market)
        bookmaker_metrics = _metrics(bookmaker_rows, market)
        if model_metrics is None or bookmaker_metrics is None:
            blockers.append("BOOKMAKER_METRICS_MISSING")
            brier = bookmaker_brier = log_loss = bookmaker_log_loss = 0.0
        else:
            brier, log_loss = model_metrics
            bookmaker_brier, bookmaker_log_loss = bookmaker_metrics
            if brier >= bookmaker_brier:
                blockers.append("MODEL_BRIER_NOT_BETTER_THAN_BOOKMAKER")
            if log_loss >= bookmaker_log_loss:
                blockers.append("MODEL_LOG_LOSS_NOT_BETTER_THAN_BOOKMAKER")
        if scored_rows:
            latest = max(row.kickoff_at for row, _ in scored_rows)
            recent_cutoff = latest - timedelta(days=recent_window_days)
            recent_scored = [(row, p) for row, p in scored_rows if row.kickoff_at >= recent_cutoff]
            recent_bookmaker = [(row, p) for row, p in bookmaker_rows if row.kickoff_at >= recent_cutoff]
        else:
            recent_scored, recent_bookmaker = [], []
        if len(recent_scored) < MIN_RECENT_BENCHMARK_MATCHES:
            blockers.append("RECENT_BOOKMAKER_SAMPLE_BELOW_100")
        recent_model_metrics = _metrics(recent_scored, market)
        recent_bookmaker_metrics = _metrics(recent_bookmaker, market)
        if recent_model_metrics is None or recent_bookmaker_metrics is None:
            blockers.append("RECENT_BOOKMAKER_METRICS_MISSING")
            recent_brier = recent_bookmaker_brier = recent_log_loss = recent_bookmaker_log_loss = 0.0
        else:
            recent_brier, recent_log_loss = recent_model_metrics
            recent_bookmaker_brier, recent_bookmaker_log_loss = recent_bookmaker_metrics
            if recent_brier >= recent_bookmaker_brier:
                blockers.append("RECENT_MODEL_BRIER_NOT_BETTER_THAN_BOOKMAKER")
            if recent_log_loss >= recent_bookmaker_log_loss:
                blockers.append("RECENT_MODEL_LOG_LOSS_NOT_BETTER_THAN_BOOKMAKER")
        evaluation_ids = {row.fixture_id for row, _ in scored_rows}
        recent_ids = {row.fixture_id for row, _ in recent_scored}
        bookmaker_ids = {row.fixture_id for row, _ in bookmaker_rows}
        recent_bookmaker_ids = {row.fixture_id for row, _ in recent_bookmaker}
        record_metrics = {
            "brier_score": brier,
            "bookmaker_brier_score": bookmaker_brier,
            "log_loss": log_loss,
            "bookmaker_log_loss": bookmaker_log_loss,
            "recent_brier_score": recent_brier,
            "recent_bookmaker_brier_score": recent_bookmaker_brier,
            "recent_log_loss": recent_log_loss,
            "recent_bookmaker_log_loss": recent_bookmaker_log_loss,
            "bookmaker_baseline_method": "DEVIGGED",
            "bookmaker_baseline_source": str(evidence.get("bookmaker_baseline_source", "The Odds API")),
            "bookmaker_fixture_set_sha256": _fixture_set_sha256(bookmaker_ids),
            "recent_fixture_set_sha256": _fixture_set_sha256(recent_ids),
            "recent_bookmaker_fixture_set_sha256": _fixture_set_sha256(recent_bookmaker_ids),
            "bookmaker_baseline_evidence_uri": evidence.get("bookmaker_baseline_evidence_uri"),
            "bookmaker_baseline_evidence_sha256": evidence.get("bookmaker_baseline_evidence_sha256"),
        }
    else:
        evaluation_ids = {row.fixture_id for row, _ in scored_rows}
        metrics = _metrics(scored_rows, market)
        if metrics is None:
            blockers.append("WALK_FORWARD_METRICS_MISSING")
            brier = log_loss = 0.0
        else:
            brier, log_loss = metrics
        record_metrics = {"brier_score": brier, "log_loss": log_loss}

    rights_time = _parse_aware(evidence.get("rights_evaluated_at"))
    record: dict[str, Any] = {
        "competition_id": competition_id,
        "market": market,
        "model_build_id": model_build_id,
        "walk_forward_method": "EXPANDING_CHRONOLOGICAL",
        "roi_basis": "NET_AFTER_FEES_AND_SLIPPAGE",
        "roi_ci95_method": "DATE_CLUSTERED_BOOTSTRAP",
        "walk_forward_matches": len(evaluation_ids),
        "prospective_settled_selections": selection_count,
        "distinct_dates": distinct_dates,
        "timestamped_odds_coverage": odds_coverage,
        "net_roi": net_roi,
        "roi_ci95_lower": roi_lower,
        "evaluation_fixture_set_sha256": _fixture_set_sha256(evaluation_ids),
        "model_artifact_sha256": evidence.get("model_artifact_sha256"),
        "feature_set_sha256": evidence.get("feature_set_sha256"),
        "point_in_time_certifiable": evidence.get("point_in_time_certifiable") is True,
        "revision_history_complete": evidence.get("revision_history_complete") is True,
        "prospective_evidence": bool(market_selections),
        "rights_approval_id": evidence.get("rights_approval_id"),
        "provider_id": evidence.get("provider_id"),
        "provider_scope": evidence.get("provider_scope"),
        "rights_evaluated_at": rights_time.isoformat().replace("+00:00", "Z") if rights_time else None,
        "evidence_uri": evidence.get("evidence_uri"),
        "evidence_sha256": evidence.get("evidence_sha256"),
        "rights_evidence_uri": evidence.get("rights_evidence_uri"),
        "rights_evidence_sha256": evidence.get("rights_evidence_sha256"),
        **record_metrics,
        "blockers": [],
        "status": "NOT_CERTIFIED",
    }
    if rights_verifier is None:
        blockers.append("RIGHTS_VERIFIER_MISSING")
    else:
        try:
            if rights_verifier(record) is not True:
                blockers.append("RIGHTS_VERIFICATION_FAILED")
        except Exception:
            blockers.append("RIGHTS_VERIFICATION_FAILED")
    record["blockers"] = sorted(set(blockers))
    if not record["blockers"]:
        record["status"] = "CERTIFIED"
    return record


def build_certification_manifest(
    *,
    report: Mapping[str, Any],
    walk_forward_report: WalkForwardReport,
    prospective_selections: Iterable[Mapping[str, Any]],
    bookmaker_quotes: Iterable[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    rights_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    generated_at_utc: datetime | None = None,
    recent_window_days: int = 90,
    bootstrap_samples: int = 2000,
    random_seed: int = 20261114,
) -> dict[str, Any]:
    """Build a candidate certification manifest; never signs or publishes it."""
    identity = verify_report_identity(report)
    if recent_window_days < 1 or bootstrap_samples < 100:
        raise ValueError("CERTIFICATION_BUILDER_CONFIGURATION_INVALID")
    generated_at = generated_at_utc or datetime.now(UTC)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("CERTIFICATION_BUILDER_TIMESTAMP_MUST_BE_AWARE")

    selections = list(prospective_selections)
    quotes = list(bookmaker_quotes)
    prediction_rows = report.get("predictions")
    if not isinstance(prediction_rows, list) or not prediction_rows:
        raise ValueError("CERTIFICATION_REPORT_PREDICTIONS_REQUIRED")

    model_builds: dict[tuple[str, str], set[str]] = defaultdict(set)
    pairs: set[tuple[str, str]] = set()
    for fixture in prediction_rows:
        if not isinstance(fixture, Mapping):
            raise ValueError("CERTIFICATION_REPORT_FIXTURE_INVALID")
        competition_id = fixture.get("competition_id")
        model_build_id = fixture.get("model_build_id")
        markets = fixture.get("certified_markets")
        if not isinstance(competition_id, str) or not competition_id.strip():
            raise ValueError("CERTIFICATION_REPORT_COMPETITION_ID_REQUIRED")
        if not isinstance(markets, list):
            raise ValueError("CERTIFICATION_REPORT_MARKETS_REQUIRED")
        for market in markets:
            if market not in SUPPORTED_MARKETS:
                raise ValueError("CERTIFICATION_REPORT_MARKET_UNSUPPORTED")
            pairs.add((competition_id, market))
            if isinstance(model_build_id, str) and model_build_id.strip():
                model_builds[(competition_id, market)].add(model_build_id)

    by_competition: dict[str, list[FixtureEvaluation]] = defaultdict(list)
    for fixture in walk_forward_report.fixtures:
        if isinstance(fixture, FixtureEvaluation):
            by_competition[fixture.competition_id].append(fixture)

    records = []
    for competition_id, market in sorted(pairs):
        builds = model_builds.get((competition_id, market), set())
        model_build_id = next(iter(builds)) if len(builds) == 1 else ""
        blockers = []
        if len(builds) != 1:
            blockers.append("MODEL_BUILD_ID_MISSING_OR_INCONSISTENT")
        rows = by_competition.get(competition_id, [])
        if (
            not model_build_id
            or walk_forward_report.model_build_id != model_build_id
            or any(row.model_build_id != model_build_id for row in rows)
        ):
            rows = []
            blockers.append("WALK_FORWARD_MODEL_BUILD_ID_MISMATCH")
        record = _record_for_market(
            competition_id=competition_id,
            market=market,
            model_build_id=model_build_id,
            walk_forward_rows=rows,
            prospective_rows=selections,
            bookmaker_quotes=quotes,
            evidence=evidence,
            rights_verifier=rights_verifier,
            recent_window_days=recent_window_days,
            bootstrap_samples=bootstrap_samples,
            seed=random_seed,
        )
        if blockers:
            record["blockers"] = sorted(set(record["blockers"] + blockers))
            record["status"] = "NOT_CERTIFIED"
        records.append(record)

    if not records:
        raise ValueError("CERTIFICATION_REPORT_HAS_NO_MARKET_PAIRS")
    status = "CERTIFIED" if all(record["status"] == "CERTIFIED" for record in records) else "NOT_CERTIFIED"
    return {
        "manifest_schema": CERTIFICATION_MANIFEST_SCHEMA,
        "report_id": identity.report_id,
        "report_sha256": identity.report_sha256,
        "generated_at_utc": generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "certifications": records,
    }
