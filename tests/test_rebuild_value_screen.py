from scripts.rebuild_value_screen import rebuild_value_screen


def test_rebuild_keeps_release_locked_and_marks_saved_snapshot_research_only():
    report = {
        "as_of_date": "2026-10-31",
        "predictions": [],
        "value_validation_certificate": {
            "status": "LOCKED_INSUFFICIENT_EVIDENCE",
            "approved_markets": [],
            "alerts_enabled": False,
        },
    }
    rebuilt = rebuild_value_screen(report)
    screen = rebuilt["value_bet_screen"]
    assert screen["status"] == "DISABLED_UNVALIDATED"
    assert screen["candidate_count"] == 0
    assert screen["paper_candidate_count"] == 0
    assert screen["alerts_enabled"] is False
    assert "No football provider was called" in rebuilt["value_screen_rebuild_notice"]
