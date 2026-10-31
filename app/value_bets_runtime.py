"""Timestamp-safe production adapter for certificate-gated market screening.

The core probability and validation rules live in app.value_bets. This adapter
adds strict quote-time validation and exposes all three full-time totals lines.
No bookmaker actions are performed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from app import value_bets as core


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _eligible_snapshot(snapshot: Any, prediction: Mapping[str, Any]) -> bool:
    if not isinstance(snapshot, Mapping):
        return False
    kickoff = _timestamp(prediction.get("kickoff_local") or prediction.get("kickoff"))
    fetched = _timestamp(snapshot.get("fetched_at"))
    commence = _timestamp(snapshot.get("commence_time"))
    return bool(
        kickoff and fetched and commence and fetched < kickoff and commence == kickoff
        and 0 <= (kickoff - fetched).total_seconds() <= 24 * 3600
    )


def _eligible_quote(book: Mapping[str, Any], snapshot: Mapping[str, Any], prediction: Mapping[str, Any]) -> bool:
    quote_time = _timestamp(book.get("last_update"))
    fetched = _timestamp(snapshot.get("fetched_at"))
    kickoff = _timestamp(prediction.get("kickoff_local") or prediction.get("kickoff"))
    return bool(
        quote_time and fetched and kickoff and quote_time <= fetched and quote_time < kickoff
        and 0 <= (kickoff - quote_time).total_seconds() <= 24 * 3600
    )


def _probabilities(prediction: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    model_name = str(prediction.get("model") or prediction.get("goal_markets_model") or "")
    if model_name == "experimental_elo_by_competition":
        raw = prediction.get("poisson_probabilities")
    elif model_name == "experimental_recent_goals_poisson":
        raw = prediction.get("probabilities")
    else:
        raw = None
    raw = raw if isinstance(raw, Mapping) else {}
    output: dict[str, dict[str, float]] = {}
    one_x_two = {
        "home_win": raw.get("home_win", raw.get("H")),
        "draw": raw.get("draw", raw.get("D")),
        "away_win": raw.get("away_win", raw.get("A")),
    }
    if all(core._valid_probability(value) for value in one_x_two.values()):
        output["1X2"] = {key: float(value) for key, value in one_x_two.items()}
    btts = prediction.get("btts_yes")
    if core._valid_probability(btts):
        output["BTTS"] = {"yes": float(btts), "no": 1.0 - float(btts)}
    for line in (1.5, 2.5, 3.5):
        suffix = str(line).replace(".", "_")
        value = prediction.get(f"over_{suffix}")
        if core._valid_probability(value):
            output[f"OVER_UNDER_{suffix}"] = {"over": float(value), "under": 1.0 - float(value)}
    return output


def _map_outcomes(outcomes: Any, home: str, away: str, market: str) -> dict[str, float]:
    if not isinstance(outcomes, list):
        return {}
    mapped: dict[str, float] = {}
    for item in outcomes:
        if not isinstance(item, Mapping) or not core._valid_odds(item.get("price")):
            continue
        name = str(item.get("name") or "").strip().casefold()
        if market == "1X2":
            if name == home.casefold():
                mapped["home_win"] = float(item["price"])
            elif name == away.casefold():
                mapped["away_win"] = float(item["price"])
            elif name in {"draw", "tie"}:
                mapped["draw"] = float(item["price"])
        elif market == "BTTS":
            if name in {"yes", "btts yes"}:
                mapped["yes"] = float(item["price"])
            elif name in {"no", "btts no"}:
                mapped["no"] = float(item["price"])
        else:
            line = float(market.removeprefix("OVER_UNDER_").replace("_", "."))
            try:
                point = float(item.get("point"))
            except (TypeError, ValueError):
                continue
            if abs(point - line) > 1e-9:
                continue
            if name in {"over", f"over {line:g}"}:
                mapped["over"] = float(item["price"])
            elif name in {"under", f"under {line:g}"}:
                mapped["under"] = float(item["price"])
    return mapped


def _paper_eligible_probabilities(prediction: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    """Return only model families/markets eligible for prospective shadow tracking."""
    model_name = str(prediction.get("model") or "")
    if model_name == "experimental_elo_by_competition":
        raw = prediction.get("poisson_probabilities")
    elif model_name == "experimental_recent_goals_poisson":
        raw = prediction.get("probabilities")
    else:
        raw = None
    raw = raw if isinstance(raw, Mapping) else {}
    output: dict[str, dict[str, float]] = {}
    one_x_two = {
        "home_win": raw.get("home_win", raw.get("H")),
        "draw": raw.get("draw", raw.get("D")),
        "away_win": raw.get("away_win", raw.get("A")),
    }
    if all(core._valid_probability(value) for value in one_x_two.values()):
        output["1X2"] = {key: float(value) for key, value in one_x_two.items()}

    calibration = prediction.get("goal_market_calibration")
    calibrated = (
        prediction.get("goal_markets_model") == "experimental_recent_goals_poisson"
        and isinstance(calibration, Mapping)
        and calibration.get("status") == "APPLIED_PROSPECTIVELY"
    )
    if calibrated:
        markets = set(calibration.get("markets") or [])
        for public_market, calibration_key, field in (
            ("BTTS", "btts_yes", "btts_yes"),
            ("OVER_UNDER_1_5", "over_1_5", "over_1_5"),
            ("OVER_UNDER_2_5", "over_2_5", "over_2_5"),
            ("OVER_UNDER_3_5", "over_3_5", "over_3_5"),
        ):
            value = prediction.get(field)
            if calibration_key in markets and core._valid_probability(value):
                probability = float(value)
                output[public_market] = (
                    {"yes": probability, "no": 1.0 - probability}
                    if public_market == "BTTS"
                    else {"over": probability, "under": 1.0 - probability}
                )
    return output


def screen_fixture_value_bets(
    prediction: Mapping[str, Any],
    *,
    validation_certificate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Separate released value candidates from unapproved prospective paper candidates."""
    markets = ["1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5"]
    probabilities = _probabilities(prediction)
    paper_probabilities = _paper_eligible_probabilities(prediction)
    price_sets: dict[str, list[dict[str, Any]]] = {market: [] for market in markets}
    snapshot = prediction.get("the_odds_api_market_odds")
    if _eligible_snapshot(snapshot, prediction):
        odds_markets = snapshot.get("markets") or {}
        if isinstance(odds_markets, Mapping):
            home, away = str(prediction.get("home_team") or ""), str(prediction.get("away_team") or "")
            provider_keys = {
                "1X2": "h2h", "BTTS": "btts",
                "OVER_UNDER_1_5": "totals", "OVER_UNDER_2_5": "totals",
                "OVER_UNDER_3_5": "totals",
            }
            for market in markets:
                for book in odds_markets.get(provider_keys[market]) or []:
                    if not isinstance(book, Mapping) or not _eligible_quote(book, snapshot, prediction):
                        continue
                    odds = _map_outcomes(book.get("outcomes"), home, away, market)
                    required = {"home_win", "draw", "away_win"} if market == "1X2" else (
                        {"yes", "no"} if market == "BTTS" else {"over", "under"}
                    )
                    if required.issubset(odds):
                        price_sets[market].append({
                            "provider": "The Odds API",
                            "bookmaker": str(book.get("bookmaker") or "bookmaker"),
                            "odds": {key: odds[key] for key in required},
                        })

    output: dict[str, Any] = {}
    candidate_count = 0
    paper_candidate_count = 0
    for market in markets:
        candidates: list[dict[str, Any]] = []
        paper_candidates: list[dict[str, Any]] = []
        approved = core._certificate_allows(validation_certificate, market)
        model_probs = probabilities.get(market)
        paper_probs = paper_probabilities.get(market)
        for price_set in price_sets[market]:
            if model_probs:
                for candidate in core.screen_value_bets(
                    model_probs, price_set["odds"], model_validated=approved
                ):
                    candidates.append({
                        **candidate, "market": market,
                        "model": "experimental_recent_goals_poisson",
                        "provider": price_set["provider"],
                        "bookmaker": price_set["bookmaker"],
                    })
            if paper_probs:
                for candidate in core.screen_value_bets(
                    paper_probs, price_set["odds"], model_validated=True
                ):
                    paper_candidates.append({
                        **candidate, "market": market,
                        "model": (
                            "experimental_recent_goals_poisson"
                            if market == "1X2"
                            else str(prediction.get("goal_markets_model") or "experimental_recent_goals_poisson")
                        ),
                        "provider": price_set["provider"],
                        "bookmaker": price_set["bookmaker"],
                        "status": "CANDIDATE_NOT_GUARANTEED" if approved else "PAPER_ONLY_NOT_APPROVED",
                        "release_status": "CERTIFIED" if approved else "LOCKED_UNVALIDATED",
                    })
        candidates.sort(key=lambda row: (row["expected_return_per_unit"], row["edge"]), reverse=True)
        paper_candidates.sort(
            key=lambda row: (row["expected_return_per_unit"], row["edge"]),
            reverse=True,
        )
        # The prospective ledger allows one best selection per fixture and market.
        paper_candidates = paper_candidates[:1]
        candidate_count += len(candidates)
        paper_candidate_count += len(paper_candidates)
        output[market] = {
            "status": (
                "CANDIDATES_FOUND" if candidates
                else "PAPER_ONLY_CANDIDATES" if paper_candidates and not approved
                else "NO_QUALIFYING_VALUE" if approved
                else "DISABLED_UNVALIDATED"
            ),
            "bookmaker_price_sets": len(price_sets[market]),
            "candidates": candidates,
            "paper_candidate_count": len(paper_candidates),
            "paper_candidates": paper_candidates,
        }
    any_approved = any(core._certificate_allows(validation_certificate, market) for market in markets)
    return {
        "status": (
            "CANDIDATES_FOUND" if candidate_count
            else "PAPER_ONLY_CANDIDATES" if paper_candidate_count
            else "NO_QUALIFYING_VALUE" if any_approved
            else "DISABLED_UNVALIDATED"
        ),
        "model_validated": any_approved,
        "markets": output,
        "candidate_count": candidate_count,
        "paper_candidate_count": paper_candidate_count,
        "note": "Paper-only candidates are prospective research records, not approved betting alerts. Release remains certificate-gated; no bookmaker actions are performed.",
    }


