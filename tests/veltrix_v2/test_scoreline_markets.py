import pytest

from veltrix_v2.models.scoreline import (
    ScorelineDistribution,
    ScorelineProbability,
)


def distribution():
    return ScorelineDistribution.from_rows(
        "fixture-1",
        "goal-model-test-v1",
        [
            ScorelineProbability(0, 0, 0.1),
            ScorelineProbability(1, 0, 0.1),
            ScorelineProbability(1, 1, 0.2),
            ScorelineProbability(2, 1, 0.3),
            ScorelineProbability(0, 3, 0.3),
        ],
    )


def test_all_markets_are_derived_from_same_joint_distribution():
    markets = distribution().derive_markets(total_line=2.5)
    assert markets.p_home_win == pytest.approx(0.4)
    assert markets.p_draw == pytest.approx(0.3)
    assert markets.p_away_win == pytest.approx(0.3)
    assert markets.p_btts_yes == pytest.approx(0.5)
    assert markets.p_btts_no == pytest.approx(0.5)
    assert markets.p_over == pytest.approx(0.6)
    assert markets.p_under == pytest.approx(0.4)
    assert markets.expected_home_goals == pytest.approx(0.9)
    assert markets.expected_away_goals == pytest.approx(1.4)


def test_derived_probability_groups_sum_to_one():
    markets = distribution().derive_markets()
    assert markets.p_home_win + markets.p_draw + markets.p_away_win == pytest.approx(1.0)
    assert markets.p_btts_yes + markets.p_btts_no == pytest.approx(1.0)
    assert markets.p_over + markets.p_under == pytest.approx(1.0)


def test_total_line_is_configurable():
    markets = distribution().derive_markets(total_line=1.5)
    assert markets.p_over == pytest.approx(0.8)
    assert markets.p_under == pytest.approx(0.2)


def test_integer_total_line_is_rejected_without_push_contract():
    with pytest.raises(ValueError, match="half-goal line"):
        distribution().derive_markets(total_line=2.0)


def test_probability_mass_is_not_silently_renormalized():
    with pytest.raises(ValueError, match="must sum to one"):
        ScorelineDistribution.from_rows(
            "fixture-1", "model-v1", [ScorelineProbability(0, 0, 0.5)]
        )


def test_duplicate_scorelines_fail_closed():
    with pytest.raises(ValueError, match="duplicate scoreline"):
        ScorelineDistribution.from_rows(
            "fixture-1",
            "model-v1",
            [ScorelineProbability(0, 0, 0.5), ScorelineProbability(0, 0, 0.5)],
        )


@pytest.mark.parametrize("home,away", [(-1, 0), (0, -1), (True, 0), (0, 1.5)])
def test_invalid_goal_counts_are_rejected(home, away):
    with pytest.raises(ValueError, match="non-negative integer"):
        ScorelineProbability(home, away, 1.0)


@pytest.mark.parametrize("probability", [-0.1, 1.1, float("nan"), float("inf"), True])
def test_invalid_scoreline_mass_is_rejected(probability):
    with pytest.raises(ValueError):
        ScorelineProbability(0, 0, probability)


def test_invalid_total_line_is_rejected():
    with pytest.raises(ValueError, match="total_line"):
        distribution().derive_markets(total_line=float("nan"))


def test_empty_distribution_is_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        ScorelineDistribution.from_rows("fixture-1", "model-v1", [])
