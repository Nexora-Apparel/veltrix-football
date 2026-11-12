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
                availability_basis="source_timestamp", source_training_approved=True,
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
    assert __import__("math").isfinite(model.home_advantage_log_rate)
    assert model.training_match_count == 54


def test_unspecified_availability_basis_cannot_enter_training():
    rows = build_rows()
    rows[0] = TrainingMatch(
        rows[0].fixture_id, rows[0].competition_key, rows[0].season,
        rows[0].kickoff_utc, rows[0].available_at_utc, rows[0].home_team_id,
        rows[0].away_team_id, rows[0].home_goals, rows[0].away_goals,
        rows[0].source_observation_id, availability_basis="unspecified",
    )
    with pytest.raises(ValueError, match="AVAILABILITY_BASIS_REQUIRED"):
        fit_poisson_strength_model(
            rows, competition_key="league", season="2024/25",
            training_cutoff_utc=BASE + timedelta(days=150),
            minimum_matches=30, minimum_team_matches=10,
        )


def test_unapproved_source_cannot_enter_model_training():
    rows = build_rows()
    rows[0] = TrainingMatch(
        rows[0].fixture_id, rows[0].competition_key, rows[0].season,
        rows[0].kickoff_utc, rows[0].available_at_utc, rows[0].home_team_id,
        rows[0].away_team_id, rows[0].home_goals, rows[0].away_goals,
        rows[0].source_observation_id, availability_basis="source_timestamp",
        source_training_approved=False,
    )
    with pytest.raises(ValueError, match="SOURCE_NOT_APPROVED"):
        fit_poisson_strength_model(
            rows, competition_key="league", season="2024/25",
            training_cutoff_utc=BASE + timedelta(days=150),
            minimum_matches=30, minimum_team_matches=10,
        )



def test_single_prior_match_team_is_accepted_without_generic_fallback():
    rows = build_rows()
    kickoff = BASE + timedelta(days=80)
    rows.append(TrainingMatch(
        "rare-team-one-match", "league", "2024/25", kickoff,
        kickoff + timedelta(hours=4), "RARE", "A", 1, 0,
        "obs-rare-team", availability_basis="source_timestamp",
        source_training_approved=True,
    ))
    model = fit_poisson_strength_model(
        rows, competition_key="league", season="2024/25",
        training_cutoff_utc=BASE + timedelta(days=150),
        minimum_matches=30, max_iterations=4000,
    )
    assert model.training_match_count == 55
    assert model.expected_goals("RARE", "A")[0] > 0
    with pytest.raises(ValueError, match="TEAM_NOT_IN_TRAINING"):
        model.expected_goals("A", "NO_HISTORY")



def test_nonconverged_model_cannot_emit_expected_goals():
    from dataclasses import replace

    model = fit_poisson_strength_model(
        build_rows(), competition_key="league", season="2024/25",
        training_cutoff_utc=BASE + timedelta(days=150), minimum_matches=30,
        minimum_team_matches=10, max_iterations=4000,
    )
    unfit = replace(model, converged=False)
    with pytest.raises(ValueError, match="MODEL_NOT_CONVERGED"):
        unfit.expected_goals("A", "B")



def test_training_order_does_not_change_fitted_model():
    rows = build_rows()
    kwargs = dict(
        competition_key="league", season="2024/25",
        training_cutoff_utc=BASE + timedelta(days=150),
        minimum_matches=30, minimum_team_matches=10, max_iterations=4000,
    )
    forward = fit_poisson_strength_model(rows, **kwargs)
    reverse = fit_poisson_strength_model(list(reversed(rows)), **kwargs)
    assert forward == reverse


def test_boolean_numeric_hyperparameters_are_rejected():
    with pytest.raises(ValueError, match="HYPERPARAMETER_INVALID"):
        fit_poisson_strength_model(
            build_rows(), competition_key="league", season="2024/25",
            training_cutoff_utc=BASE + timedelta(days=150),
            minimum_matches=30, recency_half_life_days=True,
        )
