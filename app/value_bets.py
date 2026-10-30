"""Conservative value-bet screening primitives.

This module does not claim that a model is accurate. It screens supplied
probabilities against available decimal odds and defaults to no bet when data
are missing or invalid. Production alerts should only be enabled after
chronological backtesting and probability calibration.
"""
from __future__ import annotations

import math
from typing import Mapping, Any



def _certificate_allows(certificate: Any, market: str) -> bool:
    """Require an evidence-backed, market-specific validation certificate."""
    return (
        isinstance(certificate, Mapping)
        and certificate.get("status") == "VALIDATED"
        and certificate.get("schema_version") == 1
        and market in (certificate.get("approved_markets") or [])
        and certificate.get("betting_validation") is True
    )


def build_value_validation_certificate(
    backtest_report: Mapping[str, Any],
    paper_report: Mapping[str, Any],
    *,
    min_walk_forward_matches: int = 1000,
    min_paper_bets: int = 300,
    min_paper_dates: int = 90,
) -> dict[str, Any]:
    """Fail-closed release certificate using backtest and prospective paper evidence."""
    failures: dict[str, list[str]] = {}
    approved: list[str] = []
    live = backtest_report.get("live_pipeline") or {}
    rolling = ((live.get("goal_markets") or {}).get("rolling_origin_calibration") or {})
    paper = paper_report.get("markets") if isinstance(paper_report.get("markets"), Mapping) else {}
    goal_markets = {
        "BTTS": "btts_yes",
        "OVER_UNDER_1_5": "over_1_5",
        "OVER_UNDER_2_5": "over_2_5",
        "OVER_UNDER_3_5": "over_3_5",
    }

    def check_paper(market: str) -> list[str]:
        evidence = paper.get(market) or {}
        reasons = []
        if int(evidence.get("settled_bets") or 0) < min_paper_bets:
            reasons.append("insufficient settled prospective paper bets")
        if int(evidence.get("distinct_match_dates") or 0) < min_paper_dates:
            reasons.append("insufficient prospective observation dates")
        roi = _safe_float(evidence.get("net_roi"))
        if roi is None or roi <= 0:
            reasons.append("prospective net ROI is not positive")
        lower = _safe_float(evidence.get("roi_lower_95_ci"))
        if lower is None or lower <= 0:
            reasons.append("95% ROI lower confidence bound is not positive")
        coverage = _safe_float(evidence.get("timestamped_odds_coverage"))
        if coverage is None or coverage < 0.98:
            reasons.append("timestamped odds coverage is below 98%")
        return reasons

    for public_market, model_market in goal_markets.items():
        reasons = []
        diagnostic = (rolling.get("markets") or {}).get(model_market) or {}
        if diagnostic.get("status") != "CALIBRATION_DIAGNOSTIC_PASS":
            reasons.append("rolling-origin calibration did not pass")
        if int((diagnostic.get("raw") or {}).get("matches") or 0) < min_walk_forward_matches:
            reasons.append("insufficient independent walk-forward test matches")
        reasons.extend(check_paper(public_market))
        if reasons:
            failures[public_market] = reasons
        else:
            approved.append(public_market)

    # 1X2 must beat the market on both full live-pipeline data and the recent holdout.
    full = ((live.get("historical_odds_subset") or {}).get("models_compared_on_same_matches") or {})
    holdout = (((backtest_report.get("recent_holdout") or {}).get("historical_odds_subset") or {}).get("models_compared_on_same_matches") or {})
    for scope, comparison in (("full", full), ("holdout", holdout)):
        model = comparison.get("live_poisson") or comparison.get("poisson") or {}
        market = comparison.get("market") or {}
        if not model or not market:
            failures.setdefault("1X2", []).append(f"{scope} market benchmark is missing")
            continue
        for metric in ("brier_score", "log_loss"):
            mv, bv = _safe_float(model.get(metric)), _safe_float(market.get(metric))
            if mv is None or bv is None or mv >= bv:
                failures.setdefault("1X2", []).append(f"{scope} {metric} does not beat market")
    failures.setdefault("1X2", []).extend(check_paper("1X2"))
    if not failures.get("1X2"):
        approved.append("1X2")

    required = ["1X2", *goal_markets.keys()]
    passed = len(approved) == len(required)
    return {
        "schema_version": 1,
        "status": "VALIDATED" if passed else "LOCKED_INSUFFICIENT_EVIDENCE",
        "betting_validation": passed,
        "approved_markets": approved if passed else [],
        "market_diagnostics": {
            market: {"status": "PASS" if market in approved else "LOCKED", "failures": failures.get(market, [])}
            for market in required
        },
        "requirements": {
            "minimum_walk_forward_matches": min_walk_forward_matches,
            "minimum_paper_bets_per_market": min_paper_bets,
            "minimum_distinct_match_dates": min_paper_dates,
            "minimum_timestamped_odds_coverage": 0.98,
            "positive_net_roi": True,
            "positive_95_percent_roi_lower_bound": True,
            "1x2_must_beat_market_on_full_and_recent_holdout": True,
        },
        "alerts_enabled": passed,
        "note": "Missing, incomplete or failing evidence keeps every market locked. Calibration alone does not prove profitability.",
    }

