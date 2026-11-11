import pytest

from veltrix_v2.models.dixon_coles import build_dixon_coles_forecast


def forecast(**overrides):
    args = {
        "fixture_id": "fixture-1",
        "expected_home_goals": 1.45,
        "expected_away_goals": 1.10,
        "rho": -0.08,
        "tail_tolerance": 1e-7,
    }
    args.update(overrides)
    return build_dixon_coles_forecast(**args)


def test_joint_distribution_is_normalized_and_tail_is_explicit():
    result = forecast()
    assert sum(row.probability for row in result.distribution.scorelines) == pytest.approx(1)
    assert result.tail_mass <= 1e-7
    assert result.retained_mass + result.tail_mass == pytest.approx(1)
    assert result.normalization == "explicit_conditional_on_retained_scoreline_support"
    markets = result.distribution.derive_markets(total_line=2.5)
    assert sum((markets.p_home_win, markets.p_draw, markets.p_away_win)) == pytest.approx(1)


def test_rho_changes_low_score_mass_but_not_fixture_identity():
    independent = forecast(rho=0.0)
    adjusted = forecast(rho=-0.08)
    def p(result, h, a):
        return next(row.probability for row in result.distribution.scorelines if (row.home_goals, row.away_goals) == (h, a))
    assert p(independent, 0, 0) != pytest.approx(p(adjusted, 0, 0))
    assert adjusted.distribution.fixture_id == "fixture-1"


@pytest.mark.parametrize("rates", [(0, 1), (-1, 1), (1, float("nan"))])
def test_invalid_goal_rates_are_rejected(rates):
    with pytest.raises(ValueError):
        forecast(expected_home_goals=rates[0], expected_away_goals=rates[1])


def test_rho_that_breaks_low_score_probability_is_rejected():
    with pytest.raises(ValueError, match="NONPOSITIVE_LOW_SCORE_MASS"):
        forecast(rho=2.0)


def test_excessive_tail_mass_fails_closed():
    with pytest.raises(ValueError, match="TAIL_MASS_EXCEEDS_TOLERANCE"):
        forecast(expected_home_goals=7.0, expected_away_goals=7.0, tail_tolerance=1e-12, maximum_max_goals=8)


def test_integer_total_line_still_requires_push_settlement():
    result = forecast()
    with pytest.raises(ValueError, match="half-goal"):
        result.distribution.derive_markets(total_line=2.0)
