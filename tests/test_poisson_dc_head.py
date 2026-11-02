import pytest

from app.poisson_dc_head import dixon_coles_markets


def test_market_probabilities_are_bounded_and_coherent():
    result = dixon_coles_markets(1.45, 1.10)
    markets = result["markets"]
    assert sum(markets["1x2"].values()) == pytest.approx(1.0, abs=1e-12)
    assert sum(markets["btts"].values()) == pytest.approx(1.0, abs=1e-12)
    for values in markets["totals"].values():
        assert sum(values.values()) == pytest.approx(1.0, abs=1e-12)
        assert 0 <= values["over"] <= 1
    assert markets["totals"]["0.5"]["over"] >= markets["totals"]["1.5"]["over"]
    assert markets["totals"]["1.5"]["over"] >= markets["totals"]["2.5"]["over"]
    assert markets["btts"]["yes"] == pytest.approx(1 - markets["btts"]["no"])


def test_truncation_is_reported_and_small_for_normal_rates():
    result = dixon_coles_markets(1.2, 0.9)
    assert result["status"] == "SHADOW_RESEARCH"
    assert result["top_scorelines"][0]["probability"] > 0
    assert result["truncated_poisson_tail_estimate"]["upper_bound_union"] < 1e-8


@pytest.mark.parametrize("home,away,rho", [
    (0, 1, -0.05), (-1, 1, -0.05), (float("nan"), 1, -0.05),
    (1, 1, 0.5), (11, 1, -0.05), (10, 10, -0.25),
])
def test_invalid_inputs_fail_closed(home, away, rho):
    with pytest.raises(ValueError):
        dixon_coles_markets(home, away, rho=rho)


def test_dc_rho_changes_low_score_sensitive_markets():
    independent = dixon_coles_markets(1.3, 1.0, rho=0.0)
    corrected = dixon_coles_markets(1.3, 1.0, rho=-0.1)
    assert corrected["markets"]["1x2"] != independent["markets"]["1x2"]


@pytest.mark.parametrize("line", [0.25, 1.0, 2.25, -0.5, float("nan")])
def test_unsupported_totals_lines_are_rejected(line):
    with pytest.raises(ValueError):
        dixon_coles_markets(1.2, 0.9, totals_lines=(line,))


def test_high_rate_requires_larger_score_grid():
    with pytest.raises(ValueError, match="truncation too large"):
        dixon_coles_markets(8.0, 8.0, max_goals=12)
    result = dixon_coles_markets(8.0, 8.0, max_goals=40)
    assert result["truncated_poisson_tail_estimate"]["upper_bound_union"] <= 1e-8