def _valid_probability(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and 0.0 <= number <= 1.0


def _valid_odds(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 1.0


def devig_probabilities(odds: Mapping[str, float]) -> dict[str, float]:
    """Normalize reciprocal odds to remove the proportional bookmaker margin."""
    if len(odds) < 2 or not all(_valid_odds(v) for v in odds.values()):
        raise ValueError("At least two valid decimal odds greater than 1 are required")
    raw = {key: 1.0 / float(value) for key, value in odds.items()}
    total = sum(raw.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Odds do not produce a valid market probability")
    return {key: value / total for key, value in raw.items()}


def screen_value_bets(
    model_probabilities: Mapping[str, float],
    decimal_odds: Mapping[str, float],
    *,
    min_edge: float = 0.04,
    min_expected_return: float = 0.05,
    min_model_probability: float = 0.45,
    min_odds: float = 1.50,
    max_odds: float = 4.00,
    model_validated: bool = False,
) -> list[dict[str, Any]]:
    """Return candidates passing strict thresholds; otherwise return no bets.

    Edge is model probability minus de-vigged market probability. Expected
    return is p*odds-1 per unit staked, before any limits, slippage or fees.
    Candidates are deliberately suppressed unless the caller explicitly
    confirms that the model has passed out-of-sample validation.
    """
    thresholds = (min_edge, min_expected_return, min_model_probability)
    if any(not math.isfinite(float(x)) for x in thresholds):
        raise ValueError("Thresholds must be finite")
    if min_edge < 0 or min_expected_return < 0 or not 0 <= min_model_probability <= 1:
        raise ValueError("Invalid probability/return thresholds")
    if min_odds <= 1 or max_odds < min_odds:
        raise ValueError("Invalid odds range")
    if not model_validated:
        return []

    keys = set(model_probabilities) & set(decimal_odds)
    if len(keys) < 2:
        return []
    valid = {
        key: float(decimal_odds[key])
        for key in keys
        if _valid_probability(model_probabilities[key]) and _valid_odds(decimal_odds[key])
    }
    if len(valid) < 2:
        return []
    market_probs = devig_probabilities(valid)
    candidates: list[dict[str, Any]] = []
    for key, odds in valid.items():
        probability = float(model_probabilities[key])
        edge = probability - market_probs[key]
        expected_return = probability * odds - 1.0
        if (
            min_odds <= odds <= max_odds
            and probability >= min_model_probability
            and edge >= min_edge
            and expected_return >= min_expected_return
        ):
            candidates.append({
                "selection": key,
                "model_probability": probability,
                "devigged_market_probability": market_probs[key],
                "edge": edge,
                "edge_percentage_points": edge * 100.0,
                "decimal_odds": odds,
                "expected_return_per_unit": expected_return,
                "status": "CANDIDATE_NOT_GUARANTEED",
            })
    return sorted(candidates, key=lambda row: (row["expected_return_per_unit"], row["edge"]), reverse=True)


def _market_probability_pairs(prediction: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    probabilities = prediction.get("probabilities") if isinstance(prediction.get("probabilities"), Mapping) else {}
    goal_markets = prediction.get("goal_markets") if isinstance(prediction.get("goal_markets"), Mapping) else {}
    btts = prediction.get("btts_yes", goal_markets.get("btts_yes_prob"))
    over = prediction.get("over_2_5", goal_markets.get("over_2_prob"))
    result: dict[str, dict[str, float]] = {}
    one_x_two = {
        key: probabilities.get(key)
        for key in ("home_win", "draw", "away_win")
    }
    if all(_valid_probability(value) for value in one_x_two.values()):
        result["1X2"] = {key: float(value) for key, value in one_x_two.items()}
    if _valid_probability(btts):
        result["BTTS"] = {"yes": float(btts), "no": 1.0 - float(btts)}
    if _valid_probability(over):
        result["OVER_UNDER_2_5"] = {"over": float(over), "under": 1.0 - float(over)}
    return result


def _outcome_odds(outcomes: Any, home_team: str, away_team: str, market: str) -> dict[str, float]:
    if not isinstance(outcomes, list):
        return {}
    mapped: dict[str, float] = {}
    for item in outcomes:
        if not isinstance(item, Mapping) or not _valid_odds(item.get("price")):
            continue
        name = str(item.get("name") or "").strip().casefold()
        if market == "1X2":
            if name == home_team.casefold():
                mapped["home_win"] = float(item["price"])
            elif name == away_team.casefold():
                mapped["away_win"] = float(item["price"])
            elif name in {"draw", "tie"}:
                mapped["draw"] = float(item["price"])
        elif market == "BTTS":
            if name in {"yes", "btts yes"}:
                mapped["yes"] = float(item["price"])
            elif name in {"no", "btts no"}:
                mapped["no"] = float(item["price"])
        elif market == "OVER_UNDER_2_5":
            point = item.get("point")
            if point is not None and float(point) != 2.5:
                continue
            if name in {"over", "over 2.5"}:
                mapped["over"] = float(item["price"])
            elif name in {"under", "under 2.5"}:
                mapped["under"] = float(item["price"])
    return mapped


def screen_fixture_value_bets(
    prediction: Mapping[str, Any],
    *,
    validation_certificate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Screen only markets released by a formal validation certificate."""
    probability_sets = _market_probability_pairs(prediction)
    home = str(prediction.get("home_team") or "")
    away = str(prediction.get("away_team") or "")
    price_sets: dict[str, list[dict[str, Any]]] = {
        "1X2": [], "BTTS": [], "OVER_UNDER_2_5": []
    }

    def add(market: str, provider: str, bookmaker: str, odds: Mapping[str, Any]) -> None:
        expected_keys = {
            "1X2": {"home_win", "draw", "away_win"},
            "BTTS": {"yes", "no"},
            "OVER_UNDER_2_5": {"over", "under"},
        }[market]
        if expected_keys.issubset(odds) and all(_valid_odds(odds[key]) for key in expected_keys):
            price_sets[market].append({
                "provider": provider, "bookmaker": bookmaker,
                "odds": {key: float(odds[key]) for key in expected_keys},
            })

    five = prediction.get("five_dollar_market_odds")
    if isinstance(five, Mapping):
        for book in five.get("bookmakers") or []:
            if not isinstance(book, Mapping):
                continue
            add("1X2", "5DollarFootballAPI", str(book.get("bookmaker") or "bookmaker"), book.get("1x2") or {})
            add("BTTS", "5DollarFootballAPI", str(book.get("bookmaker") or "bookmaker"), book.get("btts") or {})
            totals = book.get("over_under") or {}
            if str(totals.get("line") or "2.5") in {"2.5", "2.50"}:
                add("OVER_UNDER_2_5", "5DollarFootballAPI", str(book.get("bookmaker") or "bookmaker"), totals)

    for provider_key, provider_name in (
        ("the_odds_api_market_odds", "The Odds API"),
        ("infer_sports_market_odds", "InferSports"),
    ):
        provider_data = prediction.get(provider_key)
        if not isinstance(provider_data, Mapping):
            continue
        markets = provider_data.get("markets") or {}
        for market in ("1X2", "BTTS", "OVER_UNDER_2_5"):
            market_key = {"1X2": "h2h", "BTTS": "btts", "OVER_UNDER_2_5": "totals"}[market]
            for item in (markets.get(market_key) or []):
                if not isinstance(item, Mapping):
                    continue
                odds = _outcome_odds(item.get("outcomes"), home, away, market)
                add(market, provider_name, str(item.get("bookmaker") or "bookmaker"), odds)

    oddspapi = prediction.get("oddspapi_market_odds")
    if isinstance(oddspapi, Mapping):
        for item in oddspapi.get("btts") or []:
            if isinstance(item, Mapping):
                add("BTTS", "OddsPapi", str(item.get("bookmaker") or "bookmaker"), item)
        for item in oddspapi.get("over_under") or []:
            if isinstance(item, Mapping) and str(item.get("line")) in {"2.5", "2.50"}:
                add("OVER_UNDER_2_5", "OddsPapi", str(item.get("bookmaker") or "bookmaker"), item)

    output: dict[str, Any] = {}
    total_candidates = 0
    for market, prices in price_sets.items():
        candidates: list[dict[str, Any]] = []
        probabilities = probability_sets.get(market)
        if probabilities:
            for price_row in prices:
                found = screen_value_bets(
                    probabilities, price_row["odds"], model_validated=_certificate_allows(validation_certificate, market)
                )
                for candidate in found:
                    candidates.append({
                        **candidate,
                        "market": market,
                        "provider": price_row["provider"],
                        "bookmaker": price_row["bookmaker"],
                    })
        candidates.sort(key=lambda row: (row["expected_return_per_unit"], row["edge"]), reverse=True)
        output[market] = {
            "status": "CANDIDATES_FOUND" if candidates else ("NO_QUALIFYING_VALUE" if _certificate_allows(validation_certificate, market) else "DISABLED_UNVALIDATED"),
            "bookmaker_price_sets": len(prices),
            "candidates": candidates,
        }
        total_candidates += len(candidates)
    return {
        "status": "CANDIDATES_FOUND" if total_candidates else ("NO_QUALIFYING_VALUE" if isinstance(validation_certificate, Mapping) and validation_certificate.get("status") == "VALIDATED" else "DISABLED_UNVALIDATED"),
        "model_validated": bool(isinstance(validation_certificate, Mapping) and validation_certificate.get("status") == "VALIDATED"),
        "markets": output,
        "candidate_count": total_candidates,
        "note": "Research screen only. No bookmaker actions are performed.",
    }


def attach_value_bet_screens(
    report: dict[str, Any],
    *,
    validation_certificate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach certificate-gated value screens to every prediction and report."""
    predictions = report.get("predictions")
    if not isinstance(predictions, list):
        predictions = []
        report["predictions"] = predictions
    aggregate = {"1X2": 0, "BTTS": 0, "OVER_UNDER_2_5": 0}
    candidate_count = 0
    for prediction in predictions:
        if not isinstance(prediction, dict):
            continue
        screen = screen_fixture_value_bets(prediction, validation_certificate=validation_certificate)
        prediction["value_bet_screen"] = screen
        candidate_count += int(screen.get("candidate_count") or 0)
        for market, result in (screen.get("markets") or {}).items():
            aggregate[market] = aggregate.get(market, 0) + int(result.get("bookmaker_price_sets") or 0)
    report["value_bet_screen"] = {
        "status": "CANDIDATES_FOUND" if candidate_count else ("NO_QUALIFYING_VALUE" if isinstance(validation_certificate, Mapping) and validation_certificate.get("status") == "VALIDATED" else "DISABLED_UNVALIDATED"),
        "model_validated": bool(isinstance(validation_certificate, Mapping) and validation_certificate.get("status") == "VALIDATED"),
        "markets": ["1X2", "BTTS", "OVER_UNDER_2_5"],
        "bookmaker_price_sets_by_market": aggregate,
        "candidate_count": candidate_count,
        "alerts_enabled": bool(isinstance(validation_certificate, Mapping) and validation_certificate.get("status") == "VALIDATED" and validation_certificate.get("alerts_enabled") is True),
        "validation_certificate": dict(validation_certificate) if isinstance(validation_certificate, Mapping) else None,
        "note": "Value candidates remain suppressed until repeated chronological out-of-sample validation passes.",
    }
    return report
