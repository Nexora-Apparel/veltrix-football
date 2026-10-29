"""Evaluate archived experimental forecasts against completed fixture results.

This is paper tracking only. It does not place bets or certify model quality.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Any

COMPLETED_STATUSES = {"FT", "AET", "PEN"}
OUTCOMES = ("H", "D", "A")


def summarize_scored_matches(matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate proper scoring metrics over already validated forecast/result pairs."""
    count = len(matches)
    if not count:
        return {"matches": 0, "result_accuracy": None, "brier_score": None, "log_loss": None}
    brier = 0.0
    log_loss = 0.0
    correct = 0
    for row in matches:
        probabilities = row["probabilities"]
        actual = row["actual"]
        brier += sum(
            (float(probabilities[key]) - float(actual == key)) ** 2
            for key in OUTCOMES
        )
        log_loss += -math.log(max(1e-15, float(probabilities[actual])))
        correct += int(row.get("correct", max(probabilities, key=probabilities.get) == actual))
    return {
        "matches": count,
        "result_accuracy": correct / count,
        "brier_score": brier / count,
        "log_loss": log_loss / count,
    }


def merge_paper_ledger(ledger: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Add one report-date evaluation idempotently and recompute cumulative metrics."""
    current = dict(ledger)
    current.setdefault("evaluations", [])
    current.setdefault("scored_matches", [])
    current.setdefault("goal_market_scored", [])
    report_date = evaluation.get("report_date")
    if not report_date:
        raise ValueError("Evaluation must include a report_date.")
    evaluation_summary = {
        "report_date": report_date,
        "fixtures_scored": evaluation.get("fixtures_scored", 0),
        "completed_forecasts_scored": evaluation.get("completed_forecasts_scored", 0),
        "awaiting_result_or_match": evaluation.get("awaiting_result_or_match", 0),
        "withheld_or_invalid_forecasts": evaluation.get("withheld_or_invalid_forecasts", 0),
        "metrics": evaluation.get("metrics", {}),
        "metrics_by_model": evaluation.get("metrics_by_model", {}),
        "model_versions": sorted({str(row.get("model", "unknown")) for row in evaluation.get("matches", [])}),
        "goal_market_selections_settled": len(evaluation.get("goal_market_matches", [])),
        "goal_market_metrics": evaluation.get("goal_market_metrics", {}),
    }
    existing_index = next(
        (index for index, row in enumerate(current["evaluations"])
         if row.get("report_date") == report_date),
        None,
    )
    if existing_index is None:
        current["evaluations"].append(evaluation_summary)
        should_merge_matches = True
    else:
        previous = current["evaluations"][existing_index]
        previous_pending = int(previous.get("awaiting_result_or_match", 0))
        previous_empty = (
            int(previous.get("completed_forecasts_scored", 0)) == 0
            and int(previous.get("fixtures_scored", 0)) == 0
            and not previous.get("model_versions")
            and int(previous.get("withheld_or_invalid_forecasts", 0)) == 0
        )
        # Empty evaluations are not proof that a report was successfully tracked:
        # an earlier same-day artifact may have contained no usable forecasts.
        should_merge_matches = previous_pending > 0 or previous_empty
        if should_merge_matches:
            current["evaluations"][existing_index] = evaluation_summary
    # Pending report dates can be re-evaluated as postponed fixtures finish;
    # match-level deduplication below prevents duplicate scores.
    if should_merge_matches:
        for match in evaluation.get("matches", []):
            current["scored_matches"].append({**match, "report_date": report_date})
        for match in evaluation.get("goal_market_matches", []):
            current["goal_market_scored"].append({**match, "report_date": report_date})
    # A report-date + fixture ID pair is the stable identity for ledger rows.
    unique: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in current["scored_matches"]:
        try:
            key = (str(row["report_date"]), int(row["fixture_id"]), str(row.get("model", "unknown")))
        except (KeyError, TypeError, ValueError):
            continue
        unique[key] = row
    current["scored_matches"] = list(unique.values())
    unique_goal: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    for row in current["goal_market_scored"]:
        try:
            key = (str(row["report_date"]), int(row["fixture_id"]), str(row["market"]), str(row["selection"]))
        except (KeyError, TypeError, ValueError):
            continue
        unique_goal[key] = row
    current["goal_market_scored"] = list(unique_goal.values())
    current["goal_market_metrics"] = summarize_goal_market_paper(current["goal_market_scored"])
    current["goal_market_metrics_by_market"] = {
        market: summarize_goal_market_paper([row for row in current["goal_market_scored"] if row.get("market") == market])
        for market in sorted({str(row.get("market")) for row in current["goal_market_scored"]})
    }
    if should_merge_matches:
        report_matches = [
            row for row in current["scored_matches"]
            if str(row.get("report_date")) == str(report_date)
        ]
        report_metrics_by_model = {
            model_name: summarize_scored_matches([
                row for row in report_matches if str(row.get("model", "unknown")) == model_name
            ])
            for model_name in sorted({str(row.get("model", "unknown")) for row in report_matches})
        }
        if len(report_metrics_by_model) == 1:
            report_metrics = next(iter(report_metrics_by_model.values()))
        elif report_metrics_by_model:
            report_metrics = None
        else:
            report_metrics = summarize_scored_matches([])
        summary_index = next(
            index for index, row in enumerate(current["evaluations"])
            if str(row.get("report_date")) == str(report_date)
        )
        current["evaluations"][summary_index].update({
            "fixtures_scored": len({int(row["fixture_id"]) for row in report_matches}),
            "completed_forecasts_scored": len(report_matches),
            "metrics": report_metrics,
            "metrics_by_model": report_metrics_by_model,
            "model_versions": sorted(report_metrics_by_model),
        })
    current["product"] = "Veltrix Football"
    current["model_status"] = "PAPER_TRACKING_ONLY"
    model_names = sorted({str(row.get("model", "unknown")) for row in current["scored_matches"]})
    current["cumulative_metrics_by_model"] = {
        model_name: summarize_scored_matches([
            row for row in current["scored_matches"]
            if str(row.get("model", "unknown")) == model_name
        ])
        for model_name in model_names
    }
    # Do not publish one combined score as if it described a single model when
    # the ledger contains forecasts from different model versions.
    current["cumulative_metrics"] = (
        current["cumulative_metrics_by_model"][model_names[0]]
        if len(model_names) == 1
        else summarize_scored_matches(current["scored_matches"]) if not model_names
        else None
    )
    current["model_versions"] = model_names
    current["evaluated_report_dates"] = len(current["evaluations"])
    current["notice"] = "Retrospective paper evaluation only; no betting recommendation or profitability claim."
    return current


def _canonical_probabilities(probabilities: Any) -> dict[str, float] | None:
    if not isinstance(probabilities, dict):
        return None
    try:
        if all(key in probabilities for key in OUTCOMES):
            values = {key: float(probabilities[key]) for key in OUTCOMES}
        else:
            values = {
                "H": float(probabilities["home_win"]),
                "D": float(probabilities["draw"]),
                "A": float(probabilities["away_win"]),
            }
    except (KeyError, TypeError, ValueError):
        return None
    total = sum(values.values())
    if (
        any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values())
        or total <= 0
        or abs(total - 1.0) > 0.02
    ):
        return None
    # Rounded production probabilities may sum to 0.9999 or 1.0001. Normalize
    # small rounding drift so Brier score and log loss use a proper distribution.
    return {key: value / total for key, value in values.items()}


def _identity_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _identity_key(day: str, home: Any, away: Any) -> tuple[str, str, str] | None:
    home_key, away_key = _identity_name(home), _identity_name(away)
    if not day or not home_key or not away_key or home_key == away_key:
        return None
    return day, home_key, away_key


def _prediction_day(prediction: dict[str, Any], timezone_name: str) -> str | None:
    raw = prediction.get("kickoff_local") or prediction.get("kickoff")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        zone = ZoneInfo(timezone_name)
        kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=zone)
        return kickoff.astimezone(zone).date().isoformat()
    except (TypeError, ValueError, OverflowError, KeyError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed
    except (TypeError, ValueError, OverflowError):
        return None


def _goal_market_paper_rows(prediction: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Record only genuine, pre-kickoff BTTS/O-U prices for prospective paper ROI."""
    odds_snapshot = prediction.get("the_odds_api_market_odds")
    if not isinstance(odds_snapshot, dict):
        return []
    kickoff = _parse_timestamp(prediction.get("kickoff_local") or prediction.get("kickoff"))
    fetched = _parse_timestamp(odds_snapshot.get("fetched_at"))
    commence = _parse_timestamp(odds_snapshot.get("commence_time"))
    if not kickoff or not fetched or not commence or fetched >= kickoff or commence != kickoff:
        return []
    markets = odds_snapshot.get("markets")
    if not isinstance(markets, dict):
        return []
    outcomes = {
        "btts_yes": result["home_goals"] > 0 and result["away_goals"] > 0,
        "over_2_5": result["home_goals"] + result["away_goals"] >= 3,
    }
    model_probs = {
        "btts_yes": prediction.get("btts_yes"),
        "over_2_5": prediction.get("over_2_5"),
    }
    wanted = {
        "btts": {"yes": "Yes", "no": "No"},
        "totals": {"over_2_5": "Over", "under_2_5": "Under"},
    }
    rows = []
    for provider_market, selections in wanted.items():
        books = markets.get(provider_market)
        if not isinstance(books, list):
            continue
        for selection, outcome_label in selections.items():
            candidates = []
            for book in books:
                if not isinstance(book, dict):
                    continue
                quote_time = _parse_timestamp(book.get("last_update"))
                if quote_time and quote_time > kickoff:
                    continue
                if quote_time and (fetched - quote_time).total_seconds() > 24 * 3600:
                    continue
                for quote in book.get("outcomes") or []:
                    if not isinstance(quote, dict) or str(quote.get("name", "")).casefold() != outcome_label.casefold():
                        continue
                    try:
                        price = float(quote.get("price"))
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(price) and 1.01 <= price <= 100:
                        candidates.append((price, str(book.get("bookmaker") or "Unknown"), quote_time))
            if not candidates:
                continue
            # Best quoted price, chosen from the snapshot available before kickoff.
            price, bookmaker, quote_time = max(candidates, key=lambda item: item[0])
            model_market = "btts_yes" if provider_market == "btts" else "over_2_5"
            probability = model_probs[model_market]
            try:
                probability = float(probability)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                continue
            won = outcomes[model_market] if selection in {"yes", "over_2_5"} else not outcomes[model_market]
            rows.append({
                "fixture_id": prediction.get("fixture_id"),
                "home_team": prediction.get("home_team"),
                "away_team": prediction.get("away_team"),
                "market": provider_market,
                "selection": selection,
                "model_probability": probability if selection in {"yes", "over_2_5"} else 1 - probability,
                "decimal_odds": price,
                "implied_probability": 1 / price,
                "edge": (probability if selection in {"yes", "over_2_5"} else 1 - probability) - (1 / price),
                "bookmaker": bookmaker,
                "odds_provider": "The Odds API",
                "odds_fetched_at": fetched.isoformat(),
                "quote_updated_at": quote_time.isoformat() if quote_time else None,
                "kickoff": kickoff.isoformat(),
                "actual_outcome": bool(won),
                "unit_stake": 1.0,
                "unit_profit": round(price - 1, 6) if won else -1.0,
                "settlement": "WON" if won else "LOST",
                "model": str(prediction.get("goal_markets_model") or "experimental_recent_goals_poisson"),
            })
    return rows


def summarize_goal_market_paper(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize flat 1-unit paper returns; not a claim of executable betting profit."""
    count = len(rows)
    wins = sum(bool(row.get("actual_outcome")) for row in rows)
    profit = sum(float(row.get("unit_profit", 0)) for row in rows)
    stake = sum(float(row.get("unit_stake", 1)) for row in rows)
    return {
        "settled_selections": count,
        "wins": wins,
        "losses": count - wins,
        "win_rate": wins / count if count else None,
        "units_staked": stake,
        "net_units": profit,
        "paper_roi": profit / stake if stake else None,
        "notice": "Best quoted price in a pre-kickoff snapshot; flat 1-unit paper stakes; not proof of executable profit or bookmaker closing-line value.",
    }


def evaluate_report(report: dict[str, Any], results_payload: dict[str, Any]) -> dict[str, Any]:
    """Score every available model forecast by fixture ID against completed results."""
    predictions = report.get("predictions")
    results = results_payload.get("response")
    if not isinstance(predictions, list):
        raise ValueError("Prediction report must contain a predictions list.")
    if not isinstance(results, list):
        raise ValueError("Results payload must contain a response list.")

    completed: dict[int, dict[str, Any]] = {}
    identity_candidates: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in results:
        fixture = item.get("fixture") or {}
        fixture_id = fixture.get("id")
        status = (fixture.get("status") or {}).get("short")
        goals = item.get("goals") or {}
        home, away = goals.get("home"), goals.get("away")
        if (
            isinstance(fixture_id, int)
            and status in COMPLETED_STATUSES
            and isinstance(home, int) and not isinstance(home, bool) and home >= 0
            and isinstance(away, int) and not isinstance(away, bool) and away >= 0
        ):
            result_row = {
                "status": status,
                "home_goals": home,
                "away_goals": away,
                "actual": "H" if home > away else "A" if home < away else "D",
            }
            completed[fixture_id] = result_row
            teams = item.get("teams") or {}
            home_team = (teams.get("home") or {}).get("name")
            away_team = (teams.get("away") or {}).get("name")
            raw_date = str(fixture.get("date") or "")
            day = raw_date[:10]
            try:
                day = date.fromisoformat(day).isoformat()
            except ValueError:
                day = ""
            identity = _identity_key(day, home_team, away_team)
            if identity:
                identity_candidates.setdefault(identity, []).append(result_row)
    # Only use identity fallback when the exact home/away/date key is unique.
    completed_by_identity = {
        key: rows[0] for key, rows in identity_candidates.items() if len(rows) == 1
    }
    timezone_name = str(report.get("timezone") or "Africa/Lagos")

    scored: list[dict[str, Any]] = []
    goal_market_scored: list[dict[str, Any]] = []
    awaiting_result = 0
    withheld = 0
    missing_fixture_id = 0
    fixtures_scored: set[int] = set()
    for prediction in predictions:
        status = prediction.get("status")
        has_model_forecast = status == "EXPERIMENTAL_ONLY"
        has_market_forecast = isinstance(prediction.get("market_probabilities"), dict)
        if status in {"INSUFFICIENT_HISTORY", "UNSUPPORTED_COMPETITION"}:
            withheld += 1
        if not has_model_forecast and not has_market_forecast:
            continue
        fixture_id = prediction.get("fixture_id")
        if not isinstance(fixture_id, int):
            missing_fixture_id += 1
            continue
        result = completed.get(fixture_id)
        if result is None:
            identity = _identity_key(
                _prediction_day(prediction, timezone_name) or "",
                prediction.get("home_team"), prediction.get("away_team"),
            )
            result = completed_by_identity.get(identity) if identity else None
        if result is None:
            awaiting_result += 1
            continue

        goal_market_scored.extend(_goal_market_paper_rows(prediction, result))

        forecast_models: list[tuple[str, Any]] = []
        if has_model_forecast:
            forecast_models.append((
                str(prediction.get("model", "unknown")),
                prediction.get("probabilities"),
            ))
            # Support both report layouts: Poisson primary + Elo alternative, or
            # competition Elo primary + Poisson alternative.
            if isinstance(prediction.get("elo_probabilities"), dict):
                forecast_models.append((
                    str(prediction.get("elo_model", "experimental_elo_unknown")),
                    prediction.get("elo_probabilities"),
                ))
            if isinstance(prediction.get("poisson_probabilities"), dict):
                forecast_models.append((
                    str(prediction.get("poisson_model", "experimental_poisson_unknown")),
                    prediction.get("poisson_probabilities"),
                ))
        if has_market_forecast:
            forecast_models.append(("market_consensus", prediction.get("market_probabilities")))

        scored_this_fixture = False
        for model_name, raw_probabilities in forecast_models:
            values = _canonical_probabilities(raw_probabilities)
            if values is None:
                withheld += 1
                continue
            actual = result["actual"]
            scored_row = {
                "fixture_id": fixture_id,
                "model": model_name,
                "home_team": prediction.get("home_team"),
                "away_team": prediction.get("away_team"),
                "actual": actual,
                "predicted": max(values, key=values.get),
                "probabilities": values,
                "correct": max(values, key=values.get) == actual,
                "home_goals": result["home_goals"],
                "away_goals": result["away_goals"],
            }
            if model_name == "market_consensus":
                scored_row["market_updated_at"] = prediction.get("market_updated_at")
                scored_row["market_bookmakers_count"] = prediction.get("market_bookmakers_count", 0)
                scored_row["market_method"] = prediction.get("market_method")
            scored.append(scored_row)
            scored_this_fixture = True
        if scored_this_fixture:
            fixtures_scored.add(fixture_id)

    metrics_by_model = {
        model_name: summarize_scored_matches([
            row for row in scored if row["model"] == model_name
        ])
        for model_name in sorted({row["model"] for row in scored})
    }
    metrics = (
        next(iter(metrics_by_model.values())) if len(metrics_by_model) == 1
        else None if len(metrics_by_model) > 1
        else summarize_scored_matches([])
    )

    return {
        "product": report.get("product", "Veltrix Football"),
        "report_date": report.get("as_of_date"),
        "model_status": "PAPER_TRACKING_ONLY",
        "predictions_in_report": len(predictions),
        "fixtures_scored": len(fixtures_scored),
        "unique_fixtures_scored": len(fixtures_scored),
        "completed_forecasts_scored": len(scored),
        "awaiting_result_or_match": awaiting_result,
        "withheld_or_invalid_forecasts": withheld,
        "forecasts_missing_fixture_id": missing_fixture_id,
        "metrics": metrics,
        "metrics_by_model": metrics_by_model,
        "matches": scored,
        "goal_market_matches": goal_market_scored,
        "goal_market_metrics": summarize_goal_market_paper(goal_market_scored),
        "notice": "Retrospective 1X2 scoring plus prospective pre-kickoff BTTS/Over 2.5 paper tracking only; no betting recommendation or profitability claim.",
    }
