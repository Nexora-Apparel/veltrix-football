from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.evaluation.model_challengers import evaluate_model_challengers
from veltrix_v2.evaluation.team_form_challenger import evaluate_team_form_challenger
from veltrix_v2.models.poisson import MatchObservation
from veltrix_v2.ledger.paper_predictions import PaperPrediction, ProspectivePaperLedger

UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def match(fid, home, away, hg, ag, day, *, certifiable=True):
    kickoff = BASE + timedelta(days=day)
    return MatchObservation(
        fixture_id=fid, competition_id="league", home_team_id=home,
        away_team_id=away, kickoff_at=kickoff,
        available_at=kickoff + timedelta(hours=2),
        recorded_at=kickoff + timedelta(hours=3),
        home_goals=hg, away_goals=ag,
        point_in_time_certifiable=certifiable,
    )


def comparison_rows():
    rows = [
        match("h1", "A", "B", 2, 1, 1),
        match("h2", "B", "A", 1, 1, 2),
        match("h3", "A", "C", 1, 0, 3),
        match("h4", "C", "B", 2, 1, 4),
        match("h5", "B", "A", 0, 2, 5),
        match("h6", "A", "B", 1, 0, 6),
        match("h7", "B", "C", 2, 0, 7),
        match("h8", "C", "A", 1, 2, 8),
        match("t9", "A", "B", 1, 1, 9),
        match("t10", "B", "A", 0, 1, 10),
        match("t11", "A", "B", 2, 0, 11),
    ]
    return rows


def test_poisson_elo_form_and_blends_use_identical_fixture_set():
    report = evaluate_model_challengers(
        comparison_rows(), evaluation_as_of=BASE + timedelta(days=20)
    )
    assert report.scored_fixtures == 3
    expected = {row.fixture_id for row in report.fixtures}
    assert expected == {"t9", "t10", "t11"}
    assert all(metric.sample_count == 3 for metric in report.metrics.values())
    assert report.metrics["blend_all_equal"].sample_count == report.metrics["poisson"].sample_count
    for row in report.fixtures:
        for prediction in row.predictions.values():
            assert prediction.home + prediction.draw + prediction.away == pytest.approx(1.0)


def test_competition_reliability_is_separated_and_duplicates_excluded():
    rows = comparison_rows()
    rows += [match("other1", "X", "Y", 1, 0, 1)]
    rows += [match("dup", "A", "B", 1, 0, 12), match("dup", "B", "A", 0, 1, 13)]
    report = evaluate_model_challengers(
        rows, evaluation_as_of=BASE + timedelta(days=20)
    )
    assert report.duplicate_fixture_rows == 2
    assert [item.competition_id for item in report.competitions] == ["league"]
    assert report.competitions[0].sample_count == 3
    assert report.competitions[0].metrics["form"].sample_count == 3


def test_uncertified_targets_are_not_scored():
    rows = comparison_rows()
    rows.append(match("uncertified", "A", "B", 4, 0, 12, certifiable=False))
    report = evaluate_model_challengers(
        rows, evaluation_as_of=BASE + timedelta(days=20)
    )
    assert report.scored_fixtures == 3
    assert report.skipped_uncertified_targets == 1


def test_paper_ledger_accepts_only_prospective_certifiable_predictions_and_settles_append_only():
    ledger = ProspectivePaperLedger()
    kickoff = BASE + timedelta(days=10)
    prediction = PaperPrediction(
        fixture_id="fixture-1", competition_id="league",
        home_team_id="A", away_team_id="B", kickoff_at=kickoff,
        prediction_cutoff_at=kickoff - timedelta(hours=2),
        forecasted_at=kickoff - timedelta(hours=1),
        recorded_at=kickoff - timedelta(minutes=59),
        model_version="candidate-v1",
        home_probability=0.5, draw_probability=0.25, away_probability=0.25,
        evidence_sha256="a" * 64, point_in_time_certifiable=True,
    )
    first = ledger.append_prediction(prediction)
    assert first.sequence == 1
    settled = ledger.append_settlement(
        fixture_id="fixture-1", model_version="candidate-v1",
        home_goals=2, away_goals=1,
        result_available_at=kickoff + timedelta(hours=2),
        recorded_at=kickoff + timedelta(hours=3),
    )
    assert settled.sequence == 2
    assert ledger.verify_chain()
    assert len(ledger.events) == 2


def test_paper_ledger_rejects_backfill_noncertifiable_and_duplicate_prediction():
    ledger = ProspectivePaperLedger()
    kickoff = BASE + timedelta(days=10)
    prediction = PaperPrediction(
        fixture_id="fixture-2", competition_id="league",
        home_team_id="A", away_team_id="B", kickoff_at=kickoff,
        prediction_cutoff_at=kickoff - timedelta(hours=2),
        forecasted_at=kickoff - timedelta(hours=1),
        recorded_at=kickoff - timedelta(minutes=59),
        model_version="candidate-v1",
        home_probability=0.5, draw_probability=0.25, away_probability=0.25,
        evidence_sha256="b" * 64, point_in_time_certifiable=True,
    )
    ledger.append_prediction(prediction)
    with pytest.raises(ValueError, match="PAPER_PREDICTION_DUPLICATE"):
        ledger.append_prediction(prediction)
    invalid = PaperPrediction(**{**prediction.__dict__, "point_in_time_certifiable": False,
                                 "fixture_id": "fixture-3"})
    with pytest.raises(ValueError, match="PAPER_PREDICTION_EVIDENCE_NOT_CERTIFIABLE"):
        ledger.append_prediction(invalid)


def test_team_form_challenger_is_expanding_window_and_excludes_future_rows():
    report = evaluate_team_form_challenger(
        comparison_rows(), evaluation_as_of=BASE + timedelta(days=20)
    )
    assert report.scored_targets == 3
    assert report.metrics is not None
    assert report.metrics.sample_count == 3
    assert report.metrics.form_mse >= 0
    assert report.metrics.competition_baseline_mse >= 0
