from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

from veltrix_v2.evaluation.certification_manifest_builder import build_certification_manifest
from veltrix_v2.evaluation.walk_forward import FixtureEvaluation, WalkForwardReport
from veltrix_v2.evaluation.publication_certification import verify_publication_authorization
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity


UTC = timezone.utc
BUILD = "model-build-2026-11-14"


def _report():
    cutoff = datetime(2026, 11, 14, 5, tzinfo=UTC)
    return bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "veltrix-2026-11-14",
        "as_of_date": "2026-11-14",
        "generated_at_utc": cutoff.isoformat().replace("+00:00", "Z"),
        "cutoff_at_utc": cutoff.isoformat().replace("+00:00", "Z"),
        "status": "PUBLISHED",
        "release_mode": "FULL_PUBLIC",
        "predictions": [{
            "fixture_id": "report-fixture-1",
            "competition_id": "comp-1",
            "model_build_id": BUILD,
            "kickoff_utc": "2026-11-14T07:00:00Z",
            "cutoff_at_utc": cutoff.isoformat().replace("+00:00", "Z"),
            "publication_status": "PUBLISHED",
            "certified_markets": ["1X2", "BTTS", "TOTALS_2_5"],
            "markets": {
                "1X2": {"home": 0.90, "draw": 0.05, "away": 0.05},
                "BTTS": {"yes": 0.60, "no": 0.40},
                "TOTALS_2_5": {"over": 0.55, "under": 0.45},
            },
        }],
    })


def _walk_forward():
    fixtures = []
    start = datetime(2025, 1, 1, 12, tzinfo=UTC)
    for index in range(1000):
        outcome = ("HOME", "DRAW", "AWAY")[index % 3]
        if outcome == "HOME":
            home_goals, away_goals = 2, 1
            p1x2 = {"home": 0.90, "draw": 0.05, "away": 0.05}
        elif outcome == "DRAW":
            home_goals, away_goals = 1, 1
            p1x2 = {"home": 0.05, "draw": 0.90, "away": 0.05}
        else:
            home_goals, away_goals = 0, 1
            p1x2 = {"home": 0.05, "draw": 0.05, "away": 0.90}
        kickoff = start + timedelta(days=index % 120, minutes=index)
        btts_yes = home_goals > 0 and away_goals > 0
        over = home_goals + away_goals >= 3
        fixtures.append(FixtureEvaluation(
            fixture_id=f"wf-{index:04d}",
            competition_id="comp-1",
            kickoff_at=kickoff,
            cutoff_at=kickoff - timedelta(hours=2),
            actual_home_goals=home_goals,
            actual_away_goals=away_goals,
            actual_1x2=outcome,
            model_home_win=p1x2["home"],
            model_draw=p1x2["draw"],
            model_away_win=p1x2["away"],
            baseline_home_win=1 / 3,
            baseline_draw=1 / 3,
            baseline_away_win=1 / 3,
            model_btts_yes=0.90 if btts_yes else 0.10,
            baseline_btts_yes=0.50,
            model_over_2_5=0.90 if over else 0.10,
            baseline_over_2_5=0.50,
            model_build_id=BUILD,
        ))
    return WalkForwardReport(
        evaluation_as_of=datetime(2025, 5, 2, tzinfo=UTC),
        total_input_fixtures=1000,
        eligible_scored_fixtures=1000,
        skipped_no_history=0,
        skipped_invalid_target=0,
        skipped_duplicate_ids=0,
        skipped_after_evaluation_as_of=0,
        one_x_two=None,
        btts=None,
        over_2_5=None,
        fixtures=tuple(fixtures),
        model_build_id=BUILD,
    )


def _quotes(walk_forward):
    return [{
        "fixture_id": row.fixture_id,
        "competition_id": row.competition_id,
        "source_provider": "The Odds API",
        "quote_timestamp_basis": "PROVIDER_OBSERVED_AT",
        "quote_at": (row.kickoff_at - timedelta(hours=3)).isoformat(),
        "bookmaker": "Bookmaker A",
        "odds": {"home": 3.0, "draw": 3.0, "away": 3.0},
        "evidence_sha256": "f" * 64,
    } for row in walk_forward.fixtures]


def _selections():
    rows = []
    start = datetime(2026, 7, 1, 12, tzinfo=UTC)
    for market in ("1X2", "BTTS", "TOTALS_2_5"):
        for index in range(300):
            kickoff = start + timedelta(days=index % 90)
            rows.append({
                "selection_id": f"{market}-{index:03d}",
                "fixture_id": f"prospective-{market}-{index:03d}",
                "competition_id": "comp-1",
                "market": market,
                "model_build_id": BUILD,
                "prospective": True,
                "settled": True,
                "kickoff_at": kickoff.isoformat(),
                "prediction_cutoff_at": (kickoff - timedelta(hours=2)).isoformat(),
                "quote_at": (kickoff - timedelta(hours=3)).isoformat(),
                "quote_timestamp_basis": "PROVIDER_OBSERVED_AT",
                "quote_source": "The Odds API",
                "quote_evidence_sha256": "a" * 64,
                "stake": 1.0,
                "net_profit_after_fees_and_slippage": 0.10,
            })
    return rows


