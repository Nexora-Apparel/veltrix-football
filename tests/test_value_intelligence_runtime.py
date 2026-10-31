from datetime import datetime, timedelta, timezone

from app.value_intelligence_runtime import attach_value_intelligence, screen_fixture_value_intelligence


def _fixture():
    kickoff = datetime.now(timezone.utc) + timedelta(hours=5)
    fetched = kickoff - timedelta(minutes=10)
    quote = fetched - timedelta(minutes=1)
    return {
        "home_team": "Home FC",
        "away_team": "Away FC",
        "kickoff_local": kickoff.isoformat(),
        "model": "experimental_recent_goals_poisson",
        "probabilities": {"home_win": 0.55, "draw": 0.25, "away_win": 0.20},
        "btts_yes": 0.60,
        "over_1_5": 0.75,
        "over_2_5": 0.55,
        "over_3_5": 0.35,
        "the_odds_api_market_odds": {
            "fetched_at": fetched.isoformat(),
            "commence_time": kickoff.isoformat(),
            "markets": {
                "h2h": [
                    {"bookmaker": "Book A", "last_update": quote.isoformat(), "outcomes": [
                        {"name": "Home FC", "price": 2.0}, {"name": "Draw", "price": 3.5}, {"name": "Away FC", "price": 4.0}]},
                    {"bookmaker": "Book B", "last_update": quote.isoformat(), "outcomes": [
                        {"name": "Home FC", "price": 1.95}, {"name": "Draw", "price": 3.6}, {"name": "Away FC", "price": 4.1}]},
                ],
                "btts": [
                    {"bookmaker": "Book A", "last_update": quote.isoformat(), "outcomes": [
                        {"name": "Yes", "price": 1.8}, {"name": "No", "price": 2.0}]},
                    {"bookmaker": "Book B", "last_update": quote.isoformat(), "outcomes": [
                        {"name": "Yes", "price": 1.85}, {"name": "No", "price": 1.95}]},
                ],
                "totals": [
                    {"bookmaker": "Book A", "last_update": quote.isoformat(), "outcomes": [
                        {"name": "Over", "point": 2.5, "price": 1.9}, {"name": "Under", "point": 2.5, "price": 1.9}]},
                    {"bookmaker": "Book B", "last_update": quote.isoformat(), "outcomes": [
                        {"name": "Over", "point": 2.5, "price": 1.95}, {"name": "Under", "point": 2.5, "price": 1.85}]},
                ],
            },
        },
    }


def test_fixture_gets_consensus_and_shadow_diagnostics_without_unlocking():
    result = screen_fixture_value_intelligence(_fixture())
    assert result["status"] == "EVALUATED"
    assert result["markets"]["1X2"]["bookmaker_count"] == 2
    assert result["markets"]["BTTS"]["bookmaker_count"] == 2
    assert result["markets"]["OVER_UNDER_2_5"]["bookmaker_count"] == 2
    assert result["release_status"] == "LOCKED_SHADOW_MODE"


def test_stale_or_post_kickoff_quotes_are_rejected():
    fixture = _fixture()
    fixture["the_odds_api_market_odds"]["fetched_at"] = (
        datetime.now(timezone.utc) - timedelta(days=2)
    ).isoformat()
    result = screen_fixture_value_intelligence(fixture)
    assert result["status"] == "NO_ELIGIBLE_TIMESTAMPED_ODDS"


def test_report_aggregates_diagnostics_and_keeps_alerts_off():
    report = attach_value_intelligence({"predictions": [_fixture()]})
    assert report["value_intelligence"]["status"] == "SHADOW_MODE"
    assert report["value_intelligence"]["fixtures_evaluated"] == 1
    assert report["value_intelligence"]["alerts_enabled"] is False
    assert "value_intelligence" in report["predictions"][0]
