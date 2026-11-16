import pytest

from veltrix_v2.models.openplay_xg_poisson import (
    MODEL_VERSION,
    predict_from_recent_features,
)


def _feature(xg, xga):
    return {"metrics":{"team":{"xg":xg,"xg_against":xga}}}


def test_model_uses_both_teams_recent_xg_and_returns_normalised_markets():
    result=predict_from_recent_features(
        home_features=[_feature(1.8,0.9),_feature(1.4,1.1)],
        away_features=[_feature(1.2,1.6),_feature(1.0,1.3)],
    )
    assert result.model_version==MODEL_VERSION
    assert result.expected_home_goals==pytest.approx((1.6+1.45)/2)
    assert result.expected_away_goals==pytest.approx((1.1+1.0)/2)
    assert sum((result.home_win,result.draw,result.away_win))==pytest.approx(1.0)
    assert 0<=result.btts_yes<=1
    assert 0<=result.over_2_5<=1
    assert result.home_sample_count==2
    assert result.away_sample_count==2


def test_model_has_no_generic_fallback_when_either_team_has_no_history():
    with pytest.raises(ValueError,match="BOTH_TEAMS_REQUIRE_HISTORY"):
        predict_from_recent_features(home_features=[],away_features=[_feature(1.1,1.0)])


def test_model_rejects_missing_or_invalid_xg_values():
    with pytest.raises(ValueError,match="XG_MISSING_OR_INVALID"):
        predict_from_recent_features(
            home_features=[{"metrics":{"team":{"xg":None,"xg_against":1.0}}}],
            away_features=[_feature(1.0,1.0)],
        )
    with pytest.raises(ValueError,match="XG_OUT_OF_RANGE"):
        predict_from_recent_features(
            home_features=[_feature(-0.2,1.0)],
            away_features=[_feature(1.0,1.0)],
        )


def test_equal_team_features_produce_symmetric_1x2():
    features=[_feature(1.5,1.2),_feature(1.1,1.4)]
    result=predict_from_recent_features(home_features=features,away_features=features)
    assert result.home_win==pytest.approx(result.away_win)
