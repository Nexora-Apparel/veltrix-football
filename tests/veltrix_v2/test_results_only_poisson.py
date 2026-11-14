from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.models.poisson import (
    InsufficientHistoryError,
    MatchObservation,
    predict_match,
)

UTC = timezone.utc
CUTOFF = datetime(2026, 11, 14, 12, tzinfo=UTC)
KICKOFF = CUTOFF + timedelta(hours=4)


def match(i, home, away, hg, ag, *, available=None, recorded=None, kickoff=None, comp="league"):
    return MatchObservation(
        fixture_id=f"f{i}", competition_id=comp,
        home_team_id=home, away_team_id=away,
        kickoff_at=kickoff or CUTOFF - timedelta(days=i + 1),
        available_at=available or CUTOFF - timedelta(days=i),
        recorded_at=recorded or CUTOFF - timedelta(days=i),
        home_goals=hg, away_goals=ag,
    )


def sample_history(n=120):
    rows = []
    teams = ["A", "B", "C", "D", "E", "F"]
    for i in range(n):
        home = teams[i % len(teams)]
        away = teams[(i + 1 + (i % 4)) % len(teams)]
        if home == away:
            away = teams[(i + 2) % len(teams)]
        rows.append(match(i, home, away, 1 + (i % 3 == 0), i % 2))
    return rows


def test_model_emits_normalized_probabilities_and_explicit_evidence_counts():
    result = predict_match(sample_history(), competition_id="league",
                           home_team_id="A", away_team_id="B",
                           kickoff_at=KICKOFF, cutoff_at=CUTOFF)
    assert result.home_win + result.draw + result.away_win == pytest.approx(1.0)
    assert 0 <= result.btts_yes <= 1
    assert 0 <= result.over_2_5 <= 1
    assert result.evidence_match_count == 120
    assert result.home_team_match_count > 0 and result.away_team_match_count > 0
    assert result.model_version == "veltrix-results-poisson-v1"


def test_late_published_or_late_recorded_results_are_excluded():
    rows = sample_history(120)
    rows.append(match(999, "A", "B", 9, 0, available=CUTOFF + timedelta(seconds=1)))
    rows.append(match(1000, "A", "B", 9, 0, recorded=CUTOFF + timedelta(seconds=1)))
    result = predict_match(rows, competition_id="league", home_team_id="A",
                           away_team_id="B", kickoff_at=KICKOFF, cutoff_at=CUTOFF)
    assert result.evidence_match_count == 120


def test_future_kickoff_and_other_competition_are_excluded():
    rows = sample_history(120)
    rows.append(match(999, "A", "B", 9, 0, kickoff=CUTOFF + timedelta(minutes=1)))
    rows.append(match(1000, "A", "B", 9, 0, comp="other"))
    result = predict_match(rows, competition_id="league", home_team_id="A",
                           away_team_id="B", kickoff_at=KICKOFF, cutoff_at=CUTOFF)
    assert result.evidence_match_count == 120


def test_no_generic_league_only_prediction_when_team_history_is_absent():
    with pytest.raises(InsufficientHistoryError, match="HOME_TEAM_HAS_NO_ELIGIBLE_HISTORY"):
        predict_match(sample_history(), competition_id="league", home_team_id="UNKNOWN",
                      away_team_id="A", kickoff_at=KICKOFF, cutoff_at=CUTOFF)


def test_one_or_two_team_matches_are_used_but_not_marked_publishable():
    rows = [match(1, "A", "C", 2, 0), match(2, "B", "A", 1, 1),
            match(3, "D", "B", 0, 1), match(4, "C", "D", 1, 0)]
    result = predict_match(rows, competition_id="league", home_team_id="A",
                           away_team_id="B", kickoff_at=KICKOFF, cutoff_at=CUTOFF)
    assert result.home_team_match_count == 2
    assert result.away_team_match_count == 2
    assert not result.publishable
    assert result.publication_reason == "INSUFFICIENT_EVIDENCE_FOR_PUBLICATION"


def test_naive_timestamps_and_invalid_scores_are_not_admitted():
    bad_time = MatchObservation("bad", "league", "A", "B", CUTOFF.replace(tzinfo=None),
                                CUTOFF, CUTOFF, 1, 0)
    bad_score = MatchObservation("bad2", "league", "A", "B", CUTOFF,
                                 CUTOFF, CUTOFF, True, 0)
    result = predict_match(sample_history() + [bad_time, bad_score],
                           competition_id="league", home_team_id="A",
                           away_team_id="B", kickoff_at=KICKOFF, cutoff_at=CUTOFF)
    assert result.evidence_match_count == 120


def test_target_cutoff_must_precede_kickoff():
    with pytest.raises(ValueError, match="TARGET_KICKOFF_MUST_BE_AFTER_CUTOFF"):
        predict_match(sample_history(), competition_id="league", home_team_id="A",
                      away_team_id="B", kickoff_at=CUTOFF, cutoff_at=CUTOFF)


def test_duplicate_fixture_ids_are_excluded_without_input_order_preference():
    rows = sample_history(120)
    duplicate = rows[0]
    conflicting = MatchObservation(
        fixture_id=duplicate.fixture_id, competition_id="league",
        home_team_id="A", away_team_id="B",
        kickoff_at=duplicate.kickoff_at, available_at=duplicate.available_at,
        recorded_at=duplicate.recorded_at, home_goals=8, away_goals=0,
    )
    result = predict_match(rows + [conflicting], competition_id="league",
                           home_team_id="A", away_team_id="B",
                           kickoff_at=KICKOFF, cutoff_at=CUTOFF)
    assert result.evidence_match_count == 119


def test_result_cannot_be_available_before_kickoff_or_recorded_before_available():
    rows = sample_history(120)
    invalid = MatchObservation(
        fixture_id="invalid-time-order", competition_id="league",
        home_team_id="A", away_team_id="B",
        kickoff_at=CUTOFF - timedelta(days=3),
        available_at=CUTOFF - timedelta(days=4),
        recorded_at=CUTOFF - timedelta(days=4),
        home_goals=9, away_goals=0,
    )
    result = predict_match(rows + [invalid], competition_id="league",
                           home_team_id="A", away_team_id="B",
                           kickoff_at=KICKOFF, cutoff_at=CUTOFF)
    assert result.evidence_match_count == 120
