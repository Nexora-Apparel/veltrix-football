"""Independent competition-scoped Poisson/Dixon-Coles goal model.

Fits attack/defence strengths from settled historical scores. Research-only:
artifacts and predictions are never publication- or betting-authorized.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any


MODEL_FAMILY = "veltrix-independent-poisson-dixon-coles-v1"
_EPS = 1e-12


class PoissonModelError(ValueError):
    pass


def _dt(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise PoissonModelError(f"{name}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PoissonModelError(f"{name}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PoissonModelError(f"{name}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode()).hexdigest()


def _finite_number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PoissonModelError(f"{name}_invalid")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise PoissonModelError(f"{name}_out_of_range")
    return result


def _tau(h: int, a: int, lam: float, mu: float, rho: float) -> float:
    if h == 0 and a == 0:
        return 1.0 - lam * mu * rho
    if h == 0 and a == 1:
        return 1.0 + lam * rho
    if h == 1 and a == 0:
        return 1.0 + mu * rho
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


def _fit_competition(rows: list[dict], *, l2: float, iterations: int,
                     learning_rate: float) -> dict:
    teams = sorted({r["home_team_id"] for r in rows} |
                   {r["away_team_id"] for r in rows})
    index = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    # theta = home intercept, away intercept, attack[n], defence[n].
    theta = [0.0, 0.0] + [0.0] * (2 * n)
    home_mean = sum(r["home_score"] for r in rows) / len(rows)
    away_mean = sum(r["away_score"] for r in rows) / len(rows)
    if home_mean <= 0 or away_mean <= 0:
        raise PoissonModelError("competition_goal_rate_nonpositive")
    theta[0], theta[1] = math.log(home_mean), math.log(away_mean)

    for _ in range(iterations):
        grad = [0.0] * len(theta)
        for row in rows:
            hi, ai = index[row["home_team_id"]], index[row["away_team_id"]]
            ha, hd = 2 + hi, 2 + n + ai
            aa, ad = 2 + ai, 2 + n + hi
            log_h = theta[0] + theta[ha] - theta[hd]
            log_a = theta[1] + theta[aa] - theta[ad]
            # Guard exponentiation against unstable optimizer excursions.
            lam, mu = math.exp(max(-3.0, min(3.0, log_h))), math.exp(max(-3.0, min(3.0, log_a)))
            weight = row["_weight"]
            grad[0] += weight * (lam - row["home_score"])
            grad[1] += weight * (mu - row["away_score"])
            grad[ha] += weight * (lam - row["home_score"])
            grad[hd] -= weight * (lam - row["home_score"])
            grad[aa] += weight * (mu - row["away_score"])
            grad[ad] -= weight * (mu - row["away_score"])
        for j in range(2, len(theta)):
            grad[j] += l2 * theta[j]
        scale = 1.0 / len(rows)
        for j in range(len(theta)):
            theta[j] -= learning_rate * grad[j] * scale

        # Identifiability: center attack and defence independently.
        attack_mean = sum(theta[2:2+n]) / n
        defence_mean = sum(theta[2+n:]) / n
        for j in range(2, 2+n):
            theta[j] -= attack_mean
        for j in range(2+n, 2+2*n):
            theta[j] -= defence_mean

    return {
        "home_intercept": theta[0], "away_intercept": theta[1],
        "attack": {team: theta[2 + index[team]] for team in teams},
        "defence": {team: theta[2 + n + index[team]] for team in teams},
        "team_count": n,
    }


def _rates(params: dict, home: str, away: str) -> tuple[float, float]:
    attack, defence = params["attack"], params["defence"]
    if home not in attack or away not in attack:
        raise PoissonModelError("team_unseen_in_training")
    lh = params["home_intercept"] + attack[home] - defence[away]
    la = params["away_intercept"] + attack[away] - defence[home]
    lam, mu = math.exp(lh), math.exp(la)
    if not (0.05 <= lam <= 8.0 and 0.05 <= mu <= 8.0):
        raise PoissonModelError("expected_goals_outside_supported_range")
    return lam, mu


def _fit_rho(rows: list[dict], params_by_comp: dict, max_abs_rho: float) -> float:
    # Profile likelihood over a deterministic grid; no test partition is accepted.
    candidates = [round(-max_abs_rho + i * (2 * max_abs_rho / 100), 8)
                  for i in range(101)]
    best_rho, best_ll = 0.0, -math.inf
    # Require every low-score correction to remain nonnegative for every
    # known home/away team pairing, not merely the observed score in-sample.
    pair_rates = []
    for comp, params in params_by_comp.items():
        teams = sorted(params["attack"])
        for home in teams:
            for away in teams:
                if home != away:
                    pair_rates.append(_rates(params, home, away))
    for rho in candidates:
        valid = all(
            min(1.0 - lam * mu * rho, 1.0 + lam * rho,
                1.0 + mu * rho, 1.0 - rho) > 0
            for lam, mu in pair_rates
        )
        if not valid:
            continue
        ll = 0.0
        for row in rows:
            lam, mu = _rates(params_by_comp[row["competition_key"]],
                             row["home_team_id"], row["away_team_id"])
            tau = _tau(row["home_score"], row["away_score"], lam, mu, rho)
            # The independent Poisson terms do not vary with rho; tau is
            # the Dixon-Coles likelihood contribution.
            ll += row["_weight"] * math.log(tau)
        if ll > best_ll:
            best_rho, best_ll = rho, ll
    if not math.isfinite(best_ll):
        raise PoissonModelError("no_valid_dixon_coles_rho")
    return best_rho


def _poisson_pmf(rate: float, max_goals: int) -> list[float]:
    values = [math.exp(-rate)]
    for goals in range(1, max_goals + 1):
        values.append(values[-1] * rate / goals)
    return values


def _independent_dixon_coles_markets(lam: float, mu: float, *, rho: float,
                                     max_goals: int) -> dict:
    """Build score-grid probabilities locally; never call the legacy prediction head."""
    if not (math.isfinite(lam) and math.isfinite(mu) and 0 < lam <= 10 and 0 < mu <= 10):
        raise PoissonModelError("expected_goals_outside_supported_range")
    if (isinstance(max_goals, bool) or not isinstance(max_goals, int)
            or not 12 <= max_goals <= 40):
        raise PoissonModelError("max_goals_out_of_range")
    if not math.isfinite(rho) or not -0.25 <= rho <= 0.25:
        raise PoissonModelError("rho_out_of_range")

    hp, ap = _poisson_pmf(lam, max_goals), _poisson_pmf(mu, max_goals)
    tail_home = max(0.0, 1.0 - sum(hp))
    tail_away = max(0.0, 1.0 - sum(ap))
    tail_bound = min(1.0, tail_home + tail_away)
    if tail_bound > 1e-8:
        raise PoissonModelError("score_grid_truncation_too_large")

    grid = []
    for home_goals, home_probability in enumerate(hp):
        row = []
        for away_goals, away_probability in enumerate(ap):
            tau = _tau(home_goals, away_goals, lam, mu, rho)
            if not math.isfinite(tau) or tau < 0:
                raise PoissonModelError("invalid_dixon_coles_low_score_probability")
            row.append(home_probability * away_probability * tau)
        grid.append(row)

    mass = sum(sum(row) for row in grid)
    if not math.isfinite(mass) or mass <= 0:
        raise PoissonModelError("score_probability_mass_invalid")
    grid = [[probability / mass for probability in row] for row in grid]

    home_win = draw = away_win = btts_yes = 0.0
    totals_over = {line: 0.0 for line in (0.5, 1.5, 2.5, 3.5, 4.5)}
    scorelines = []
    for home_goals, row in enumerate(grid):
        for away_goals, probability in enumerate(row):
            if home_goals > away_goals:
                home_win += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away_win += probability
            if home_goals > 0 and away_goals > 0:
                btts_yes += probability
            for line in totals_over:
                if home_goals + away_goals > line:
                    totals_over[line] += probability
            scorelines.append((probability, home_goals, away_goals))

    return {
        "status": "SHADOW_RESEARCH",
        "expected_goals": {"home_lambda": lam, "away_mu": mu},
        "rho": rho,
        "max_goals": max_goals,
        "truncated_poisson_tail_estimate": {
            "home": tail_home, "away": tail_away, "upper_bound_union": tail_bound,
        },
        "markets": {
            "1x2": {"H": home_win, "D": draw, "A": away_win},
            "btts": {"yes": btts_yes, "no": 1.0 - btts_yes},
            "totals": {
                str(line): {"over": probability, "under": 1.0 - probability}
                for line, probability in sorted(totals_over.items())
            },
        },
        "top_scorelines": [
            {"score": f"{home_goals}-{away_goals}", "probability": probability}
            for probability, home_goals, away_goals
            in sorted(scorelines, reverse=True)[:10]
        ],
    }


def fit_poisson_dixon_coles(*, history: list[dict], training_cutoff: str,
                            trained_at: str, dataset_sha256: str,
                            train_fixture_ids: list[str], validation_fixture_ids: list[str],
                            test_fixture_ids: list[str], l2: float = 0.15,
                            iterations: int = 2500, learning_rate: float = 0.025,
                            time_decay_days: float | None = None,
                            rho_bound: float = 0.15) -> dict:
    """Fit from training rows only; split manifests bind the resulting artifact.

    Rows require competition_key, fixture_id, kickoff_at, settled_at,
    home_team_id, away_team_id, home_score, away_score and source_record_sha256.
    Validation/test IDs are recorded but their rows must not be supplied.
    """
    cutoff, fit_time = _dt(training_cutoff, "training_cutoff"), _dt(trained_at, "trained_at")
    if fit_time <= cutoff:
        raise PoissonModelError("training_timestamp_must_follow_cutoff")
    if (not isinstance(dataset_sha256, str) or len(dataset_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in dataset_sha256)):
        raise PoissonModelError("dataset_digest_invalid")
    for name, ids in (("train", train_fixture_ids), ("validation", validation_fixture_ids),
                      ("test", test_fixture_ids)):
        if not isinstance(ids, list) or len(ids) != len(set(ids)) or any(not isinstance(x, str) or not x for x in ids):
            raise PoissonModelError(f"{name}_manifest_invalid")
    if set(train_fixture_ids) & (set(validation_fixture_ids) | set(test_fixture_ids)) or set(validation_fixture_ids) & set(test_fixture_ids):
        raise PoissonModelError("split_manifests_overlap")
    l2 = _finite_number(l2, "l2", 0.0, 100.0)
    learning_rate = _finite_number(learning_rate, "learning_rate", 0.0001, 0.2)
    rho_bound = _finite_number(rho_bound, "rho_bound", 0.001, 0.25)
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not 100 <= iterations <= 20000:
        raise PoissonModelError("iterations_out_of_range")
    if time_decay_days is not None:
        time_decay_days = _finite_number(time_decay_days, "time_decay_days", 30.0, 3650.0)
    if not isinstance(history, list) or len(history) < 100:
        raise PoissonModelError("minimum_100_training_rows_required")
    required = {"competition_key", "fixture_id", "kickoff_at", "settled_at",
                "home_team_id", "away_team_id", "home_score", "away_score",
                "source_record_sha256"}
    clean, seen = [], set()
    for i, row in enumerate(history):
        if not isinstance(row, dict) or set(row) != required:
            raise PoissonModelError(f"history_shape_invalid:{i}")
        if row["fixture_id"] in seen or row["fixture_id"] not in train_fixture_ids:
            raise PoissonModelError(f"training_manifest_mismatch:{row['fixture_id']}")
        seen.add(row["fixture_id"])
        kickoff, settled = _dt(row["kickoff_at"], "kickoff_at"), _dt(row["settled_at"], "settled_at")
        if settled <= kickoff or settled > cutoff or settled > fit_time:
            raise PoissonModelError(f"label_temporal_order_invalid:{row['fixture_id']}")
        if row["home_team_id"] == row["away_team_id"]:
            raise PoissonModelError("same_team_fixture")
        for key in ("home_score", "away_score"):
            if isinstance(row[key], bool) or not isinstance(row[key], int) or not 0 <= row[key] <= 15:
                raise PoissonModelError(f"score_invalid:{row['fixture_id']}")
        digest = row["source_record_sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise PoissonModelError(f"source_digest_invalid:{row['fixture_id']}")
        age_days = max(0.0, (cutoff - settled).total_seconds() / 86400)
        weight = math.exp(-age_days / time_decay_days) if time_decay_days else 1.0
        clean.append({**row, "_settled": settled, "_weight": weight})
    if seen != set(train_fixture_ids):
        raise PoissonModelError("training_rows_do_not_match_train_manifest")
    by_comp: dict[str, list[dict]] = {}
    for row in clean:
        by_comp.setdefault(row["competition_key"], []).append(row)
    params = {}
    for comp, rows in sorted(by_comp.items()):
        if len(rows) < 30:
            raise PoissonModelError(f"competition_training_rows_below_30:{comp}")
        params[comp] = _fit_competition(rows, l2=l2, iterations=iterations,
                                       learning_rate=learning_rate)
    rho = _fit_rho(clean, params, rho_bound)
    artifact = {
        "schema_version": 1, "model_family": MODEL_FAMILY,
        "dataset_sha256": dataset_sha256,
        "train_fixture_ids": sorted(train_fixture_ids),
        "validation_fixture_ids": sorted(validation_fixture_ids),
        "test_fixture_ids": sorted(test_fixture_ids),
        "train_fixture_manifest_sha256": _sha(sorted(train_fixture_ids)),
        "validation_fixture_manifest_sha256": _sha(sorted(validation_fixture_ids)),
        "test_fixture_manifest_sha256": _sha(sorted(test_fixture_ids)),
        "training_cutoff": training_cutoff, "trained_at": trained_at,
        "training_row_count": len(clean), "competition_count": len(params),
        "time_decay_days": time_decay_days,
        "config": {"l2": l2, "iterations": iterations,
                   "learning_rate": learning_rate, "rho_bound": rho_bound},
        "rho": rho, "competitions": params,
        "training_source_digest": _sha([
            {"fixture_id": r["fixture_id"], "source_record_sha256": r["source_record_sha256"]}
            for r in sorted(clean, key=lambda x: x["fixture_id"])
        ]),
        "publication_allowed": False, "value_betting_enabled": False,
    }
    artifact["artifact_sha256"] = _sha(artifact)
    return artifact


def predict_poisson_dixon_coles(*, artifact: dict, fixture: dict,
                                max_goals: int = 20) -> dict:
    """Predict from a sealed artifact for a strictly pre-kickoff feature snapshot."""
    if not isinstance(artifact, dict) or artifact.get("model_family") != MODEL_FAMILY:
        raise PoissonModelError("model_family_invalid")
    supplied = dict(artifact)
    digest = supplied.pop("artifact_sha256", None)
    if not isinstance(digest, str) or digest != _sha(supplied):
        raise PoissonModelError("artifact_digest_mismatch")
    kickoff = _dt(fixture.get("kickoff_at"), "fixture_kickoff")
    feature_as_of = _dt(fixture.get("feature_as_of"), "feature_as_of")
    trained_at = _dt(artifact.get("trained_at"), "trained_at")
    cutoff = _dt(artifact.get("training_cutoff"), "training_cutoff")
    if feature_as_of >= kickoff or trained_at > feature_as_of or cutoff >= kickoff:
        raise PoissonModelError("prediction_temporal_order_invalid")
    comp = fixture.get("competition_key")
    if comp not in artifact["competitions"]:
        raise PoissonModelError("competition_unseen_in_training")
    lam, mu = _rates(artifact["competitions"][comp],
                     fixture.get("home_team_id"), fixture.get("away_team_id"))
    markets = _independent_dixon_coles_markets(lam, mu, rho=artifact["rho"], max_goals=max_goals)
    return {
        "fixture_id": fixture.get("fixture_id"),
        "model_family": MODEL_FAMILY,
        "expected_goals": markets["expected_goals"],
        "markets": markets["markets"],
        "top_scorelines": markets["top_scorelines"],
        "artifact_sha256": digest,
        "publication_allowed": False, "value_betting_enabled": False,
    }
