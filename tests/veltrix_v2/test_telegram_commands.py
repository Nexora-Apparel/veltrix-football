from __future__ import annotations

from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity
from veltrix_v2.reporting.telegram_commands import handle_v2_command


def public_report():
    return bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "telegram-commands-2026-11-14",
        "as_of_date": "2026-11-14",
        "release_mode": "RESTRICTED_PUBLIC",
        "predictions": [
            {
                "fixture_id": "fixture-1",
                "publication_status": "PUBLISHED",
                "home_team": "Alpha FC",
                "away_team": "Beta FC",
                "competition_name": "Example League",
                "kickoff_wat": "19:00 WAT",
                "certified_markets": ["1X2", "BTTS", "TOTALS_2_5"],
                "markets": {
                    "1X2": {"home": 0.50, "draw": 0.25, "away": 0.25},
                    "BTTS": {"yes": 0.55, "no": 0.45},
                    "TOTALS_2_5": {"over": 0.52, "under": 0.48},
                },
                # Legacy fields must never be used by the V2 command renderer.
                "status": "EXPERIMENTAL_ONLY",
                "probabilities": {"home_win": 0.99, "draw": 0.005, "away_win": 0.005},
                "expected_goals": {"home": 4.0, "away": 0.1},
            }
        ],
    })


def verifier(report, identity):
    return report.get("report_id") == identity.report_id and report.get("report_sha256") == identity.report_sha256


def test_v2_1x2_command_uses_only_certified_v2_market_values():
    reply = handle_v2_command("/1x2", report=public_report(), authorization_verifier=verifier)
    assert "Home 50%" in reply
    assert "Draw 25%" in reply
    assert "Away 25%" in reply
    assert "99%" not in reply
    assert "EXPERIMENTAL" not in reply


def test_v2_btts_and_totals_commands_use_their_certified_market_only():
    report = public_report()
    btts = handle_v2_command("/btts", report=report, authorization_verifier=verifier)
    totals = handle_v2_command("/overunder", report=report, authorization_verifier=verifier)
    assert "Yes 55%" in btts and "No 45%" in btts
    assert "Over 2.5 52%" in totals and "Under 2.5 48%" in totals


def test_v2_command_hides_uncertified_market_even_if_legacy_probabilities_exist():
    report = public_report()
    report["predictions"][0]["certified_markets"] = []
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    reply = handle_v2_command("/1x2", report=report, authorization_verifier=verifier)
    assert "V2 REPORT UNAVAILABLE" in reply
    assert "99%" not in reply


def test_v2_value_commands_remain_locked_and_ignore_legacy_value_candidates():
    report = public_report()
    report["predictions"][0]["value_bet_screen"] = {
        "markets": {"1X2": {"paper_candidates": [{"selection": "HOME", "model_probability": 0.99}]}}
    }
    for command in ("/value", "/1x2value", "/bttsvalue", "/overvalue"):
        reply = handle_v2_command(command, report=report, authorization_verifier=verifier)
        assert "VALUE BETTING — LOCKED" in reply
        assert "0.99" not in reply


def test_v2_expected_goals_command_does_not_expose_uncertified_legacy_means():
    reply = handle_v2_command("/goals", report=public_report(), authorization_verifier=verifier)
    assert "EXPECTED-GOALS INSIGHTS — NOT CERTIFIED" in reply
    assert "4.00" not in reply


def test_v2_fixture_and_match_commands_render_report_identity_and_fixture():
    report = public_report()
    fixtures = handle_v2_command("/fixtures", report=report, authorization_verifier=verifier)
    match = handle_v2_command("/match Alpha FC vs Beta FC", report=report, authorization_verifier=verifier)
    assert report["report_id"] in fixtures
    assert "Alpha FC vs Beta FC" in fixtures
    assert "1X2: Home 50%" in match


def test_v2_report_commands_fail_closed_without_report_or_authoritative_verifier():
    assert "V2 REPORT UNAVAILABLE" in handle_v2_command(
        "/today", report=public_report(), authorization_verifier=None
    )
    assert "V2 REPORT UNAVAILABLE" in handle_v2_command(
        "/today", report=None, authorization_verifier=verifier
    )


def test_v2_static_commands_remain_available_without_report():
    assert "AVAILABLE COMMANDS" in handle_v2_command(
        "/help", report=None, authorization_verifier=None
    )
    assert "Combined decimal odds: 6.24" in handle_v2_command(
        "/slipcheck 1.80 2.00 1.7333333333",
        report=None,
        authorization_verifier=None,
    )


def test_v2_renderer_rejects_bad_probability_vector_even_when_verifier_returns_true():
    report = public_report()
    report["predictions"][0]["markets"]["1X2"]["home"] = 0.9
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    reply = handle_v2_command("/1x2", report=report, authorization_verifier=verifier)
    assert "NO CERTIFIED PUBLIC FIXTURES" in reply
