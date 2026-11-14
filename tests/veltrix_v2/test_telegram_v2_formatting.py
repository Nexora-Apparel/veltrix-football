from __future__ import annotations

from copy import deepcopy

import pytest

from veltrix_v2.reporting.report_identity import bind_report_identity
from veltrix_v2.reporting.telegram import (
    TELEGRAM_TEXT_LIMIT,
    format_public_telegram_messages,
)


def public_report():
    return bind_report_identity({
        "schema": "VELTRIX_V2_DAILY_REPORT_V1",
        "report_id": "veltrix-2026-11-14-restricted",
        "as_of_date": "2026-11-14",
        "release_mode": "RESTRICTED_PUBLIC",
        "predictions": [{
            "publication_status": "PUBLISHED",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "competition_name": "Example League",
            "kickoff_wat": "17:30 WAT",
            "certified_markets": ["1X2", "BTTS"],
            "markets": {
                "1X2": {"home": 0.5, "draw": 0.25, "away": 0.25},
                "BTTS": {"yes": 0.6, "no": 0.4},
                "TOTALS_2_5": {"over": 0.55, "under": 0.45},
            },
        }],
    })


def verifier(report, identity):
    return identity.report_id == report["report_id"] and identity.report_sha256 == report["report_sha256"]


def test_public_formatter_emits_only_explicitly_certified_markets():
    messages = format_public_telegram_messages(public_report(), verifier)
    joined = "\n".join(messages)
    assert "Alpha FC vs Beta FC" in joined
    assert "1X2: Home 50% | Draw 25% | Away 25%" in joined
    assert "BTTS: Yes 60% | No 40%" in joined
    assert "TOTALS_2_5:" not in joined
    assert "VALUE BET" not in joined


@pytest.mark.parametrize("release_mode", ["INTERNAL_SHADOW", "RESEARCH_ONLY", "DRAFT", None])
def test_shadow_and_non_public_reports_cannot_be_formatted_for_public_telegram(release_mode):
    report = public_report()
    report["release_mode"] = release_mode
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    with pytest.raises(PermissionError, match="public release mode"):
        format_public_telegram_messages(report, verifier)


def test_public_formatting_requires_authoritative_verifier():
    with pytest.raises(PermissionError, match="authorization"):
        format_public_telegram_messages(public_report(), lambda *_: False)


def test_tampered_report_is_rejected_before_authorization():
    report = public_report()
    report["predictions"][0]["markets"]["1X2"]["home"] = 0.99
    with pytest.raises(ValueError, match="content hash"):
        format_public_telegram_messages(report, verifier)


def test_unpublished_fixture_is_not_rendered():
    report = public_report()
    report["predictions"][0]["publication_status"] = "SHADOW_ONLY"
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    message = "\n".join(format_public_telegram_messages(report, verifier))
    assert "Alpha FC vs Beta FC" not in message
    assert "No certified fixtures" in message


def test_missing_market_probabilities_fail_closed():
    report = public_report()
    report["predictions"][0]["markets"].pop("BTTS")
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    with pytest.raises(ValueError, match="no probabilities"):
        format_public_telegram_messages(report, verifier)


def test_missing_market_certification_does_not_render_probabilities():
    report = public_report()
    report["predictions"][0]["certified_markets"] = []
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    message = "\n".join(format_public_telegram_messages(report, verifier))
    assert "50%" not in message
    assert "Forecast unavailable" in message


def test_long_reports_split_without_dropping_fixtures_or_exceeding_limit():
    report = public_report()
    template = deepcopy(report["predictions"][0])
    report["predictions"] = [
        {**template, "home_team": f"Home {index:02d}", "away_team": f"Away {index:02d}"}
        for index in range(80)
    ]
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    messages = format_public_telegram_messages(report, verifier)
    assert len(messages) > 1
    assert all(len(message) <= TELEGRAM_TEXT_LIMIT for message in messages)
    combined = "\n".join(messages)
    for index in range(80):
        assert f"Home {index:02d} vs Away {index:02d}" in combined


def test_single_fixture_block_too_large_is_rejected_not_truncated():
    report = public_report()
    report["predictions"][0]["home_team"] = "H" * (TELEGRAM_TEXT_LIMIT + 100)
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    with pytest.raises(ValueError, match="single fixture block"):
        format_public_telegram_messages(report, verifier)


def test_legacy_telegram_formatter_cannot_consume_v2_report():
    from scripts.send_telegram_report import format_report_messages as legacy_formatter

    with pytest.raises(ValueError, match="V2 report rejected"):
        legacy_formatter(public_report())


@pytest.mark.parametrize("values", [
    {"home": 0.8, "draw": 0.3, "away": 0.1},
    {"home": 1.2, "draw": -0.1, "away": -0.1},
    {"home": float("nan"), "draw": 0.3, "away": 0.7},
])
def test_certified_market_with_invalid_or_unnormalized_probabilities_is_rejected(values):
    report = public_report()
    report["predictions"][0]["markets"]["1X2"] = values
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    with pytest.raises(ValueError, match="CERTIFIED_MARKET_PROBABILIT"):
        format_public_telegram_messages(report, verifier)
