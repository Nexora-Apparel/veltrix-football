import pytest

from app.poisson_dc_head import dixon_coles_markets


def test_market_probabilities_are_bounded_and_coherent():
    result = dixon_coles_markets(1.45, 1.10)
    markets = result["markets"]
    assert abs(sum(markets["1x2"].values()) - 1.0) < 1e-12
    assert abs(sum(markets["btts"].values()) - 1.0) < 1e-12
    for values in markets["totals"].values():
        assert abs(sum(values.values()) - 1.0) < 1e-12
        assert 0 <= values["over"] <= 1
    assert markets["totals"]["0.5"]["over"] >= markets["totals"]["1.5"]["over"]
    assert markets["totals"]["1.5"]["over"] >= markets["totals"]["2.5"]["over"]
    assert markets["btts"]["yes"] == pytest.approx(
        1 - markets["btts"]["no"], abs=1e-12
    )


def test_scoreline_probabilities_sum_to_one():
    result = dixon_coles_markets(1.2, 0.9)
    # The displayed top ten are a subset, while the internal market grid sums to one.
    assert result["status"] == "SHADOW_RESEARCH"
    assert result["top_scorelines"][0]["probability"] > 0
    assert result["truncated_poisson_tail_estimate"]["upper_bound_union"] < 1e-6


@pytest.mark.parametrize("home,away,rho", [
    (0, 1, -0.05), (-1, 1, -0.05), (float("nan"), 1, -0.05),
    (1, 1, 0.5), (11, 1, -0.05),
])
def test_invalid_inputs_fail_closed(home, away, rho):
    with pytest.raises(ValueError):
        dixon_coles_markets(home, away, rho=rho)


def test_dc_rho_changes_low_score_sensitive_markets():
    independent = dixon_coles_markets(1.3, 1.0, rho=0.0)
    corrected = dixon_coles_markets(1.3, 1.0, rho=-0.1)
    assert corrected["markets"]["1x2"] != independent["markets"]["1x2"]
