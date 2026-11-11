"""Leakage-resistant expanding-window evaluation split contracts.

This module partitions already-collected historical fixtures only. It does not
fit models, score forecasts, fetch providers, or write to a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable


@dataclass(frozen=True, slots=True)
class EvaluationFixture:
    fixture_id: str
    kickoff_utc: datetime
    settled_at_utc: datetime

    def __post_init__(self) -> None:
        for field_name in ("kickoff_utc", "settled_at_utc"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
            object.__setattr__(self, field_name, value.astimezone(timezone.utc))
        if not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if self.settled_at_utc < self.kickoff_utc:
            raise ValueError("settlement cannot precede kickoff")


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_number: int
    train_fixture_ids: tuple[str, ...]
    test_fixture_ids: tuple[str, ...]
    test_start_utc: datetime
    test_end_utc: datetime
    training_label_cutoff_utc: datetime


def build_expanding_walk_forward_folds(
    fixtures: Iterable[EvaluationFixture],
    *,
    first_test_start_utc: datetime,
    test_window: timedelta,
    n_splits: int,
    embargo: timedelta = timedelta(0),
    min_train_fixtures: int = 1,
) -> tuple[WalkForwardFold, ...]:
    """Create chronological test windows with labels settled before train cutoff.

    Training rows must kick off before the test window and their outcomes must
    have settled no later than test_start - embargo. Test windows are disjoint.
    """
    if first_test_start_utc.tzinfo is None or first_test_start_utc.utcoffset() is None:
        raise ValueError("first_test_start_utc must be timezone-aware")
    if test_window <= timedelta(0):
        raise ValueError("test_window must be positive")
    if n_splits < 1 or min_train_fixtures < 1:
        raise ValueError("n_splits and min_train_fixtures must be positive")
    if embargo < timedelta(0):
        raise ValueError("embargo cannot be negative")

    rows = tuple(fixtures)
    ids = [row.fixture_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate fixture IDs are not allowed")

    first_start = first_test_start_utc.astimezone(timezone.utc)
    folds: list[WalkForwardFold] = []
    for index in range(n_splits):
        start = first_start + index * test_window
        end = start + test_window
        label_cutoff = start - embargo
        train = tuple(sorted(
            row.fixture_id for row in rows
            if row.kickoff_utc < start and row.settled_at_utc <= label_cutoff
        ))
        test = tuple(sorted(
            row.fixture_id for row in rows
            if start <= row.kickoff_utc < end
        ))
        if len(train) < min_train_fixtures:
            raise ValueError(
                f"fold {index + 1} has {len(train)} eligible training fixtures; "
                f"requires {min_train_fixtures}"
            )
        if not test:
            raise ValueError(f"fold {index + 1} has no test fixtures")
        folds.append(WalkForwardFold(
            fold_number=index + 1,
            train_fixture_ids=train,
            test_fixture_ids=test,
            test_start_utc=start,
            test_end_utc=end,
            training_label_cutoff_utc=label_cutoff,
        ))
    return tuple(folds)
