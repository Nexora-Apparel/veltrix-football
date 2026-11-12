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
            training_provenance = {
                observation_id: (fixture_id, kickoff, available_at)
                for fixture_id, observation_id, kickoff, available_at in fold.training_observation_provenance
            }
            if (
                set(training_provenance) != set(fold.training_observation_ids)
                or {fixture_id for fixture_id, _, _ in training_provenance.values()} != set(fold.training_fixture_ids)
            ):
                rejected.append(("*", "training_fixture_observation_provenance_mismatch"))
            for observation_id in fold.training_observation_ids:
                required_ids.add(observation_id)
                observation = by_id.get(observation_id)
                if observation is None:
                    rejected.append((observation_id, "training_observation_missing"))
                    continue
                if (observation.competition_key, observation.season) != scope:
                    rejected.append((observation_id, "training_observation_scope_mismatch"))
                    continue
                provenance = training_provenance.get(observation_id)
                if provenance is None:
                    rejected.append((observation_id, "training_observation_fixture_link_missing"))
                    continue
                fixture_id, kickoff, recorded_available_at = provenance
                if (
                    observation.available_at_utc <= kickoff
                    or observation.available_at_utc > recorded_available_at
                ):
                    rejected.append((observation_id, "training_result_availability_provenance_invalid"))
                    continue
                observed_fixture_id = observation.values.get("fixture_id")
                if observed_fixture_id is not None and observed_fixture_id != fixture_id:
                    rejected.append((observation_id, "training_observation_fixture_id_mismatch"))
                    continue
                decision = evaluate_observation(
                    observation,
                    data_type=observation.entity_type,
                    cutoff=cutoff,
                    approvals=approval_rows,
                    max_age=timedelta.max,
                    required_uses=("collection", "storage", "model_training", "public_display", "commercial_use"),
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
                fixture_id, kickoff = fixture
                if observation.available_at_utc <= kickoff:
                    rejected.append((observation_id, "held_out_result_observed_before_kickoff"))
                    continue
                observed_fixture_id = observation.values.get("fixture_id")
                if observed_fixture_id is not None and observed_fixture_id != fixture_id:
                    rejected.append((observation_id, "held_out_result_fixture_id_mismatch"))
                    continue
                decision = evaluate_observation(
                    observation,
                    data_type=observation.entity_type,
                    cutoff=ForecastCutoff(observation.retrieved_at_utc),
                    approvals=approval_rows,
                    max_age=timedelta.max,
                    required_uses=("collection", "storage", "benchmarking", "commercial_use"),
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
    from veltrix_v2.evaluation.binary_metrics import score_binary_market
    from veltrix_v2.evaluation.metrics import score_1x2

    def coverage_matches(coverage, eligible_count: int, forecast_count: int) -> bool:
        expected = forecast_count / eligible_count if eligible_count else None
        return (
            coverage.eligible_fixture_count == eligible_count
            and coverage.forecast_count == forecast_count
            and coverage.abstention_count == eligible_count - forecast_count
            and coverage.coverage == expected
        )

    failures: list[str] = []
    held_out_ids: list[str] = []
    scope_eligible_ids: list[str] = []
    scope_forecasts_1x2 = []
    scope_outcomes_1x2 = []
    scope_forecasts_btts = []
    scope_outcomes_btts = []
    scope_forecasts_totals = []
    scope_outcomes_totals = []
    recomputed_test_count = 0
    recomputed_fold_count = 0
    recomputed_forecast_count = 0

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
            training_provenance = tuple(fold.training_observation_provenance)
            training_provenance_fixture_ids = {fixture_id for fixture_id, _, _, _ in training_provenance}
            training_provenance_observation_ids = {observation_id for _, observation_id, _, _ in training_provenance}
            if (
                not train_ids
                or len(train_ids) != len(set(train_ids))
                or training_provenance_fixture_ids != set(train_ids)
                or training_provenance_observation_ids != set(training_observation_ids)
                or len(training_provenance) != len(train_ids)
            ):
                failures.append("TRAINING_FIXTURE_OBSERVATION_PROVENANCE_INVALID")
            if any(
                kickoff >= available_at or available_at > fold.training_label_cutoff_utc
                for _, _, kickoff, available_at in training_provenance
            ):
                failures.append("TRAINING_FIXTURE_NOT_BEFORE_LABEL_CUTOFF")
            if not test_ids or len(test_ids) != len(set(test_ids)):
                failures.append("HELD_OUT_FIXTURE_IDENTITIES_INVALID")
            if set(train_ids) & set(test_ids):
                failures.append("TRAINING_AND_HELD_OUT_FIXTURES_OVERLAP")
            if not training_observation_ids or len(training_observation_ids) != len(set(training_observation_ids)):
                failures.append("TRAINING_OBSERVATION_IDENTITIES_INVALID")
            kickoff_rows = tuple(fold.test_fixture_kickoffs)
            kickoff_fixture_ids = {fixture_id for fixture_id, _, _ in kickoff_rows}
            kickoff_observation_ids = {observation_id for _, observation_id, _ in kickoff_rows}
            if (
                len(test_observation_ids) != len(test_ids)
                or len(test_observation_ids) != len(set(test_observation_ids))
                or kickoff_observation_ids != set(test_observation_ids)
                or kickoff_fixture_ids != set(test_ids)
                or len(kickoff_rows) != len(test_ids)
            ):
                failures.append("HELD_OUT_RESULT_PROVENANCE_INVALID")
            for fixture_id, _, kickoff in kickoff_rows:
                if not (
                    fold.test_start_utc <= kickoff < fold.test_end_utc
                ):
                    failures.append("HELD_OUT_FIXTURE_KICKOFF_OUTSIDE_TEST_WINDOW")
            held_out_ids.extend(test_ids)
            scope_eligible_ids.extend(test_ids)
            recomputed_test_count += fold.test_fixture_count
            recomputed_forecast_count += len(fold.forecasts_1x2)
            recomputed_fold_count += 1

            fold_1x2 = score_1x2(fold.forecasts_1x2, fold.outcomes_1x2) if fold.forecasts_1x2 else None
            fold_btts = (
                score_binary_market(
                    fold.btts_forecasts, fold.btts_outcomes,
                    eligible_fixture_ids=test_ids,
                )
                if fold.btts_forecasts else None
            )
            fold_totals = (
                score_binary_market(
                    fold.totals_forecasts, fold.totals_outcomes,
                    eligible_fixture_ids=test_ids,
                )
                if fold.totals_forecasts else None
            )
            if (
                fold.score_1x2 != fold_1x2
                or fold.btts_report != fold_btts
                or fold.totals_report != fold_totals
            ):
                failures.append("FOLD_SCORE_REPORT_DOES_NOT_MATCH_HELD_OUT_RECORDS")
            if (
                fold.forecast_count != len(fold.forecasts_1x2)
                or not coverage_matches(fold.coverage_1x2, fold.test_fixture_count, len(fold.forecasts_1x2))
                or not coverage_matches(fold.coverage_btts, fold.test_fixture_count, len(fold.btts_forecasts))
                or not coverage_matches(fold.coverage_totals, fold.test_fixture_count, len(fold.totals_forecasts))
                or set(fold.abstained_fixture_ids) != set(test_ids) - {row.fixture_id for row in fold.forecasts_1x2}
                or len(fold.abstained_fixture_ids) != len(set(fold.abstained_fixture_ids))
            ):
                failures.append("FOLD_MARKET_COVERAGE_DOES_NOT_MATCH_HELD_OUT_RECORDS")

        scope_eligible = tuple(
            fixture_id
            for fold in scope_report.folds
            for fixture_id in fold.eligible_fixture_ids
        )
        scope_folds = scope_report.folds
        scope_1x2_forecasts = tuple(row for fold in scope_folds for row in fold.forecasts_1x2)
        scope_1x2_outcomes = tuple(row for fold in scope_folds for row in fold.outcomes_1x2)
        scope_btts_forecasts = tuple(row for fold in scope_folds for row in fold.btts_forecasts)
        scope_btts_outcomes = tuple(row for fold in scope_folds for row in fold.btts_outcomes)
        scope_totals_forecasts = tuple(row for fold in scope_folds for row in fold.totals_forecasts)
        scope_totals_outcomes = tuple(row for fold in scope_folds for row in fold.totals_outcomes)
        expected_scope_1x2 = score_1x2(scope_1x2_forecasts, scope_1x2_outcomes) if scope_1x2_forecasts else None
        expected_scope_btts = (
            score_binary_market(scope_btts_forecasts, scope_btts_outcomes, eligible_fixture_ids=scope_eligible)
            if scope_btts_forecasts else None
        )
        expected_scope_totals = (
            score_binary_market(scope_totals_forecasts, scope_totals_outcomes, eligible_fixture_ids=scope_eligible)
            if scope_totals_forecasts else None
        )
        if (
            scope_report.aggregate_1x2 != expected_scope_1x2
            or scope_report.aggregate_btts != expected_scope_btts
            or scope_report.aggregate_totals != expected_scope_totals
        ):
            failures.append("SCOPE_AGGREGATE_REPORT_DOES_NOT_MATCH_FOLD_RECORDS")
        expected_scope_test_count = sum(fold.test_fixture_count for fold in scope_folds)
        expected_scope_forecast_count = len(scope_1x2_forecasts)
        if (
            scope_report.total_test_fixtures != expected_scope_test_count
            or scope_report.total_forecasts != expected_scope_forecast_count
            or scope_report.total_abstentions != expected_scope_test_count - expected_scope_forecast_count
            or not coverage_matches(scope_report.aggregate_coverage_1x2, expected_scope_test_count, len(scope_1x2_forecasts))
            or not coverage_matches(scope_report.aggregate_coverage_btts, expected_scope_test_count, len(scope_btts_forecasts))
            or not coverage_matches(scope_report.aggregate_coverage_totals, expected_scope_test_count, len(scope_totals_forecasts))
        ):
            failures.append("SCOPE_COUNTS_DO_NOT_MATCH_FOLD_RECORDS")

        scope_forecasts_1x2.extend(scope_1x2_forecasts)
        scope_outcomes_1x2.extend(scope_1x2_outcomes)
        scope_forecasts_btts.extend(scope_btts_forecasts)
        scope_outcomes_btts.extend(scope_btts_outcomes)
        scope_forecasts_totals.extend(scope_totals_forecasts)
        scope_outcomes_totals.extend(scope_totals_outcomes)

    if not held_out_ids or len(held_out_ids) != len(set(held_out_ids)):
        failures.append("HELD_OUT_FIXTURES_MISSING_OR_REPEATED_ACROSS_FOLDS")
    expected_aggregate_1x2 = score_1x2(scope_forecasts_1x2, scope_outcomes_1x2) if scope_forecasts_1x2 else None
    expected_aggregate_btts = (
        score_binary_market(scope_forecasts_btts, scope_outcomes_btts, eligible_fixture_ids=scope_eligible_ids)
        if scope_forecasts_btts else None
    )
    expected_aggregate_totals = (
        score_binary_market(scope_forecasts_totals, scope_outcomes_totals, eligible_fixture_ids=scope_eligible_ids)
        if scope_forecasts_totals else None
    )
    if (
        walk_forward.aggregate_1x2 != expected_aggregate_1x2
        or walk_forward.aggregate_btts != expected_aggregate_btts
        or walk_forward.aggregate_totals != expected_aggregate_totals
    ):
        failures.append("MULTI_COMPETITION_AGGREGATES_DO_NOT_MATCH_FOLD_RECORDS")
    if (
        walk_forward.total_test_fixtures != recomputed_test_count
        or walk_forward.total_forecasts != recomputed_forecast_count
        or walk_forward.total_abstentions != recomputed_test_count - recomputed_forecast_count
        or walk_forward.total_folds != recomputed_fold_count
        or not coverage_matches(walk_forward.coverage_1x2, recomputed_test_count, len(scope_forecasts_1x2))
        or not coverage_matches(walk_forward.coverage_btts, recomputed_test_count, len(scope_forecasts_btts))
        or not coverage_matches(walk_forward.coverage_totals, recomputed_test_count, len(scope_forecasts_totals))
    ):
        failures.append("MULTI_COMPETITION_COUNTS_DO_NOT_MATCH_FOLD_RECORDS")
    unique_failures = tuple(sorted(set(failures)))
    return WalkForwardIntegrityAudit(
        fold_count=sum(len(scope.folds) for scope in walk_forward.scope_reports),
        held_out_fixture_ids=tuple(held_out_ids),
        passed=bool(held_out_ids) and not unique_failures,
        failures=unique_failures,
    )


@dataclass(frozen=True, slots=True)
class OddsSourceAudit:
    snapshot_count: int
    approved_snapshot_ids: tuple[str, ...]
    rejected_snapshots: tuple[tuple[str, str], ...]
    passed: bool


def audit_odds_snapshot_sources(
    walk_forward: MultiCompetitionWalkForwardEvaluation,
    snapshots: Iterable[OddsSnapshot],
    observations: Iterable[TrainingObservationEvidence],
    approvals: Iterable["SourceApproval"],
) -> OddsSourceAudit:
    """Verify quote-to-source lineage, point-in-time capture and benchmark rights."""
    from datetime import timedelta
    from veltrix_v2.contracts import ForecastCutoff
    from veltrix_v2.quality.eligibility import SourceApproval, evaluate_observation

    if not isinstance(walk_forward, MultiCompetitionWalkForwardEvaluation):
        raise ValueError("CERTIFICATION_WALK_FORWARD_REPORT_REQUIRED")
    snapshot_rows = tuple(snapshots)
    observation_rows = tuple(observations)
    approval_rows = tuple(approvals)
    if any(not isinstance(row, OddsSnapshot) for row in snapshot_rows):
        raise ValueError("CERTIFICATION_ODDS_SNAPSHOT_TYPE_INVALID")
    if any(not isinstance(row, TrainingObservationEvidence) for row in observation_rows):
        raise ValueError("CERTIFICATION_TRAINING_OBSERVATION_EVIDENCE_TYPE_INVALID")
    if any(not isinstance(row, SourceApproval) for row in approval_rows):
        raise ValueError("CERTIFICATION_SOURCE_APPROVAL_TYPE_INVALID")

    observation_by_id = {row.observation_id: row.observation for row in observation_rows}
    if len(observation_by_id) != len(observation_rows):
        raise ValueError("CERTIFICATION_DUPLICATE_SOURCE_OBSERVATION_ID")
    fixture_scopes = {}
    for scope_report in walk_forward.scope_reports:
        scope = (scope_report.competition_key, scope_report.season)
        for fold in scope_report.folds:
            for fixture_id in fold.eligible_fixture_ids:
                prior = fixture_scopes.setdefault(fixture_id, scope)
                if prior != scope:
                    raise ValueError("CERTIFICATION_FIXTURE_SCOPE_CONFLICT")

    approved: set[str] = set()
    rejected: list[tuple[str, str]] = []
    seen_snapshot_ids: set[str] = set()
    audited_snapshot_ids: set[str] = set()
    for snapshot in snapshot_rows:
        if snapshot.fixture_id not in fixture_scopes:
            # Prospective paper-ledger odds are audited separately against
            # their own forecast and selection records.
            continue
        audited_snapshot_ids.add(snapshot.snapshot_id)
        if snapshot.snapshot_id in seen_snapshot_ids:
            rejected.append((snapshot.snapshot_id, "duplicate_odds_snapshot_id"))
            continue
        seen_snapshot_ids.add(snapshot.snapshot_id)
        observation_id = snapshot.source_observation_id
        if not observation_id:
            rejected.append((snapshot.snapshot_id, "odds_source_observation_id_missing"))
            continue
        observation = observation_by_id.get(observation_id)
        if observation is None:
            rejected.append((snapshot.snapshot_id, "odds_source_observation_missing"))
            continue
        scope = fixture_scopes.get(snapshot.fixture_id)
        if scope is None or (observation.competition_key, observation.season) != scope:
            rejected.append((snapshot.snapshot_id, "odds_source_observation_scope_mismatch"))
            continue
        if observation.provider != snapshot.source_id:
            rejected.append((snapshot.snapshot_id, "odds_source_provider_mismatch"))
            continue
        observed_fixture_id = observation.values.get("fixture_id")
        if observed_fixture_id is not None and observed_fixture_id != snapshot.fixture_id:
            rejected.append((snapshot.snapshot_id, "odds_source_fixture_id_mismatch"))
            continue
        if observation.available_at_utc > snapshot.captured_at:
            rejected.append((snapshot.snapshot_id, "odds_source_observation_after_capture"))
            continue
        if snapshot.provider_quote_at is None or not (
            snapshot.provider_quote_at < snapshot.kickoff_at
            and snapshot.provider_quote_at <= snapshot.captured_at
        ):
            rejected.append((snapshot.snapshot_id, "odds_provider_quote_timestamp_invalid"))
            continue
        decision = evaluate_observation(
            observation,
            data_type=observation.entity_type,
            cutoff=ForecastCutoff(snapshot.captured_at),
            approvals=approval_rows,
            max_age=timedelta.max,
            required_uses=("collection", "storage", "benchmarking", "commercial_use"),
        )
        if not decision.eligible:
            rejected.append((snapshot.snapshot_id, decision.reason))
        else:
            approved.add(snapshot.snapshot_id)

    failures = tuple(sorted(set(rejected)))
    return OddsSourceAudit(
        snapshot_count=len(audited_snapshot_ids),
        approved_snapshot_ids=tuple(sorted(approved)),
        rejected_snapshots=failures,
        passed=bool(audited_snapshot_ids) and not failures and len(approved) == len(audited_snapshot_ids),
    )


@dataclass(frozen=True, slots=True)
class PaperLedgerSourceAudit:
    selection_count: int
    settlement_count: int
    approved_observation_ids: tuple[str, ...]
    rejected_observations: tuple[tuple[str, str], ...]
    passed: bool


def audit_paper_ledger_sources(
    walk_forward: MultiCompetitionWalkForwardEvaluation,
    paper_ledger: PaperLedger,
    observations: Iterable[TrainingObservationEvidence],
    approvals: Iterable["SourceApproval"],
) -> PaperLedgerSourceAudit:
    """Verify forecast inputs, odds quotes and settled results in the paper ledger."""
    from datetime import timedelta
    from veltrix_v2.contracts import ForecastCutoff
    from veltrix_v2.quality.eligibility import SourceApproval, evaluate_observation

    if not isinstance(walk_forward, MultiCompetitionWalkForwardEvaluation):
        raise ValueError("CERTIFICATION_WALK_FORWARD_REPORT_REQUIRED")
    if not isinstance(paper_ledger, PaperLedger):
        raise ValueError("CERTIFICATION_PAPER_LEDGER_REQUIRED")
    observation_rows = tuple(observations)
    approval_rows = tuple(approvals)
    if any(not isinstance(row, TrainingObservationEvidence) for row in observation_rows):
        raise ValueError("CERTIFICATION_TRAINING_OBSERVATION_EVIDENCE_TYPE_INVALID")
    if any(not isinstance(row, SourceApproval) for row in approval_rows):
        raise ValueError("CERTIFICATION_SOURCE_APPROVAL_TYPE_INVALID")
    by_id = {row.observation_id: row.observation for row in observation_rows}
    if len(by_id) != len(observation_rows):
        raise ValueError("CERTIFICATION_DUPLICATE_SOURCE_OBSERVATION_ID")

    selection_by_id = {row.selection_id: row for row in paper_ledger.selections}
    approved: set[str] = set()
    rejected: list[tuple[str, str]] = []
    required_ids: set[str] = set()

    selection_scopes = {}
    for selection in paper_ledger.selections:
        forecast_scope_rows = set()
        for observation_id in selection.forecast_source_observation_ids:
            required_ids.add(observation_id)
            observation = by_id.get(observation_id)
            if observation is None:
                rejected.append((observation_id, "paper_forecast_source_observation_missing"))
                continue
            forecast_scope_rows.add((observation.competition_key, observation.season))
            observed_fixture_id = observation.values.get("fixture_id")
            if observed_fixture_id is not None and observed_fixture_id != selection.bet.fixture_id:
                rejected.append((observation_id, "paper_forecast_fixture_id_mismatch"))
                continue
            decision = evaluate_observation(
                observation,
                data_type=observation.entity_type,
                cutoff=ForecastCutoff(selection.forecast_generated_at_utc),
                approvals=approval_rows,
                max_age=timedelta.max,
                required_uses=("collection", "storage", "model_training", "public_display", "commercial_use"),
            )
            if not decision.eligible:
                rejected.append((observation_id, decision.reason))
            else:
                approved.add(observation_id)
        if len(forecast_scope_rows) != 1:
            rejected.append((selection.selection_id, "paper_forecast_source_scope_missing_or_conflicting"))
            scope = None
        else:
            scope = next(iter(forecast_scope_rows))
        selection_scopes[selection.selection_id] = scope

        odds = selection.odds_snapshot
        odds_observation_id = odds.source_observation_id
        if not odds_observation_id:
            rejected.append((selection.selection_id, "paper_odds_source_observation_id_missing"))
            continue
        required_ids.add(odds_observation_id)
        odds_observation = by_id.get(odds_observation_id)
        if odds_observation is None:
            rejected.append((odds_observation_id, "paper_odds_source_observation_missing"))
            continue
        observed_odds_fixture_id = odds_observation.values.get("fixture_id")
        if (
            scope is None
            or odds_observation.provider != odds.source_id
            or (odds_observation.competition_key, odds_observation.season) != scope
            or odds_observation.available_at_utc > odds.captured_at
            or (observed_odds_fixture_id is not None and observed_odds_fixture_id != selection.bet.fixture_id)
        ):
            rejected.append((odds_observation_id, "paper_odds_source_provenance_mismatch"))
            continue
        odds_decision = evaluate_observation(
            odds_observation,
            data_type=odds_observation.entity_type,
            cutoff=ForecastCutoff(odds.captured_at),
            approvals=approval_rows,
            max_age=timedelta.max,
            required_uses=("collection", "storage", "benchmarking", "commercial_use"),
        )
        if not odds_decision.eligible:
            rejected.append((odds_observation_id, odds_decision.reason))
        else:
            approved.add(odds_observation_id)

    if not paper_ledger.selections or not paper_ledger.settlements:
        rejected.append(("*", "paper_ledger_has_no_prospective_settled_evidence"))

    for event in paper_ledger.settlements:
        selection = selection_by_id[event.selection_id]
        scope = selection_scopes.get(selection.selection_id)
        observation_id = event.result_source_observation_id
        required_ids.add(observation_id)
        observation = by_id.get(observation_id)
        if observation is None:
            rejected.append((observation_id, "paper_result_source_observation_missing"))
            continue
        observed_result_fixture_id = observation.values.get("fixture_id")
        if (
            scope is None
            or (observation.competition_key, observation.season) != scope
            or (observed_result_fixture_id is not None and observed_result_fixture_id != selection.bet.fixture_id)
        ):
            rejected.append((observation_id, "paper_result_source_scope_or_fixture_mismatch"))
            continue
        if (
            observation.available_at_utc <= selection.odds_snapshot.kickoff_at
            or observation.available_at_utc > event.result_observed_at_utc
        ):
            rejected.append((observation_id, "paper_result_source_time_invalid"))
            continue
        decision = evaluate_observation(
            observation,
            data_type=observation.entity_type,
            cutoff=ForecastCutoff(event.result_observed_at_utc),
            approvals=approval_rows,
            max_age=timedelta.max,
            required_uses=("collection", "storage", "benchmarking", "commercial_use"),
        )
        if not decision.eligible:
            rejected.append((observation_id, decision.reason))
        else:
            approved.add(observation_id)

        date_observation_id = event.settlement.match_date_source_observation_id
        if date_observation_id:
            required_ids.add(date_observation_id)
            date_observation = by_id.get(date_observation_id)
            if date_observation is None:
                rejected.append((date_observation_id, "paper_match_date_source_observation_missing"))
            elif (
                scope is None
                or (date_observation.competition_key, date_observation.season) != scope
                or date_observation.available_at_utc > event.result_observed_at_utc
            ):
                rejected.append((date_observation_id, "paper_match_date_source_provenance_mismatch"))
            else:
                date_decision = evaluate_observation(
                    date_observation,
                    data_type=date_observation.entity_type,
                    cutoff=ForecastCutoff(event.result_observed_at_utc),
                    approvals=approval_rows,
                    max_age=timedelta.max,
                    required_uses=("collection", "storage", "benchmarking", "commercial_use"),
                )
                if not date_decision.eligible:
                    rejected.append((date_observation_id, date_decision.reason))
                else:
                    approved.add(date_observation_id)

    failures = tuple(sorted(set(rejected)))
    return PaperLedgerSourceAudit(
        selection_count=len(paper_ledger.selections),
        settlement_count=len(paper_ledger.settlements),
        approved_observation_ids=tuple(sorted(approved)),
        rejected_observations=failures,
        passed=bool(required_ids) and not failures and approved == required_ids,
    )


@dataclass(frozen=True, slots=True)
class ReleaseSourceAuditBundle:
    """Complete provenance audit retained with a value-bet certification."""

    training_sources: TrainingSourceAudit
    walk_forward_integrity: WalkForwardIntegrityAudit
    odds_sources: OddsSourceAudit
    paper_ledger_sources: PaperLedgerSourceAudit

    def __post_init__(self) -> None:
        if not isinstance(self.training_sources, TrainingSourceAudit):
            raise ValueError("CERTIFICATION_TRAINING_SOURCE_AUDIT_REQUIRED")
        if not isinstance(self.walk_forward_integrity, WalkForwardIntegrityAudit):
            raise ValueError("CERTIFICATION_WALK_FORWARD_INTEGRITY_AUDIT_REQUIRED")
        if not isinstance(self.odds_sources, OddsSourceAudit):
            raise ValueError("CERTIFICATION_ODDS_SOURCE_AUDIT_REQUIRED")
        if not isinstance(self.paper_ledger_sources, PaperLedgerSourceAudit):
            raise ValueError("CERTIFICATION_PAPER_LEDGER_SOURCE_AUDIT_REQUIRED")

    @property
    def source_approved(self) -> bool:
        return (
            self.training_sources.passed
            and self.odds_sources.passed
            and self.paper_ledger_sources.passed
        )

    @property
    def point_in_time_validated(self) -> bool:
        return self.walk_forward_integrity.passed and self.source_approved


@dataclass(frozen=True, slots=True)
class PredictionAuditBundle:
    """Actual provenance, leakage and held-out calibration reports retained."""

    source_audit: TrainingSourceAudit
    integrity_audit: WalkForwardIntegrityAudit
    calibration_1x2: "CalibrationReport1X2 | None"
    calibration_btts: "BinaryCalibrationReport | None"
    calibration_totals: "BinaryCalibrationReport | None"
    calibration_gates: tuple["CalibrationGateResult", ...]

    def __post_init__(self) -> None:
        from veltrix_v2.evaluation.binary_calibration import BinaryCalibrationReport
        from veltrix_v2.evaluation.calibration import CalibrationReport1X2
        from veltrix_v2.evaluation.calibration_gate import CalibrationGateResult
        if not isinstance(self.source_audit, TrainingSourceAudit):
            raise ValueError("PREDICTION_AUDIT_SOURCE_REPORT_REQUIRED")
        if not isinstance(self.integrity_audit, WalkForwardIntegrityAudit):
            raise ValueError("PREDICTION_AUDIT_INTEGRITY_REPORT_REQUIRED")
        if self.calibration_1x2 is not None and not isinstance(self.calibration_1x2, CalibrationReport1X2):
            raise ValueError("PREDICTION_AUDIT_1X2_CALIBRATION_REPORT_INVALID")
        if self.calibration_btts is not None and not isinstance(self.calibration_btts, BinaryCalibrationReport):
            raise ValueError("PREDICTION_AUDIT_BTTS_CALIBRATION_REPORT_INVALID")
        if self.calibration_totals is not None and not isinstance(self.calibration_totals, BinaryCalibrationReport):
            raise ValueError("PREDICTION_AUDIT_TOTALS_CALIBRATION_REPORT_INVALID")
        gates = tuple(self.calibration_gates)
        if any(not isinstance(row, CalibrationGateResult) for row in gates):
            raise ValueError("PREDICTION_AUDIT_CALIBRATION_GATE_RESULT_INVALID")
        object.__setattr__(self, "calibration_gates", gates)

    def calibration_passed(self, market: str) -> bool:
        if market == "1X2":
            rows = tuple(row for row in self.calibration_gates if row.market.startswith("1X2:"))
            return len(rows) == 3 and all(row.passed for row in rows)
        rows = tuple(row for row in self.calibration_gates if row.market == market)
        return len(rows) == 1 and rows[0].passed

    @property
    def source_approved(self) -> bool:
        return self.source_audit.passed

    @property
    def point_in_time_validated(self) -> bool:
        return self.integrity_audit.passed and self.source_audit.passed
