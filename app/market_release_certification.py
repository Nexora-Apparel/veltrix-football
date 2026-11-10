"""Fail-closed certification evaluator for market release and value-bet gates.

Consumes externally produced, immutable walk-forward and prospective evidence.
It performs no provider calls, persistence, publication, or Telegram delivery.
A passing report is evidence for human review, not automatic activation.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

MARKETS = {
    "1x2": ("home", "draw", "away"),
    "btts": ("no", "yes"),
    "over_2_5": ("no", "yes"),
}
WAT = ZoneInfo("Africa/Lagos")
MIN_WALK_FORWARD = 1000
MIN_PROSPECTIVE = 300
MIN_DATES = 90
MIN_ODDS_COVERAGE = 0.98
BOOTSTRAP_REPLICATES = 5000


class CertificationError(ValueError):
    pass


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CertificationError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CertificationError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CertificationError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _wat_date(value: str, field: str) -> date:
    return _timestamp(value, field).astimezone(WAT).date()


def _canonical_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _probabilities(value: object, classes: tuple[str, ...], field: str) -> dict:
    if not isinstance(value, dict) or set(value) != set(classes):
        raise CertificationError(f"{field}_classes_invalid")
    output = {}
    for key in classes:
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise CertificationError(f"{field}_value_invalid")
        number = float(number)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise CertificationError(f"{field}_value_invalid")
        output[key] = number
    if abs(sum(output.values()) - 1.0) > 1e-6:
        raise CertificationError(f"{field}_not_normalized")
    return output


def _metrics(rows: list[dict], market: str, classes: tuple[str, ...]) -> dict:
    model_brier = book_brier = model_loss = book_loss = 0.0
    for row in rows:
        actual = row["target"]
        model = row["probabilities"]
        book = row["bookmaker_probabilities"]
        model_loss -= math.log(max(model[actual], 1e-15))
        book_loss -= math.log(max(book[actual], 1e-15))
        for outcome in classes:
            observed = 1.0 if outcome == actual else 0.0
            model_brier += (model[outcome] - observed) ** 2
            book_brier += (book[outcome] - observed) ** 2
    n = len(rows)
    return {
        "fixture_count": n,
        "model": {"brier": model_brier / n, "log_loss": model_loss / n},
        "bookmaker": {"brier": book_brier / n, "log_loss": book_loss / n},
        "beats_bookmaker": {
            "brier": model_brier < book_brier,
            "log_loss": model_loss < book_loss,
        },
    }


def _bootstrap_roi(rows: list[dict], seed: int) -> dict:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["wat_date"], []).append(row)
    days = sorted(grouped)
    if len(days) < 2:
        return {"lower_95": None, "upper_95": None, "method": "wat_date_cluster_bootstrap",
                "replicates": 0, "status": "insufficient_dates"}
    rng = random.Random(seed)
    estimates = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled = [rng.choice(days) for _ in days]
        stake = profit = 0.0
        for day in sampled:
            for row in grouped[day]:
                stake += row["stake_units"]
                profit += row["profit_units"]
        estimates.append(profit / stake if stake else float("-inf"))
    estimates.sort()
    return {
        "lower_95": estimates[int(0.025 * (len(estimates) - 1))],
        "upper_95": estimates[int(0.975 * (len(estimates) - 1))],
        "method": "wat_date_cluster_percentile_bootstrap",
        "replicates": BOOTSTRAP_REPLICATES,
        "status": "computed",
    }


def _walk_forward(rows: object, market: str, evaluated: datetime) -> tuple[list[dict], dict]:
    classes = MARKETS[market]
    if not isinstance(rows, list):
        raise CertificationError(f"{market}_walk_forward_rows_invalid")
    normalized, seen = [], set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CertificationError(f"{market}_walk_forward_row_invalid:{index}")
        fixture = row.get("fixture_id")
        if not isinstance(fixture, str) or not fixture.strip() or fixture in seen:
            raise CertificationError(f"{market}_walk_forward_fixture_identity_invalid:{index}")
        seen.add(fixture)
        kickoff = _timestamp(row.get("kickoff_at"), f"{market}_kickoff_at")
        label_available = _timestamp(row.get("label_available_at"), f"{market}_label_available_at")
        if kickoff > evaluated or label_available > evaluated:
            raise CertificationError(f"{market}_walk_forward_record_after_evaluation:{fixture}")
        if label_available <= kickoff:
            raise CertificationError(f"{market}_label_not_available_after_kickoff:{fixture}")
        for digest_field in ("label_source_evidence_sha256",):
            digest = row.get(digest_field)
            if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise CertificationError(f"{market}_{digest_field}_invalid:{fixture}")
        target = row.get("target")
        if target not in classes:
            raise CertificationError(f"{market}_target_invalid:{fixture}")
        probabilities = _probabilities(row.get("probabilities"), classes, f"{market}_model")
        captured_at = row.get("bookmaker_odds_at")
        odds = row.get("bookmaker_odds_decimal")
        book_probs = None
        if captured_at is not None and odds is not None:
            captured = _timestamp(captured_at, f"{market}_bookmaker_odds_at")
            if captured > kickoff:
                raise CertificationError(f"{market}_odds_after_kickoff:{fixture}")
            odds_digest = row.get("odds_source_evidence_sha256")
            if not isinstance(odds_digest, str) or len(odds_digest) != 64 or any(ch not in "0123456789abcdef" for ch in odds_digest):
                raise CertificationError(f"{market}_odds_source_evidence_sha256_invalid:{fixture}")
            crosswalk_digest = row.get("crosswalk_source_evidence_sha256")
            if not isinstance(crosswalk_digest, str) or len(crosswalk_digest) != 64 or any(ch not in "0123456789abcdef" for ch in crosswalk_digest):
                raise CertificationError(f"{market}_crosswalk_source_evidence_sha256_invalid:{fixture}")
            if not isinstance(odds, dict) or set(odds) != set(classes):
                raise CertificationError(f"{market}_bookmaker_odds_classes_invalid:{fixture}")
            implied = {}
            for outcome in classes:
                price = odds[outcome]
                if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(float(price)) or float(price) <= 1.0:
                    raise CertificationError(f"{market}_bookmaker_odds_invalid:{fixture}:{outcome}")
                implied[outcome] = 1.0 / float(price)
            total = sum(implied.values())
            book_probs = {key: value / total for key, value in implied.items()}
        elif captured_at is not None or odds is not None:
            raise CertificationError(f"{market}_partial_odds_record:{fixture}")
        normalized.append({
            "fixture_id": fixture, "kickoff_at": kickoff.isoformat(),
            "wat_date": kickoff.astimezone(WAT).date().isoformat(),
            "target": target, "probabilities": probabilities,
            "bookmaker_probabilities": book_probs,
            "odds_source_evidence_sha256": row.get("odds_source_evidence_sha256"),
            "crosswalk_source_evidence_sha256": row.get("crosswalk_source_evidence_sha256"),
        })
    return normalized, {row["fixture_id"] for row in normalized}


def _prospective(rows: object, market: str, evaluated: datetime) -> list[dict]:
    classes = MARKETS[market]
    if not isinstance(rows, list):
        raise CertificationError(f"{market}_prospective_rows_invalid")
    output, seen = [], set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CertificationError(f"{market}_prospective_row_invalid:{index}")
        fixture = row.get("fixture_id")
        if not isinstance(fixture, str) or not fixture.strip() or fixture in seen:
            raise CertificationError(f"{market}_prospective_fixture_identity_invalid:{index}")
        seen.add(fixture)
        kickoff = _timestamp(row.get("kickoff_at"), f"{market}_prospective_kickoff")
        settled = _timestamp(row.get("settled_at"), f"{market}_prospective_settled_at")
        if settled <= kickoff:
            raise CertificationError(f"{market}_settlement_not_after_kickoff:{fixture}")
        if settled > evaluated or kickoff > evaluated:
            raise CertificationError(f"{market}_prospective_record_after_evaluation:{fixture}")
        for digest_field in ("settlement_source_evidence_sha256", "odds_source_evidence_sha256",
                             "crosswalk_source_evidence_sha256"):
            digest = row.get(digest_field)
            if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise CertificationError(f"{market}_{digest_field}_invalid:{fixture}")
        odds_at = _timestamp(row.get("odds_captured_at"), f"{market}_prospective_odds_captured_at")
        if odds_at > kickoff:
            raise CertificationError(f"{market}_prospective_odds_after_kickoff:{fixture}")
        selection = row.get("selection")
        actual = row.get("actual")
        if selection not in classes or actual not in classes:
            raise CertificationError(f"{market}_selection_or_actual_invalid:{fixture}")
        price, stake = row.get("odds_decimal"), row.get("stake_units")
        for name, number in (("odds_decimal", price), ("stake_units", stake)):
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(float(number)):
                raise CertificationError(f"{market}_{name}_invalid:{fixture}")
        if float(price) <= 1.0 or float(stake) <= 0.0:
            raise CertificationError(f"{market}_price_or_stake_out_of_range:{fixture}")
        stake = float(stake)
        profit = stake * (float(price) - 1.0) if selection == actual else -stake
        output.append({
            "fixture_id": fixture, "wat_date": kickoff.astimezone(WAT).date().isoformat(),
            "stake_units": stake, "profit_units": profit,
            "selection": selection, "actual": actual,
            "settlement_source_evidence_sha256": row["settlement_source_evidence_sha256"],
            "odds_source_evidence_sha256": row["odds_source_evidence_sha256"],
            "crosswalk_source_evidence_sha256": row["crosswalk_source_evidence_sha256"],
        })
    return output


def evaluate_market_release_certification(*, evidence: dict,
                                          evaluated_at: str,
                                          verified_source_evidence_sha256: list[str] | set[str] | tuple[str, ...] | None = None) -> dict:
    """Evaluate market thresholds without activating any production behavior.

    evidence[market] = {"walk_forward": [...], "prospective": [...]}.
    Odds are decimal prices captured before kickoff. ROI is derived from
    selections, actual outcomes, prices and stakes; supplied P/L is ignored.
    """
    evaluated = _timestamp(evaluated_at, "evaluated_at")
    if not isinstance(evidence, dict) or set(evidence) != set(MARKETS):
        raise CertificationError("evidence_must_contain_exactly_all_markets")
    verified_digests = set()
    if verified_source_evidence_sha256 is not None:
        if not isinstance(verified_source_evidence_sha256, (list, set, tuple)):
            raise CertificationError("verified_source_evidence_digest_set_invalid")
        for digest in verified_source_evidence_sha256:
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise CertificationError("verified_source_evidence_digest_invalid")
            verified_digests.add(digest)
    results = {}
    for market, classes in MARKETS.items():
        bundle = evidence[market]
        if not isinstance(bundle, dict) or set(bundle) != {"walk_forward", "prospective"}:
            raise CertificationError(f"{market}_evidence_bundle_invalid")
        wf, wf_fixture_ids = _walk_forward(bundle["walk_forward"], market, evaluated)
        prospective = _prospective(bundle["prospective"], market, evaluated)
        prospective_ids = {row["fixture_id"] for row in prospective}
        if wf_fixture_ids & prospective_ids:
            raise CertificationError(f"{market}_walk_forward_prospective_fixture_overlap")
        wf_dates = {row["wat_date"] for row in wf}
        odds_rows = [row for row in wf if row["bookmaker_probabilities"] is not None]
        coverage = len(odds_rows) / len(wf) if wf else 0.0
        benchmark = _metrics(odds_rows, market, classes) if odds_rows else None
        prospective_dates = {row["wat_date"] for row in prospective}
        total_stake = sum(row["stake_units"] for row in prospective)
        total_profit = sum(row["profit_units"] for row in prospective)
        roi = total_profit / total_stake if total_stake else None
        seed = int(_canonical_digest({"market": market, "fixtures": sorted(row["fixture_id"] for row in prospective)})[:8], 16)
        roi_ci = _bootstrap_roi(prospective, seed) if prospective else {
            "lower_95": None, "upper_95": None, "method": "wat_date_cluster_bootstrap",
            "replicates": 0, "status": "no_selections",
        }
        required_source_digests = {
            row["label_source_evidence_sha256"] for row in bundle["walk_forward"]
        }
        required_source_digests.update(
            row["odds_source_evidence_sha256"] for row in bundle["walk_forward"]
            if isinstance(row, dict) and row.get("odds_source_evidence_sha256") is not None
        )
        required_source_digests.update(
            row["settlement_source_evidence_sha256"] for row in prospective
        )
        required_source_digests.update(
            row["odds_source_evidence_sha256"] for row in prospective
        )
        required_source_digests.update(
            row["crosswalk_source_evidence_sha256"] for row in bundle["walk_forward"]
            if isinstance(row, dict) and row.get("crosswalk_source_evidence_sha256") is not None
        )
        required_source_digests.update(
            row["crosswalk_source_evidence_sha256"] for row in prospective
        )
        checks = {
            "source_evidence_receipts_verified": bool(required_source_digests)
                and required_source_digests.issubset(verified_digests),
            "walk_forward_fixtures": len(wf) >= MIN_WALK_FORWARD,
            "walk_forward_dates": len(wf_dates) >= MIN_DATES,
            "prospective_selections": len(prospective) >= MIN_PROSPECTIVE,
            "prospective_dates": len(prospective_dates) >= MIN_DATES,
            "timestamped_odds_coverage": coverage >= MIN_ODDS_COVERAGE,
            "positive_net_roi": roi is not None and roi > 0,
            "positive_lower_95_roi_bound": roi_ci["lower_95"] is not None and roi_ci["lower_95"] > 0,
        }
        if market == "1x2":
            checks["beats_bookmaker_brier"] = bool(benchmark and benchmark["beats_bookmaker"]["brier"])
            checks["beats_bookmaker_log_loss"] = bool(benchmark and benchmark["beats_bookmaker"]["log_loss"])
        results[market] = {
            "walk_forward_fixture_count": len(wf),
            "walk_forward_distinct_wat_dates": len(wf_dates),
            "timestamped_odds_rows": len(odds_rows),
            "timestamped_odds_coverage": coverage,
            "bookmaker_comparison": benchmark,
            "prospective_selection_count": len(prospective),
            "prospective_distinct_wat_dates": len(prospective_dates),
            "stake_units": total_stake,
            "net_profit_units": total_profit,
            "net_roi": roi,
            "net_roi_ci_95": roi_ci,
            "checks": checks,
            "certified": all(checks.values()),
            "evidence_sha256": _canonical_digest({
                "walk_forward": bundle["walk_forward"],
                "prospective": bundle["prospective"],
            }),
        }
    all_certified = all(item["certified"] for item in results.values())
    return {
        "schema_version": 1,
        "evaluation_type": "market_release_and_value_bet_certification",
        "evaluated_at": evaluated.isoformat(),
        "thresholds": {
            "walk_forward_fixtures_per_market": MIN_WALK_FORWARD,
            "prospective_selections_per_market": MIN_PROSPECTIVE,
            "distinct_wat_dates": MIN_DATES,
            "timestamped_odds_coverage": MIN_ODDS_COVERAGE,
            "roi_confidence": "date-cluster percentile bootstrap, 5000 replicates",
        },
        "markets": results,
        "all_markets_certified": all_certified,
        "value_betting_thresholds_met": all_certified,
        "verified_source_evidence_digest_count": len(verified_digests),
        "value_betting_authorized": False,
        "publication_authorized": False,
        "provenance_receipt_verification_required": True,
        "human_release_approval_required": True,
        "side_effects": {
            "provider_requests": 0, "database_writes": 0,
            "prediction_publications": 0, "telegram_deliveries": 0,
            "schedules_activated": 0,
        },
    }
