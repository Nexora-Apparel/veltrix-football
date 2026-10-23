from app.football_api import FootballAPI

def test_api_client_has_expected_methods():
    assert callable(FootballAPI.get)
    assert callable(FootballAPI.status)
    assert callable(FootballAPI.fixtures)
    assert callable(FootballAPI.leagues)
