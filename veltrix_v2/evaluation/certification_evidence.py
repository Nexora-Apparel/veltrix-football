"""Evidence derivation primitives for VELTRIX V2 certification.

All counts and financial metrics in this module are derived from evaluator
outputs, the immutable prospective ledger, and raw OddsSnapshot records.
This module intentionally does not accept caller-supplied counts or pass flags.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Iterable

from veltrix_v2.contracts.odds import OddsSnapshot
from veltrix_v2.evaluation.multi_competition_walk_forward import (
    MultiCompetitionWalkForwardEvaluation,
)
from veltrix_v2.evaluation.paper_ledger import PaperLedger
from veltrix_v2.evaluation.roi import MarketPerformance, evaluate_roi

_EXPECTED_SELECTIONS = {
    "1X2": frozenset({"HOME", "DRAW", "AWAY"}),
    "BTTS": frozenset({"YES", "NO"}),
    "TOTALS": frozenset({"OVER", "UNDER"}),
}


@dataclass(frozen=True, slots=True)
class TimestampedOddsCoverage:
    market: str
    eligible_fixture_ids: tuple[str, ...]
    covered_fixture_ids: tuple[str, ...]
    eligible_fixture_count: int
    covered_fixture_count: int
    coverage: Decimal | None


@dataclass(frozen=True, slots=True)
class DerivedMarketEvidence:
    """Computed evidence; no caller-provided metric or pass/fail fields."""

    market: str
    walk_forward_matches: int
    prospective_settled_selections: int
    distinct_dates: int
    timestamped_odds: TimestampedOddsCoverage
    roi_performance: MarketPerformance


def _eligible_ids(report: MultiCompetitionWalkForwardEvaluation) -> tuple[str, ...]:
    ids = tuple(
        fixture_id
        for scope in report.scope_reports
        for fold in scope.folds
        for fixture_id in fold.eligible_fixture_ids
    )
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("CERTIFICATION_WALK_FORWARD_ELIGIBLE_FIXTURES_INVALID")
    return ids


def _walk_forward_sample_size(
    report: MultiCompetitionWalkForwardEvaluation, market: str
) -> int:
    aggregate = {
        "1X2": report.aggregate_1x2,
        "BTTS": report.aggregate_btts,
        "TOTALS": report.aggregate_totals,
    }[market]
    if aggregate is None:
        return 0
    size = aggregate.sample_size
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError("CERTIFICATION_WALK_FORWARD_SAMPLE_SIZE_INVALID")
    return size


def derive_timestamped_odds_coverage(
    eligible_fixture_ids: Iterable[str],
    snapshots: Iterable[OddsSnapshot],
    *,
    market: str,
) -> TimestampedOddsCoverage:
    """Count fixtures with at least one complete, point-in-time quote group.

    A group is complete only when every market selection is present for the
    same fixture, source, bookmaker, line, capture time and kickoff, and every
    quote has a provider quote timestamp strictly before kickoff and no later
    than local capture. Partial groups never count toward coverage.
    """
    canonical = "TOTALS" if market == "OVER_UNDER" else market
    expected = _EXPECTED_SELECTIONS.get(canonical)
    if expected is None:
        raise ValueError("CERTIFICATION_ODDS_MARKET_UNSUPPORTED")

    eligible = tuple(eligible_fixture_ids)
    if not eligible or len(eligible) != len(set(eligible)):
        raise ValueError("CERTIFICATION_ODDS_ELIGIBLE_FIXTURES_INVALID")
    eligible_set = set(eligible)

    groups: dict[tuple[object, ...], dict[str, OddsSnapshot]] = {}
    seen_snapshot_ids: set[str] = set()
    for row in snapshots:
        if not isinstance(row, OddsSnapshot):
            raise ValueError("CERTIFICATION_ODDS_SNAPSHOT_TYPE_INVALID")
        row_market = "TOTALS" if row.market.upper() == "OVER_UNDER" else row.market.upper()
        if row_market != canonical or row.fixture_id not in eligible_set:
            continue
        if row.snapshot_id in seen_snapshot_ids:
            raise ValueError("CERTIFICATION_ODDS_DUPLICATE_SNAPSHOT_ID")
        seen_snapshot_ids.add(row.snapshot_id)
        if row.provider_quote_at is None:
            continue
        if not (row.provider_quote_at < row.kickoff_at and row.provider_quote_at <= row.captured_at < row.kickoff_at):
            continue
        key = (
            row.fixture_id, row.source_id, row.bookmaker_id, row_market,
            row.line, row.captured_at, row.kickoff_at,
        )
        group = groups.setdefault(key, {})
        selection = row.selection.upper()
        if selection in group:
            raise ValueError("CERTIFICATION_ODDS_DUPLICATE_SELECTION")
        group[selection] = row

    covered: set[str] = set()
    for key, group in groups.items():
        fixture_id = key[0]
        if frozenset(group) == expected:
            covered.add(str(fixture_id))

    covered_ids = tuple(sorted(covered))
    return TimestampedOddsCoverage(
        market=canonical,
        eligible_fixture_ids=eligible,
        covered_fixture_ids=covered_ids,
        eligible_fixture_count=len(eligible),
        covered_fixture_count=len(covered_ids),
        coverage=Decimal(len(covered_ids)) / Decimal(len(eligible)) if eligible else None,
    )


def derive_market_evidence(
    walk_forward: MultiCompetitionWalkForwardEvaluation,
    paper_ledger: PaperLedger,
    odds_snapshots: Iterable[OddsSnapshot],
    *,
    market: str,
    bootstrap_draws: int = 2000,
    bootstrap_seed: int = 20261112,
) -> DerivedMarketEvidence:
    """Derive every market-level certification metric from source records."""
    canonical = "TOTALS" if market == "OVER_UNDER" else market
    if canonical not in _EXPECTED_SELECTIONS:
        raise ValueError("CERTIFICATION_MARKET_UNSUPPORTED")
    if not isinstance(walk_forward, MultiCompetitionWalkForwardEvaluation):
        raise ValueError("CERTIFICATION_WALK_FORWARD_REPORT_REQUIRED")
    if not isinstance(paper_ledger, PaperLedger):
        raise ValueError("CERTIFICATION_PAPER_LEDGER_REQUIRED")

    eligible_ids = _eligible_ids(walk_forward)
    counts = paper_ledger.counts_for_market(canonical)
    settlements = paper_ledger.settlements_for_market(canonical)
    # ROI is recomputed from the authoritative ledger settlements. No supplied
    # MarketPerformance object is accepted as certification input.
    roi_report = evaluate_roi(
        settlements,
        bootstrap_draws=bootstrap_draws,
        bootstrap_seed=bootstrap_seed,
    )
    performance = next(
        (row for row in roi_report.markets if row.market in {canonical, "OVER_UNDER" if canonical == "TOTALS" else canonical}),
        None,
    )
    if performance is None:
        # An empty ledger is explicit zero evidence, not a missing report.
        performance = MarketPerformance(
            market=canonical,
            total_bets=0, wins=0, losses=0, pushes=0, voids=0,
            decisive_bets=0, settled_bets=0,
            win_rate=None, win_rate_ci_95=None,
            settled_turnover=Decimal("0"), gross_return=Decimal("0"),
            net_profit=Decimal("0"), roi=None, roi_ci_95=None,
            roi_ci_method="unavailable_insufficient_match_dates",
        )
    elif performance.market != canonical:
        performance = replace(performance, market=canonical)
    odds = derive_timestamped_odds_coverage(
        eligible_ids, odds_snapshots, market=canonical
    )
    return DerivedMarketEvidence(
        market=canonical,
        walk_forward_matches=_walk_forward_sample_size(walk_forward, canonical),
        prospective_settled_selections=counts.settled_count,
        distinct_dates=counts.distinct_settled_dates,
        timestamped_odds=odds,
        roi_performance=performance,
    )



@dataclass(frozen=True, slots=True)
class TrainingObservationEvidence:
    """Database observation identity joined to its immutable provider record."""

    observation_id: str
    observation: "ProviderObservation"

    def __post_init__(self) -> None:
        from veltrix_v2.contracts import ProviderObservation
        if not isinstance(self.observation_id, str) or not self.observation_id.strip():
            raise ValueError("CERTIFICATION_TRAINING_OBSERVATION_ID_REQUIRED")
        if not isinstance(self.observation, ProviderObservation):
            raise ValueError("CERTIFICATION_PROVIDER_OBSERVATION_REQUIRED")


@dataclass(frozen=True, slots=True)
class TrainingSourceAudit:
    """Record-derived source and point-in-time audit for walk-forward training."""

    observation_count: int
    approved_observation_ids: tuple[str, ...]
    rejected_observations: tuple[tuple[str, str], ...]
    passed: bool


def audit_walk_forward_training_sources(
    walk_forward: MultiCompetitionWalkForwardEvaluation,
    observations: Iterable[TrainingObservationEvidence],
    approvals: Iterable["SourceApproval"],
) -> TrainingSourceAudit:
    """Audit model-training and held-out result records against source rights.

    Training observations must be available by the fold's training-label
    cutoff and explicitly licensed for model training. Held-out result
    observations must be post-kickoff and licensed for benchmarking. Every
    referenced source observation must resolve to an immutable provider record.
    """
    from datetime import timedelta
    from veltrix_v2.contracts import ForecastCutoff
    from veltrix_v2.quality.eligibility import SourceApproval, evaluate_observation

    if not isinstance(walk_forward, MultiCompetitionWalkForwardEvaluation):
        raise ValueError("CERTIFICATION_WALK_FORWARD_REPORT_REQUIRED")
    observation_rows = tuple(observations)
    approval_rows = tuple(approvals)
    if any(not isinstance(row, TrainingObservationEvidence) for row in observation_rows):
        raise ValueError("CERTIFICATION_TRAINING_OBSERVATION_EVIDENCE_TYPE_INVALID")
    if any(not isinstance(row, SourceApproval) for row in approval_rows):
        raise ValueError("CERTIFICATION_SOURCE_APPROVAL_TYPE_INVALID")
    by_id = {row.observation_id: row.observation for row in observation_rows}
    if len(by_id) != len(observation_rows):
        raise ValueError("CERTIFICATION_DUPLICATE_TRAINING_OBSERVATION_ID")

    approved: set[str] = set()
    rejected: list[tuple[str, str]] = []
    required_ids: set[str] = set()
    for scope_report in walk_forward.scope_reports:
        scope = (scope_report.competition_key, scope_report.season)
        for fold in scope_report.folds:
            cutoff = ForecastCutoff(fold.training_label_cutoff_utc)
            for observation_id in fold.training_observation_ids:
                required_ids.add(observation_id)
                observation = by_id.get(observation_id)
                if observation is None:
                    rejected.append((observation_id, "training_observation_missing"))
                    continue
                if (observation.competition_key, observation.season) != scope:
                    rejected.append((observation_id, "training_observation_scope_mismatch"))
                    continue
                decision = evaluate_observation(
                    observation,
                    data_type=observation.entity_type,
                    cutoff=cutoff,
                    approvals=approval_rows,
                    max_age=timedelta.max,
                    required_uses=("collection", "storage", "model_training"),
                )
                if not decision.eligible:
                    rejected.append((observation_id, decision.reason))
                else:
                    approved.add(observation_id)

            kickoff_by_observation = {
                observation_id: (fixture_id, kickoff)
                for fixture_id, observation_id, kickoff in fold.test_fixture_kickoffs
            }
            if (
                set(kickoff_by_observation) != set(fold.test_observation_ids)
                or {fixture for fixture, _ in kickoff_by_observation.values()} != set(fold.eligible_fixture_ids)
            ):
                rejected.append(("*", "held_out_result_fixture_provenance_mismatch"))
            for observation_id in fold.test_observation_ids:
                required_ids.add(observation_id)
                observation = by_id.get(observation_id)
                if observation is None:
                    rejected.append((observation_id, "held_out_result_observation_missing"))
                    continue
                if (observation.competition_key, observation.season) != scope:
                    rejected.append((observation_id, "held_out_result_scope_mismatch"))
                    continue
                fixture = kickoff_by_observation.get(observation_id)
                if fixture is None:
                    rejected.append((observation_id, "held_out_result_kickoff_missing"))
                    continue
                _, kickoff = fixture
                if observation.available_at_utc < kickoff or observation.source_event_time_utc < kickoff:
                    rejected.append((observation_id, "held_out_result_observed_before_kickoff"))
                    continue
                decision = evaluate_observation(
                    observation,
                    data_type=observation.entity_type,
                    cutoff=ForecastCutoff(observation.retrieved_at_utc),
                    approvals=approval_rows,
                    max_age=timedelta.max,
                    required_uses=("collection", "storage", "benchmarking"),
                )
                if not decision.eligible:
                    rejected.append((observation_id, decision.reason))
                else:
                    approved.add(observation_id)

    if not required_ids:
        rejected.append(("*", "walk_forward_has_no_source_provenance"))
    failures = tuple(sorted(set(rejected)))
    return TrainingSourceAudit(
        observation_count=len(required_ids),
        approved_observation_ids=tuple(sorted(approved)),
        rejected_observations=failures,
        passed=bool(required_ids) and not failures and approved == required_ids,
    )


@dataclass(frozen=True, slots=True)
class WalkForwardIntegrityAudit:
    fold_count: int
    held_out_fixture_ids: tuple[str, ...]
    passed: bool
    failures: tuple[str, ...]


def audit_walk_forward_integrity(
    walk_forward: MultiCompetitionWalkForwardEvaluation,
) -> WalkForwardIntegrityAudit:
    """Recheck fold identity, temporal boundaries and held-out isolation."""
    if not isinstance(walk_forward, MultiCompetitionWalkForwardEvaluation):
        raise ValueError("CERTIFICATION_WALK_FORWARD_REPORT_REQUIRED")
    failures: list[str] = []
    held_out_ids: list[str] = []
    for scope_report in walk_forward.scope_reports:
        previous_end = None
        fold_numbers: set[int] = set()
        for fold in scope_report.folds:
            if fold.fold_number in fold_numbers:
                failures.append("DUPLICATE_FOLD_NUMBER")
            fold_numbers.add(fold.fold_number)
            if not (
                fold.training_label_cutoff_utc.tzinfo is not None
                and fold.test_start_utc.tzinfo is not None
                and fold.test_end_utc.tzinfo is not None
            ):
                failures.append("FOLD_TEMPORAL_BOUNDARY_NOT_TIMEZONE_AWARE")
                continue
            if not (
                fold.training_label_cutoff_utc < fold.test_start_utc < fold.test_end_utc
            ):
                failures.append("TRAINING_CUTOFF_OR_TEST_WINDOW_ORDER_INVALID")
            if previous_end is not None and fold.test_start_utc < previous_end:
                failures.append("HELD_OUT_TEST_WINDOWS_OVERLAP_OR_REVERSE")
            previous_end = fold.test_end_utc
            train_ids = tuple(fold.training_fixture_ids)
            test_ids = tuple(fold.eligible_fixture_ids)
            training_observation_ids = tuple(fold.training_observation_ids)
            test_observation_ids = tuple(fold.test_observation_ids)
            if not train_ids or len(train_ids) != len(set(train_ids)):
                failures.append("TRAINING_FIXTURE_IDENTITIES_INVALID")
            if not test_ids or len(test_ids) != len(set(test_ids)):
                failures.append("HELD_OUT_FIXTURE_IDENTITIES_INVALID")
            if set(train_ids) & set(test_ids):
                failures.append("TRAINING_AND_HELD_OUT_FIXTURES_OVERLAP")
            if not training_observation_ids or len(training_observation_ids) != len(set(training_observation_ids)):
                failures.append("TRAINING_OBSERVATION_IDENTITIES_INVALID")
            if (
                len(test_observation_ids) != len(test_ids)
                or len(test_observation_ids) != len(set(test_observation_ids))
            ):
                failures.append("HELD_OUT_RESULT_PROVENANCE_INVALID")
            held_out_ids.extend(test_ids)
    if not held_out_ids or len(held_out_ids) != len(set(held_out_ids)):
        failures.append("HELD_OUT_FIXTURES_MISSING_OR_REPEATED_ACROSS_FOLDS")
    unique_failures = tuple(sorted(set(failures)))
    return WalkForwardIntegrityAudit(
        fold_count=sum(len(scope.folds) for scope in walk_forward.scope_reports),
        held_out_fixture_ids=tuple(held_out_ids),
        passed=bool(held_out_ids) and not unique_failures,
        failures=unique_failures,
    )
