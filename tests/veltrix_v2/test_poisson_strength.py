from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.models.poisson_strength import TrainingMatch, fit_poisson_strength_model


BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def build_rows():
    rows = []
    # Synthetic deterministic league: A strong attack, B weak attack, C balanced.
    strengths = {"A": (0.55, -0.15), "B": (-0.45, 0.20), "C": (-0.10, -0.05)}
    fixture = 0
    for week in range(18):
        for home, away in (("A", "B"), ("B", "C"), ("C", "A")):
            fixture += 1
            ah, dh = strengths[home]
            aa, da = strengths[away]
            home_rate = 1.35 * 1.18 * __import__("math").exp(ah - da)
            away_rate = 1.35 * __import__("math").exp(aa - dh)
            # Fixed score pattern preserves a learnable signal without randomness.
            hg = max(0, round(home_rate + ((week % 3) - 1) * 0.2))
            ag = max(0, round(away_rate + (((week + 1) % 3) - 1) * 0.2))
            kickoff = BASE + timedelta(days=week * 7 + fixture % 3)
            rows.append(TrainingMatch(
                f"f{fixture}", "league", "2024/25", kickoff,
                kickoff + timedelta(hours=4), home, away, hg, ag, f"obs{fixture}",
            ))
    return rows


def test_fit_is_deterministic_and_produces_positive_rates():
    rows = build_rows()
    cutoff = BASE + timedelta(days=150)
    model = fit_poisson_strength_model(
        rows, competition_key="league", season="2024/25",
        training_cutoff_utc=cutoff, minimum_matches=30,
        minimum_team_matches=10, max_iterations=4000,
    )
    assert model.training_match_count == 54
    assert model.training_team_count == 3
    assert model.training_fixture_ids
    assert model.converged is True
    home, away = model.expected_goals("A", "B")
    assert home > 0 and away > 0
    again = fit_poisson_strength_model(
        rows, competition_key="league", season="2024/25",
        training_cutoff_utc=cutoff, minimum_matches=30,
        minimum_team_matches=10, max_iterations=4000,
    )
    assert model == again


def test_future_or_unavailable_results_never_enter_training():
    rows = build_rows()
    cutoff = BASE + timedelta(days=150)
    rows.extend([
        TrainingMatch("future", "league", "2024/25", cutoff + timedelta(days=1),
                      cutoff + timedelta(days=2), "A", "B", 9, 0, "future-obs"),
        TrainingMatch("late", "league", "2024/25", BASE + timedelta(days=20),
                      cutoff + timedelta(days=1), "A", "B", 8, 0, "late-obs"),
    ])
    model = fit_poisson_strength_model(
        rows, competition_key="league", season="2024/25",
        training_cutoff_utc=cutoff, minimum_matches=30, minimum_team_matches=10,
        max_iterations=4000,
    )
    assert "future" not in model.training_fixture_ids
    assert "late" not in model.training_fixture_ids


def test_quarantined_and_other_competition_rows_are_excluded():
    rows = build_rows()
    row = rows[0]
    rows.extend([
        TrainingMatch("quarantine", "league", "2024/25", row.kickoff_utc,
                      row.available_at_utc, "A", "B", 10, 0, "qobs", "quarantined"),
        TrainingMatch("other", "other-league", "2024/25", row.kickoff_utc,
                      row.available_at_utc, "A", "B", 10, 0, "oobs"),
    ])
    model = fit_poisson_strength_model(
        rows, competition_key="league", season="2024/25",
        training_cutoff_utc=BASE + timedelta(days=150), minimum_matches=30,
        minimum_team_matches=10, max_iterations=4000,
    )
    assert model.training_match_count == 54


def test_insufficient_training_data_fails_closed():
    with pytest.raises(ValueError, match="INSUFFICIENT_MATCHES"):
        fit_poisson_strength_model(
            build_rows()[:3], competition_key="league", season="2024/25",
            training_cutoff_utc=BASE + timedelta(days=150), minimum_matches=30,
        )


def test_naive_cutoff_and_duplicate_provenance_are_rejected():
    with pytest.raises(ValueError, match="CUTOFF_MUST_BE_AWARE"):
        fit_poisson_strength_model(build_rows(), competition_key="league", season="2024/25",
                                   training_cutoff_utc=datetime(2025, 7, 1))
    rows = build_rows()
    rows.append(rows[0])
    with pytest.raises(ValueError, match="DUPLICATE_PROVENANCE"):
        fit_poisson_strength_model(rows, competition_key="league", season="2024/25",
                                   training_cutoff_utc=BASE + timedelta(days=150),
                                   minimum_matches=30, minimum_team_matches=10)


def test_unseen_team_is_not_given_a_generic_fallback():
    model = fit_poisson_strength_model(
        build_rows(), competition_key="league", season="2024/25",
        training_cutoff_utc=BASE + timedelta(days=150), minimum_matches=30,
        minimum_team_matches=10, max_iterations=4000,
    )
    with pytest.raises(ValueError, match="TEAM_NOT_IN_TRAINING"):
        model.expected_goals("A", "UNSEEN")



def test_training_contract_excludes_popularity_reputation_and_market_favourites():
    from dataclasses import fields

    accepted_fields = {field.name for field in fields(TrainingMatch)}
    prohibited = {
        "team_name", "team_popularity", "fanbase_size", "social_engagement",
        "reputation", "club_rank", "league_prestige", "bookmaker_odds",
        "implied_probability", "market_favourite", "public_betting_percentage",
    }
    assert accepted_fields.isdisjoint(prohibited)


def test_home_advantage_is_a_fitted_parameter_not_a_hard_coded_bonus():
    rows = build_rows()
    cutoff = BASE + timedelta(days=150)
    model = fit_poisson_strength_model(
        rows, competition_key="league", season="2024/25",
        training_cutoff_utc=cutoff, minimum_matches=30,
        minimum_team_matches=10, max_iterations=4000,
    )
    # The model exposes the coefficient learned from this training sample;
    # it does not inject a fixed percentage into every home forecast.
    assert isinstance(model.home_advantage_log_rate, float)
    assert model.home_advantage_log_rate != pytest.approx(__import__("math").log(1.18), abs=1e-3)
