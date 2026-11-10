"""Hard certification gate for walk-forward and prospective value-bet evidence.

The evaluator is deliberately independent of prediction generation. It accepts
settled out-of-sample records, computes clustered ROI uncertainty, checks odds
timestamps and compares 1X2 probabilities with a de-vigged bookmaker baseline.
It never places bets or enables publication.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


MARKETS = {
    "1x2": {"outcomes": {"home", "draw", "away"}},
    "btts": {"outcomes": {"yes", "no"}},
    "over_2_5": {"outcomes": {"yes", "no"}},
}
MIN_WALK_FORWARD_MATCHES = 1000
MIN_PROSPECTIVE_SETTLED_SELECTIONS = 300
MIN_DISTINCT_DATES = 90
MIN_TIMESTAMPED_ODDS_COVERAGE = 0.98
BOOTSTRAP_REPLICATES = 5000
BOOTSTRAP_SEED = 20261110


class ValueBetCertificationError(ValueError):
    pass


def _hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueBetCertificationError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueBetCertificationError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueBetCertificationError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _valid_decimal_map(value: Any, outcomes: set[str], field: str) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != outcomes:
        raise ValueBetCertificationError(f"{field}_shape_invalid")
    normalized = {}
    for key, odds in value.items():
        if isinstance(odds, bool) or not isinstance(odds, (int, float)) or not math.isfinite(odds) or odds <= 1.0:
            raise ValueBetCertificationError(f"{field}_decimal_odds_invalid:{key}")
        normalized[key] = float(odds)
    return normalized


def _probability_map(value: Any, outcomes: set[str], field: str) -> dict:
    if not isinstance(value, dict) or set(value) != outcomes:
        raise ValueBetCertificationError(f"{field}_shape_invalid")
    normalized = {}
    for key, probability in value.items():
        if (isinstance(probability, bool) or not isinstance(probability, (int, float))
                or not math.isfinite(probability) or not 0 < probability < 1):
            raise ValueBetCertificationError(f"{field}_probability_invalid:{key}")
        normalized[key] = float(probability)
    if abs(sum(normalized.values()) - 1.0) > 1e-6:
        raise ValueBetCertificationError(f"{field}_probabilities_do_not_sum_to_one")
    return normalized


def _clustered_roi_interval(clusters: dict[str, tuple[float, float]]) -> tuple[float, float] | tuple[None, None]:
    dates = sorted(clusters)
    if len(dates) < 2:
        return None, None
    rng = random.Random(BOOTSTRAP_SEED)
    samples = []
    for _ in range(BOOTSTRAP_REPLICATES):
        profit = stake = 0.0
        for day in rng.choices(dates, k=len(dates)):
            day_profit, day_stake = clusters[day]
            profit += day_profit
            stake += day_stake
        if stake > 0:
            samples.append(profit / stake)
    if len(samples) != BOOTSTRAP_REPLICATES:
        return None, None
    samples.sort()
    lower = samples[int(0.025 * (len(samples) - 1))]
    upper = samples[int(0.975 * (len(samples) - 1))]
    return lower, upper


def certify_value_bet_markets(*, evaluation_records: list[dict]) -> dict:
    if not isinstance(evaluation_records, list):
        raise ValueBetCertificationError("evaluation_records_must_be_array")
    zone = ZoneInfo("Africa/Lagos")
    seen = set()
    grouped = defaultdict(list)

    for index, row in enumerate(evaluation_records):
        if not isinstance(row, dict):
            raise ValueBetCertificationError(f"evaluation_record_invalid:{index}")
        required = {
            "market", "fixture_id", "competition_key", "kickoff_at",
            "prediction_as_of", "walk_forward", "is_prospective", "selected",
            "selection", "stake_units", "decimal_odds", "odds",
            "odds_observed_at", "odds_retrieved_at", "settled_at",
            "actual_outcome", "model_probabilities", "bookmaker_odds",
        }
        if set(row) != required:
            raise ValueBetCertificationError(f"evaluation_record_shape_invalid:{index}")
        market = row.get("market")
        if not isinstance(market, str) or market not in MARKETS:
            raise ValueBetCertificationError(f"evaluation_market_invalid:{index}")
        fixture_id = row.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ValueBetCertificationError(f"evaluation_fixture_id_invalid:{index}")
        identity = (market, fixture_id)
        if identity in seen:
            raise ValueBetCertificationError(f"duplicate_evaluation_fixture:{market}:{fixture_id}")
        seen.add(identity)
        if not isinstance(row.get("competition_key"), str) or not row["competition_key"].strip():
            raise ValueBetCertificationError(f"evaluation_competition_invalid:{index}")
        if row.get("walk_forward") is not True:
            raise ValueBetCertificationError(f"non_walk_forward_record:{index}")
        if not isinstance(row.get("is_prospective"), bool) or not isinstance(row.get("selected"), bool):
            raise ValueBetCertificationError(f"evaluation_selection_flags_invalid:{index}")
        outcomes = MARKETS[market]["outcomes"]
        actual = row.get("actual_outcome")
        if not isinstance(actual, str) or actual not in outcomes:
            raise ValueBetCertificationError(f"evaluation_actual_outcome_invalid:{index}")
        kickoff = _time(row.get("kickoff_at"), f"record_{index}_kickoff")
        cutoff = _time(row.get("prediction_as_of"), f"record_{index}_prediction_as_of")
        settled = _time(row.get("settled_at"), f"record_{index}_settled_at")
        if cutoff >= kickoff or settled <= kickoff:
            raise ValueBetCertificationError(f"evaluation_temporal_order_invalid:{index}")
        local_date = kickoff.astimezone(zone).date().isoformat()

        odds = _valid_decimal_map(row.get("odds"), outcomes, f"record_{index}_odds")
        odds_observed = row.get("odds_observed_at")
        odds_retrieved = row.get("odds_retrieved_at")
        odds_timestamped = odds is not None and odds_observed is not None and odds_retrieved is not None
        if odds_timestamped:
            observed = _time(odds_observed, f"record_{index}_odds_observed_at")
            retrieved = _time(odds_retrieved, f"record_{index}_odds_retrieved_at")
            if observed > cutoff or retrieved > cutoff or retrieved < observed:
                raise ValueBetCertificationError(f"evaluation_odds_temporal_order_invalid:{index}")
        elif row.get("selected") and row.get("is_prospective"):
            raise ValueBetCertificationError(f"prospective_selection_without_timestamped_odds:{index}")

        stake = row.get("stake_units")
        if isinstance(stake, bool) or not isinstance(stake, (int, float)) or not math.isfinite(stake) or stake < 0:
            raise ValueBetCertificationError(f"evaluation_stake_invalid:{index}")
        selected = row["selected"]
        pick = row.get("selection")
        decimal_odds = row.get("decimal_odds")
        profit = 0.0
        prospective_selection = False
        if selected:
            if not isinstance(pick, str) or pick not in outcomes or not row["is_prospective"] or odds is None or pick not in odds:
                raise ValueBetCertificationError(f"invalid_prospective_selection:{index}")
            if (stake <= 0 or isinstance(decimal_odds, bool)
                    or not isinstance(decimal_odds, (int, float))
                    or not math.isfinite(decimal_odds) or decimal_odds <= 1.0):
                raise ValueBetCertificationError(f"selected_stake_or_odds_invalid:{index}")
            if abs(float(decimal_odds) - odds[pick]) > 1e-9:
                raise ValueBetCertificationError(f"selected_odds_do_not_match_timestamped_quote:{index}")
            prospective_selection = True
            profit = float(stake) * (odds[pick] - 1.0) if pick == actual else -float(stake)
        else:
            if pick is not None or decimal_odds is not None or float(stake) != 0.0:
                raise ValueBetCertificationError(f"unselected_record_contains_stake_or_pick:{index}")

        model_probabilities = None
        bookmaker_odds = None
        bookmaker_probabilities = None
        if market == "1x2":
            model_probabilities = _probability_map(
                row.get("model_probabilities"), outcomes, f"record_{index}_model_probabilities"
            )
            bookmaker_odds = _valid_decimal_map(
                row.get("bookmaker_odds"), outcomes, f"record_{index}_bookmaker_odds"
            )
            if odds_timestamped:
                if bookmaker_odds is None:
                    raise ValueBetCertificationError(f"1x2_bookmaker_baseline_missing:{index}")
                if any(abs(bookmaker_odds[key] - odds[key]) > 1e-9 for key in outcomes):
                    raise ValueBetCertificationError(f"1x2_bookmaker_quote_mismatch:{index}")
                implied = {key: 1.0 / value for key, value in bookmaker_odds.items()}
                overround = sum(implied.values())
                bookmaker_probabilities = {key: value / overround for key, value in implied.items()}
            elif bookmaker_odds is not None:
                raise ValueBetCertificationError(f"1x2_untimestamped_bookmaker_quote:{index}")
            grouped[market].append({
                "fixture_id": fixture_id,
                "local_date": local_date,
                "actual": actual,
                "model_probabilities": model_probabilities,
                "bookmaker_probabilities": bookmaker_probabilities,
                "odds_timestamped": odds_timestamped,
                "prospective_selection": prospective_selection,
                "profit": profit,
                "stake": float(stake) if prospective_selection else 0.0,
            })
        else:
            grouped[market].append({
                "fixture_id": fixture_id,
                "local_date": local_date,
                "actual": actual,
                "odds_timestamped": odds_timestamped,
                "prospective_selection": prospective_selection,
                "profit": profit,
                "stake": float(stake) if prospective_selection else 0.0,
            })

    market_reports = {}
    for market in ("1x2", "btts", "over_2_5"):
        rows = grouped.get(market, [])
        dates = sorted({row["local_date"] for row in rows})
        timestamped = sum(1 for row in rows if row["odds_timestamped"])
        odds_coverage = timestamped / len(rows) if rows else 0.0
        selected_rows = [row for row in rows if row["prospective_selection"]]
        prospective_dates = sorted({row["local_date"] for row in selected_rows})
        total_stake = sum(row["stake"] for row in selected_rows)
        total_profit = sum(row["profit"] for row in selected_rows)
        roi = total_profit / total_stake if total_stake else None
        clusters = defaultdict(lambda: [0.0, 0.0])
        for row in selected_rows:
            clusters[row["local_date"]][0] += row["profit"]
            clusters[row["local_date"]][1] += row["stake"]
        lower, upper = _clustered_roi_interval({
            day: (values[0], values[1]) for day, values in clusters.items()
        })

        brier_model = brier_book = logloss_model = logloss_book = None
        bookmaker_comparison_rows = [
            row for row in rows if row.get("bookmaker_probabilities") is not None
        ] if market == "1x2" else []
        if market == "1x2" and bookmaker_comparison_rows:
            model_brier = bookmaker_brier = model_logloss = bookmaker_logloss = 0.0
            for row in bookmaker_comparison_rows:
                actual = row["actual"]
                model = row["model_probabilities"]
                book = row["bookmaker_probabilities"]
                model_brier += sum((model[key] - (1.0 if key == actual else 0.0)) ** 2 for key in MARKETS["1x2"]["outcomes"])
                bookmaker_brier += sum((book[key] - (1.0 if key == actual else 0.0)) ** 2 for key in MARKETS["1x2"]["outcomes"])
                model_logloss -= math.log(model[actual])
                bookmaker_logloss -= math.log(book[actual])
            brier_model = model_brier / len(bookmaker_comparison_rows)
            brier_book = bookmaker_brier / len(bookmaker_comparison_rows)
            logloss_model = model_logloss / len(bookmaker_comparison_rows)
            logloss_book = bookmaker_logloss / len(bookmaker_comparison_rows)

        checks = {
            "walk_forward_sample": len(rows) >= MIN_WALK_FORWARD_MATCHES,
            "prospective_settled_selections": len(selected_rows) >= MIN_PROSPECTIVE_SETTLED_SELECTIONS,
            "distinct_dates": len(prospective_dates) >= MIN_DISTINCT_DATES,
            "timestamped_odds_coverage": odds_coverage >= MIN_TIMESTAMPED_ODDS_COVERAGE,
            "net_roi_positive": roi is not None and roi > 0,
            "roi_lower_95_bound_positive": lower is not None and lower > 0,
        }
        if market == "1x2":
            checks["beats_bookmaker_brier"] = brier_model is not None and brier_book is not None and brier_model < brier_book
            checks["beats_bookmaker_log_loss"] = logloss_model is not None and logloss_book is not None and logloss_model < logloss_book
        market_reports[market] = {
            "walk_forward_matches": len(rows),
            "prospective_settled_selections": len(selected_rows),
            "distinct_dates": len(prospective_dates),
            "walk_forward_distinct_dates": len(dates),
            "timestamped_odds_count": timestamped,
            "timestamped_odds_coverage": round(odds_coverage, 6),
            "bookmaker_comparison_matches": len(bookmaker_comparison_rows),
            "net_profit_units": round(total_profit, 6),
            "stake_units": round(total_stake, 6),
            "net_roi": round(roi, 6) if roi is not None else None,
            "roi_confidence_interval_95_clustered_by_date": {
                "lower": round(lower, 6) if lower is not None else None,
                "upper": round(upper, 6) if upper is not None else None,
                "method": "percentile_cluster_bootstrap",
                "replicates": BOOTSTRAP_REPLICATES,
            },
            "brier": {
                "model": round(brier_model, 6) if brier_model is not None else None,
                "bookmaker": round(brier_book, 6) if brier_book is not None else None,
            },
            "log_loss": {
                "model": round(logloss_model, 6) if logloss_model is not None else None,
                "bookmaker": round(logloss_book, 6) if logloss_book is not None else None,
            },
            "checks": checks,
            "certified": all(checks.values()),
        }

    report = {
        "schema_version": 1,
        "report_type": "veltrix_value_bet_certification",
        "evaluation_records_sha256": _hash({"records": evaluation_records}),
        "thresholds": {
            "walk_forward_matches_per_market": MIN_WALK_FORWARD_MATCHES,
            "prospective_settled_selections_per_market": MIN_PROSPECTIVE_SETTLED_SELECTIONS,
            "distinct_dates_per_market": MIN_DISTINCT_DATES,
            "timestamped_odds_coverage_per_market": MIN_TIMESTAMPED_ODDS_COVERAGE,
            "net_roi": ">0",
            "roi_lower_95_bound": ">0",
            "one_x_two_beats_bookmaker": ["brier", "log_loss"],
        },
        "methodology": {
            "roi_confidence_interval": "date-clustered percentile bootstrap",
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bookmaker_probabilities": "inverse decimal odds normalized by market overround",
            "timezone_for_distinct_dates": "Africa/Lagos",
        },
        "markets": market_reports,
        "value_betting_enabled": all(item["certified"] for item in market_reports.values()),
        "side_effects": {
            "provider_requests": 0,
            "database_writes": 0,
            "real_money_bets": 0,
            "prediction_publications": 0,
        },
    }
    report["certification_sha256"] = _hash(report)
    return report


def validate_value_bet_certification_report(report: Any, *,
                                          evaluation_records: list[dict] | None = None) -> dict:
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueBetCertificationError("certification_schema_invalid")
    if report.get("report_type") != "veltrix_value_bet_certification":
        raise ValueBetCertificationError("certification_type_invalid")
    supplied = report.get("certification_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64:
        raise ValueBetCertificationError("certification_hash_invalid")
    unhashed = dict(report)
    unhashed.pop("certification_sha256", None)
    if _hash(unhashed) != supplied:
        raise ValueBetCertificationError("certification_hash_mismatch")
    source_hash = report.get("evaluation_records_sha256")
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        raise ValueBetCertificationError("certification_source_hash_invalid")

    expected_thresholds = {
        "walk_forward_matches_per_market": MIN_WALK_FORWARD_MATCHES,
        "prospective_settled_selections_per_market": MIN_PROSPECTIVE_SETTLED_SELECTIONS,
        "distinct_dates_per_market": MIN_DISTINCT_DATES,
        "timestamped_odds_coverage_per_market": MIN_TIMESTAMPED_ODDS_COVERAGE,
        "net_roi": ">0",
        "roi_lower_95_bound": ">0",
        "one_x_two_beats_bookmaker": ["brier", "log_loss"],
    }
    if report.get("thresholds") != expected_thresholds:
        raise ValueBetCertificationError("certification_thresholds_mismatch")
    methodology = report.get("methodology")
    if not isinstance(methodology, dict) or (
        methodology.get("roi_confidence_interval") != "date-clustered percentile bootstrap"
        or methodology.get("bootstrap_replicates") != BOOTSTRAP_REPLICATES
        or methodology.get("bootstrap_seed") != BOOTSTRAP_SEED
        or methodology.get("bookmaker_probabilities") != "inverse decimal odds normalized by market overround"
        or methodology.get("timezone_for_distinct_dates") != "Africa/Lagos"
    ):
        raise ValueBetCertificationError("certification_methodology_mismatch")

    markets = report.get("markets")
    if not isinstance(markets, dict) or set(markets) != set(MARKETS):
        raise ValueBetCertificationError("certification_market_scope_invalid")
    all_pass = True
    for market, item in markets.items():
        if not isinstance(item, dict) or not isinstance(item.get("checks"), dict):
            raise ValueBetCertificationError(f"certification_market_report_invalid:{market}")
        sample = item.get("walk_forward_matches")
        selections = item.get("prospective_settled_selections")
        dates = item.get("distinct_dates")
        walk_forward_dates = item.get("walk_forward_distinct_dates")
        odds_count = item.get("timestamped_odds_count")
        coverage = item.get("timestamped_odds_coverage")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
               for value in (sample, selections, dates, walk_forward_dates, odds_count)):
            raise ValueBetCertificationError(f"certification_market_counts_invalid:{market}")
        if (sample < 0 or selections > sample or dates > selections
                or walk_forward_dates > sample or dates > walk_forward_dates
                or odds_count > sample):
            raise ValueBetCertificationError(f"certification_market_count_bounds_invalid:{market}")
        if isinstance(coverage, bool) or not isinstance(coverage, (int, float)) or not math.isfinite(coverage) or not 0 <= coverage <= 1:
            raise ValueBetCertificationError(f"certification_odds_coverage_invalid:{market}")
        expected_coverage = round(odds_count / sample, 6) if sample else 0.0
        if round(float(coverage), 6) != expected_coverage:
            raise ValueBetCertificationError(f"certification_odds_coverage_count_mismatch:{market}")

        profit, stake, roi = item.get("net_profit_units"), item.get("stake_units"), item.get("net_roi")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in (profit, stake)):
            raise ValueBetCertificationError(f"certification_roi_totals_invalid:{market}")
        if stake < 0 or (stake == 0 and roi is not None):
            raise ValueBetCertificationError(f"certification_roi_stake_invalid:{market}")
        if stake > 0:
            if isinstance(roi, bool) or not isinstance(roi, (int, float)) or not math.isfinite(roi):
                raise ValueBetCertificationError(f"certification_roi_invalid:{market}")
            if abs(float(roi) - float(profit) / float(stake)) > 1e-5:
                raise ValueBetCertificationError(f"certification_roi_total_mismatch:{market}")
        interval = item.get("roi_confidence_interval_95_clustered_by_date")
        if not isinstance(interval, dict) or (
            interval.get("method") != "percentile_cluster_bootstrap"
            or interval.get("replicates") != BOOTSTRAP_REPLICATES
        ):
            raise ValueBetCertificationError(f"certification_roi_interval_invalid:{market}")
        lower, upper = interval.get("lower"), interval.get("upper")
        if (lower is None) != (upper is None):
            raise ValueBetCertificationError(f"certification_roi_interval_bounds_invalid:{market}")
        if lower is not None and (
            isinstance(lower, bool) or isinstance(upper, bool)
            or not isinstance(lower, (int, float)) or not isinstance(upper, (int, float))
            or not math.isfinite(lower) or not math.isfinite(upper) or lower > upper
        ):
            raise ValueBetCertificationError(f"certification_roi_interval_bounds_invalid:{market}")

        expected_checks = {
            "walk_forward_sample": sample >= MIN_WALK_FORWARD_MATCHES,
            "prospective_settled_selections": selections >= MIN_PROSPECTIVE_SETTLED_SELECTIONS,
            "distinct_dates": dates >= MIN_DISTINCT_DATES,
            "timestamped_odds_coverage": float(coverage) >= MIN_TIMESTAMPED_ODDS_COVERAGE,
            "net_roi_positive": roi is not None and roi > 0,
            "roi_lower_95_bound_positive": lower is not None and lower > 0,
        }
        comparison_matches = item.get("bookmaker_comparison_matches")
        if (isinstance(comparison_matches, bool) or not isinstance(comparison_matches, int)
                or comparison_matches < 0 or comparison_matches > sample):
            raise ValueBetCertificationError(f"certification_bookmaker_comparison_count_invalid:{market}")
        if market == "1x2":
            if comparison_matches != odds_count:
                raise ValueBetCertificationError("certification_1x2_comparison_coverage_mismatch")
            brier, logloss = item.get("brier"), item.get("log_loss")
            if not isinstance(brier, dict) or not isinstance(logloss, dict):
                raise ValueBetCertificationError("certification_1x2_metrics_missing")
            bm, bb = brier.get("model"), brier.get("bookmaker")
            lm, lb = logloss.get("model"), logloss.get("bookmaker")
            if comparison_matches:
                numeric = (bm, bb, lm, lb)
                if any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) or value < 0 for value in numeric):
                    raise ValueBetCertificationError("certification_1x2_metrics_invalid")
                expected_checks["beats_bookmaker_brier"] = bm < bb
                expected_checks["beats_bookmaker_log_loss"] = lm < lb
            else:
                if any(value is not None for value in (bm, bb, lm, lb)):
                    raise ValueBetCertificationError("certification_1x2_empty_comparison_has_metrics")
                expected_checks["beats_bookmaker_brier"] = False
                expected_checks["beats_bookmaker_log_loss"] = False
        else:
            if comparison_matches != 0:
                raise ValueBetCertificationError(f"certification_unexpected_baseline_count:{market}")
            if item.get("brier") != {"model": None, "bookmaker": None} or item.get("log_loss") != {"model": None, "bookmaker": None}:
                raise ValueBetCertificationError(f"certification_unexpected_baseline_metrics:{market}")
        if item["checks"] != expected_checks:
            raise ValueBetCertificationError(f"certification_checks_do_not_match_metrics:{market}")
        certified = all(expected_checks.values())
        if item.get("certified") is not certified:
            raise ValueBetCertificationError(f"certification_market_status_mismatch:{market}")
        all_pass = all_pass and certified

    if report.get("value_betting_enabled") is not all_pass:
        raise ValueBetCertificationError("certification_global_status_mismatch")
    side_effects = report.get("side_effects")
    if not isinstance(side_effects, dict) or any(side_effects.get(key) != 0 for key in (
        "provider_requests", "database_writes", "real_money_bets", "prediction_publications",
    )):
        raise ValueBetCertificationError("certification_side_effect_boundary_invalid")

    source_revalidated = False
    if evaluation_records is not None:
        if _hash({"records": evaluation_records}) != source_hash:
            raise ValueBetCertificationError("certification_source_records_hash_mismatch")
        recomputed = certify_value_bet_markets(evaluation_records=evaluation_records)
        if recomputed["certification_sha256"] != supplied:
            raise ValueBetCertificationError("certification_recomputation_mismatch")
        source_revalidated = True
    elif all_pass:
        raise ValueBetCertificationError("source_records_required_for_certification_enablement")

    return {
        "valid": True,
        "certification_sha256": supplied,
        "value_betting_enabled": all_pass and source_revalidated,
        "source_records_revalidated": source_revalidated,
        "market_status": {market: item["certified"] for market, item in markets.items()},
    }
