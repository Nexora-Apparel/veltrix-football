import json

from scripts.build_value_certificate import build


def test_certificate_builder_fails_closed_without_paper_ledger(tmp_path):
    backtest = {
        "live_pipeline": {
            "goal_markets": {"rolling_origin_calibration": {"markets": {}}},
            "historical_odds_subset": {"models_compared_on_same_matches": {}},
        },
        "recent_holdout": {"historical_odds_subset": {"models_compared_on_same_matches": {}}},
        "dataset_provenance": {"rows_loaded": 1234},
    }
    backtest_path = tmp_path / "backtest.json"
    backtest_path.write_text(json.dumps(backtest), encoding="utf-8")
    report_path = tmp_path / "daily.json"
    report_path.write_text(json.dumps({"predictions": []}), encoding="utf-8")
    certificate_path = tmp_path / "certificate.json"

    certificate = build(
        str(report_path),
        str(tmp_path / "missing-ledger.json"),
        str(certificate_path),
        backtest_path=str(backtest_path),
    )

    assert certificate["status"] == "LOCKED_INSUFFICIENT_EVIDENCE"
    assert certificate["approved_markets"] == []
    assert certificate["alerts_enabled"] is False
    assert certificate["paper_ledger_present"] is False
    assert json.loads(certificate_path.read_text(encoding="utf-8"))["status"] == certificate["status"]
    updated_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert updated_report["value_validation_certificate"]["status"] == certificate["status"]
    assert updated_report["value_bet_screen"]["alerts_enabled"] is False