def attach_value_bet_screens(
    report: dict[str, Any],
    *,
    validation_certificate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach released and paper-only candidate counts without weakening release gates."""
    predictions = report.get("predictions")
    if not isinstance(predictions, list):
        predictions = []
        report["predictions"] = predictions
    aggregate = {market: 0 for market in ("1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5")}
    candidate_count = 0
    paper_candidate_count = 0
    for prediction in predictions:
        if not isinstance(prediction, dict):
            continue
        screen = screen_fixture_value_bets(prediction, validation_certificate=validation_certificate)
        prediction["value_bet_screen"] = screen
        candidate_count += int(screen.get("candidate_count") or 0)
        paper_candidate_count += int(screen.get("paper_candidate_count") or 0)
        for market, result in (screen.get("markets") or {}).items():
            aggregate[market] = aggregate.get(market, 0) + int(result.get("bookmaker_price_sets") or 0)
    any_approved = any(
        core._certificate_allows(validation_certificate, market) for market in aggregate
    )
    report["value_bet_screen"] = {
        "status": (
            "CANDIDATES_FOUND" if candidate_count
            else "PAPER_ONLY_CANDIDATES" if paper_candidate_count
            else "NO_QUALIFYING_VALUE" if any_approved
            else "DISABLED_UNVALIDATED"
        ),
        "model_validated": any_approved,
        "markets": list(aggregate),
        "bookmaker_price_sets_by_market": aggregate,
        "candidate_count": candidate_count,
        "paper_candidate_count": paper_candidate_count,
        "alerts_enabled": bool(
            any_approved and isinstance(validation_certificate, Mapping)
            and validation_certificate.get("alerts_enabled") is True
        ),
        "validation_certificate": dict(validation_certificate) if isinstance(validation_certificate, Mapping) else None,
        "note": "Paper-only candidates are logged for prospective validation and are not approved betting alerts. Live alerts remain locked until market-specific evidence passes.",
    }
    return report
