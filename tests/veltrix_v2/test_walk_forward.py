"""Leakage and chronology tests for walk-forward fold construction."""
from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.evaluation.walk_forward import (
    EvaluationFixture,
    build_expanding_walk_forward_folds,
)

UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def row(name, kickoff_day, settled_day):
    return EvaluationFixture(
        fixture_id=name,
        kickoff_utc=BASE + timedelta(days=kickoff_day),
        settled_at_utc=BASE + timedelta(days=settled_day),
    )


def test_expanding_folds_are_chronological_and_test_windows_disjoint():
    rows = [
        row("old-1", 1, 1), row("old-2", 2, 2), row("old-3", 3, 3),
        row("test-1", 10, 10), row("test-2", 15, 15),
        row("test-3", 20, 20),
    ]
    folds = build_expanding_walk_forward_folds(
        rows,
        first_test_start_utc=BASE + timedelta(days=10),
        test_window=timedelta(days=5),
        n_splits=3,
        min_train_fixtures=3,
    )
    assert folds[0].train_fixture_ids == ("old-1", "old-2", "old-3")
    assert folds[0].test_fixture_ids == ("test-1",)
    assert folds[1].test_fixture_ids == ("test-2",)
    assert folds[2].test_fixture_ids == ("test-3",)
    assert set(folds[0].test_fixture_ids).isdisjoint(folds[1].test_fixture_ids)


def test_unsettled_training_labels_are_excluded():
    rows = [
        row("settled", 1, 1),
        row("late-settled", 2, 9),
        row("test", 10, 10),
    ]
    fold = build_expanding_walk_forward_folds(
        rows,
        first_test_start_utc=BASE + timedelta(days=10),
        test_window=timedelta(days=5),
        n_splits=1,
    )[0]
    assert fold.train_fixture_ids == ("settled",)


def test_embargo_excludes_recently_settled_labels():
    rows = [row("old", 1, 1), row("recent", 7, 9), row("test", 10, 10)]
    fold = build_expanding_walk_forward_folds(
        rows,
        first_test_start_utc=BASE + timedelta(days=10),
        test_window=timedelta(days=5),
        n_splits=1,
        embargo=timedelta(days=2),
    )[0]
    assert fold.training_label_cutoff_utc == BASE + timedelta(days=8)
    assert fold.train_fixture_ids == ("old",)


def test_duplicate_fixture_ids_fail_closed():
    with pytest.raises(ValueError, match="duplicate fixture IDs"):
        build_expanding_walk_forward_folds(
            [row("same", 1, 1), row("same", 2, 2)],
            first_test_start_utc=BASE + timedelta(days=10),
            test_window=timedelta(days=5),
            n_splits=1,
        )


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        EvaluationFixture("bad", datetime(2026, 1, 1), BASE)


def test_missing_test_window_fails_closed():
    with pytest.raises(ValueError, match="no test fixtures"):
        build_expanding_walk_forward_folds(
            [row("old", 1, 1)],
            first_test_start_utc=BASE + timedelta(days=10),
            test_window=timedelta(days=5),
            n_splits=1,
        )


def test_minimum_training_size_is_enforced():
    with pytest.raises(ValueError, match="eligible training fixtures"):
        build_expanding_walk_forward_folds(
            [row("old", 1, 1), row("test", 10, 10)],
            first_test_start_utc=BASE + timedelta(days=10),
            test_window=timedelta(days=5),
            n_splits=1,
            min_train_fixtures=2,
        )