def _evidence():
    return {
        "evidence_uri": "https://evidence.example/walk-forward-paper",
        "evidence_sha256": hashlib.sha256(b"walk-forward-paper").hexdigest(),
        "rights_evidence_uri": "https://evidence.example/rights",
        "rights_evidence_sha256": hashlib.sha256(b"rights").hexdigest(),
        "rights_approval_id": "rights-bundle-1",
        "rights_evaluated_at": "2026-11-14T04:00:00Z",
        "model_artifact_sha256": "c" * 64,
        "feature_set_sha256": "d" * 64,
        "bookmaker_baseline_evidence_uri": "https://evidence.example/odds",
        "bookmaker_baseline_evidence_sha256": hashlib.sha256(b"odds").hexdigest(),
        "bookmaker_baseline_source": "The Odds API",
        "point_in_time_certifiable": True,
        "revision_history_complete": True,
        "paper_ledger_chain_verified": True,
    }


def test_builder_computes_all_three_markets_and_verifier_accepts_signed_evidence_contract():
    report = _report()
    walk_forward = _walk_forward()
    evidence = _evidence()
    manifest = build_certification_manifest(
        report=report,
        walk_forward_report=walk_forward,
        prospective_selections=_selections(),
        bookmaker_quotes=_quotes(walk_forward),
        evidence=evidence,
        rights_verifier=lambda record: True,
        generated_at_utc=datetime(2026, 11, 14, 5, 30, tzinfo=UTC),
    )
    assert manifest["status"] == "CERTIFIED"
    records = {record["market"]: record for record in manifest["certifications"]}
    assert set(records) == {"1X2", "BTTS", "TOTALS_2_5"}
    for record in records.values():
        assert record["walk_forward_matches"] == 1000
        assert record["prospective_settled_selections"] == 300
        assert record["distinct_dates"] == 90
        assert record["timestamped_odds_coverage"] == 1.0
        assert record["net_roi"] > 0
        assert record["roi_ci95_lower"] > 0
        assert record["status"] == "CERTIFIED"
    assert records["1X2"]["brier_score"] < records["1X2"]["bookmaker_brier_score"]
    assert records["1X2"]["log_loss"] < records["1X2"]["bookmaker_log_loss"]

    evidence_bytes = {
        evidence["evidence_uri"]: b"walk-forward-paper",
        evidence["rights_evidence_uri"]: b"rights",
        evidence["bookmaker_baseline_evidence_uri"]: b"odds",
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    assert verify_publication_authorization(
        report,
        manifest_bytes,
        lambda payload, digest: hashlib.sha256(payload).hexdigest() == digest,
        lambda record: True,
        lambda uri: evidence_bytes[uri],
    )


def test_builder_fails_closed_without_prospective_selections_and_rights_verifier():
    report = _report()
    walk_forward = _walk_forward()
    manifest = build_certification_manifest(
        report=report,
        walk_forward_report=walk_forward,
        prospective_selections=[],
        bookmaker_quotes=_quotes(walk_forward),
        evidence=_evidence(),
        rights_verifier=None,
    )
    assert manifest["status"] == "NOT_CERTIFIED"
    for record in manifest["certifications"]:
        assert record["prospective_settled_selections"] == 0
        assert record["status"] == "NOT_CERTIFIED"
        assert "PROSPECTIVE_SETTLED_SELECTIONS_BELOW_300" in record["blockers"]
        assert "RIGHTS_VERIFIER_MISSING" in record["blockers"]


def test_builder_rejects_non_provider_observed_timestamps_for_bookmaker_benchmark():
    report = _report()
    walk_forward = _walk_forward()
    quotes = _quotes(walk_forward)
    for quote in quotes:
        quote["quote_timestamp_basis"] = "RETRIEVED_AT"
    manifest = build_certification_manifest(
        report=report,
        walk_forward_report=walk_forward,
        prospective_selections=_selections(),
        bookmaker_quotes=quotes,
        evidence=_evidence(),
        rights_verifier=lambda record: True,
    )
    one_x_two = next(row for row in manifest["certifications"] if row["market"] == "1X2")
    assert one_x_two["walk_forward_matches"] == 0
    assert one_x_two["status"] == "NOT_CERTIFIED"
    assert "BOOKMAKER_FIXTURE_SET_MISMATCH" in one_x_two["blockers"]
