"""Chronological calibration diagnostics; never mutate production probabilities."""
from __future__ import annotations
import math
from typing import Any


def rolling_origin_1x2_temperature(rows: list[dict[str, Any]], probability_key: str, *, folds: int = 4, min_training_matches: int = 1000, min_test_matches: int = 200) -> dict[str, Any]:
    """Fit multiclass temperature on prior dates and score disjoint future folds."""
    clean = []
    for row in rows:
        raw = row.get(probability_key)
        if not isinstance(raw, dict) or row.get("actual") not in {"H", "D", "A"} or not row.get("match_date"):
            continue
        try:
            p = {k: float(raw[k]) for k in ("H", "D", "A")}
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        total = sum(p.values())
        if any(not math.isfinite(v) or v <= 0 or v > 1 for v in p.values()) or not 0.98 <= total <= 1.02:
            continue
        clean.append({**row, probability_key: {k: v / total for k, v in p.items()}})
    dates = sorted({str(r["match_date"]) for r in clean})
    base = {"status": "ROLLING_ORIGIN_DIAGNOSTIC_ONLY", "method": "expanding date-ordered training; fixed temperature grid; non-overlapping future folds", "probability_model": probability_key, "folds_requested": folds, "folds_evaluated": 0, "calibration_applied_to_live": False, "betting_validation": False}
    if folds < 2 or len(dates) < folds + 2:
        return {**base, "status": "INSUFFICIENT_DATES", "folds": []}

    def apply(p, t):
        logits = {k: math.log(max(1e-12, p[k])) / t for k in ("H", "D", "A")}
        peak = max(logits.values())
        exps = {k: math.exp(logits[k] - peak) for k in logits}
        total = sum(exps.values())
        return {k: exps[k] / total for k in exps}

    def blend(model, market, model_weight):
        return {k: model_weight * model[k] + (1.0 - model_weight) * market[k] for k in ("H", "D", "A")}

    def score(items, temperature=None):
        if not items:
            return {"matches": 0, "brier_score": None, "log_loss": None, "accuracy": None}
        brier = loss = correct = 0.0
        for row in items:
            p = row[probability_key] if temperature is None else apply(row[probability_key], temperature)
            y = row["actual"]
            brier += sum((p[k] - float(k == y)) ** 2 for k in ("H", "D", "A"))
            loss -= math.log(max(1e-15, p[y]))
            correct += int(max(p, key=p.get) == y)
        n = len(items)
        return {"matches": n, "brier_score": brier / n, "log_loss": loss / n, "accuracy": correct / n}

    starts = sorted(set(min(len(dates) - 1, int(len(dates) * (0.5 + 0.1 * i))) for i in range(folds)))
    results, all_test, all_cal, all_market, all_market_cal, all_blend_cal = [], [], [], [], [], []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(dates)
        train_days, test_days = set(dates[:start]), set(dates[start:end])
        train = [r for r in clean if str(r["match_date"]) in train_days]
        test = [r for r in clean if str(r["match_date"]) in test_days]
        if len(train) < min_training_matches or len(test) < min_test_matches:
            results.append({"fold": index + 1, "status": "INSUFFICIENT_MATCHES", "training_matches": len(train), "test_matches": len(test)})
            continue
        best_t, best_loss = 1.0, float("inf")
        for step in range(10, 61):
            t = step / 20.0
            value = score(train, t)["log_loss"]
            if value < best_loss:
                best_t, best_loss = t, value
        raw, cal = score(test), score(test, best_t)
        train_market = [r for r in train if isinstance(r.get("market"), dict)]
        market_rows = [r for r in test if isinstance(r.get("market"), dict)]
        market = score([{**r, probability_key: r["market"]} for r in market_rows]) if market_rows else None
        best_alpha, best_blend_loss = 0.0, float("inf")
        for step in range(0, 41):
            alpha = step / 40.0
            blend_loss = 0.0
            for row in train_market:
                p = blend(row[probability_key], row["market"], alpha)
                blend_loss -= math.log(max(1e-15, p[row["actual"]]))
            if train_market:
                blend_loss /= len(train_market)
                if blend_loss < best_blend_loss:
                    best_alpha, best_blend_loss = alpha, blend_loss
        blended_rows = [{**r, probability_key: blend(r[probability_key], r["market"], best_alpha)} for r in market_rows]
        blended = score(blended_rows) if blended_rows else None
        all_market.extend(market_rows)
        all_market_cal.extend((r, best_t) for r in market_rows)
        all_blend_cal.extend((r, best_alpha) for r in market_rows)
        results.append({"fold": index + 1, "status": "EVALUATED", "training_matches": len(train), "test_matches": len(test), "training_end": dates[start - 1], "test_start": dates[start], "test_end": dates[end - 1], "temperature": best_t, "training_log_loss": best_loss, "raw": raw, "calibrated": cal, "market_same_fixtures": market, "market_blend_model_weight": best_alpha, "market_blend_training_log_loss": best_blend_loss if train_market else None, "market_blend_same_fixtures": blended, "market_blend_beats_market": bool(blended and market and blended["brier_score"] < market["brier_score"] and blended["log_loss"] < market["log_loss"]), "improved_brier_and_log_loss": cal["brier_score"] < raw["brier_score"] and cal["log_loss"] < raw["log_loss"]})
        all_test.extend(test)
        all_cal.extend((r, best_t) for r in test)
    evaluated = [r for r in results if r["status"] == "EVALUATED"]
    raw_total = score(all_test) if all_test else None
    cal_total = None
    if all_cal:
        brier = loss = correct = 0.0
        for row, t in all_cal:
            p, y = apply(row[probability_key], t), row["actual"]
            brier += sum((p[k] - float(k == y)) ** 2 for k in ("H", "D", "A"))
            loss -= math.log(max(1e-15, p[y]))
            correct += int(max(p, key=p.get) == y)
        n = len(all_cal)
        cal_total = {"matches": n, "brier_score": brier / n, "log_loss": loss / n, "accuracy": correct / n}
    market_total = score([{**r, probability_key: r["market"]} for r in all_market]) if all_market else None
    market_cal_total = None
    if all_market_cal:
        brier = loss = correct = 0.0
        for row, t in all_market_cal:
            p, y = apply(row[probability_key], t), row["actual"]
            brier += sum((p[k] - float(k == y)) ** 2 for k in ("H", "D", "A"))
            loss -= math.log(max(1e-15, p[y]))
            correct += int(max(p, key=p.get) == y)
        n = len(all_market_cal)
        market_cal_total = {"matches": n, "brier_score": brier / n, "log_loss": loss / n, "accuracy": correct / n}
    beats_market = bool(market_total and market_cal_total and
        market_cal_total["brier_score"] < market_total["brier_score"] and
        market_cal_total["log_loss"] < market_total["log_loss"])
    market_blend_total = None
    if all_blend_cal:
        brier = loss = correct = 0.0
        for row, alpha in all_blend_cal:
            p, y = blend(row[probability_key], row["market"], alpha), row["actual"]
            brier += sum((p[k] - float(k == y)) ** 2 for k in ("H", "D", "A"))
            loss -= math.log(max(1e-15, p[y]))
            correct += int(max(p, key=p.get) == y)
        n = len(all_blend_cal)
        market_blend_total = {"matches": n, "brier_score": brier / n, "log_loss": loss / n, "accuracy": correct / n}
    blend_beats_market = bool(market_total and market_blend_total and
        market_blend_total["brier_score"] < market_total["brier_score"] and
        market_blend_total["log_loss"] < market_total["log_loss"])
    return {**base, "folds": results, "folds_evaluated": len(evaluated), "raw": raw_total, "calibrated": cal_total,
            "market_on_same_odds_covered_fixtures": market_total,
            "calibrated_on_same_odds_covered_fixtures": market_cal_total,
            "beats_market_on_same_fixtures": beats_market,
            "market_anchor_blend_on_same_fixtures": market_blend_total,
            "market_anchor_blend_beats_market": blend_beats_market,
            "calibration_diagnostic_pass": len(evaluated) == folds and all(r["improved_brier_and_log_loss"] for r in evaluated),
            "note": "A calibration pass does not establish market-beating skill or betting profitability; fitted temperatures are not applied to production."}
