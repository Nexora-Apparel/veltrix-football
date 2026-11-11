"""Append-only prospective paper-selection ledger contracts.

This module is an in-memory domain contract. It performs no network or database
writes. A persistence adapter must append these immutable selection and
settlement events without rewriting prior records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from veltrix_v2.contracts.odds import OddsSnapshot
from veltrix_v2.evaluation.settlement import (
    MarketBet,
    MatchResult,
    Settlement,
    settle_market_bet,
)

REQUIRED_PROSPECTIVE_SETTLED = 300
REQUIRED_PROSPECTIVE_DATES = 90


def _aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"PAPER_LEDGER_{field.upper()}_MUST_BE_AWARE")
    return value.astimezone(timezone.utc)


def _decimal(value: Decimal | str | int | float, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"PAPER_LEDGER_{field.upper()}_MUST_BE_FINITE_DECIMAL") from exc
    if not result.is_finite():
        raise ValueError(f"PAPER_LEDGER_{field.upper()}_MUST_BE_FINITE_DECIMAL")
    return result


def _canonical_market(value: str) -> str:
    return "TOTALS" if value.upper() in {"TOTALS", "OVER_UNDER"} else value.upper()


@dataclass(frozen=True, slots=True)
class PaperSelection:
    """One prospective value candidate recorded before its fixture kicks off."""

    selection_id: str
    bet: MarketBet
    odds_snapshot: OddsSnapshot
    model_probability: Decimal
    model_version: str
    forecast_generated_at_utc: datetime
    selected_at_utc: datetime
    forecast_source_observation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.selection_id, str) or not self.selection_id.strip():
            raise ValueError("PAPER_LEDGER_SELECTION_ID_REQUIRED")
        if not isinstance(self.bet, MarketBet):
            raise ValueError("PAPER_LEDGER_MARKET_BET_REQUIRED")
        if not isinstance(self.odds_snapshot, OddsSnapshot):
            raise ValueError("PAPER_LEDGER_ODDS_SNAPSHOT_REQUIRED")
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ValueError("PAPER_LEDGER_MODEL_VERSION_REQUIRED")
        if not isinstance(self.forecast_source_observation_ids, (tuple, list)):
            raise ValueError("PAPER_LEDGER_FORECAST_PROVENANCE_REQUIRED")
        source_ids = tuple(self.forecast_source_observation_ids)
        if not source_ids or any(not isinstance(item, str) or not item.strip() for item in source_ids):
            raise ValueError("PAPER_LEDGER_FORECAST_PROVENANCE_REQUIRED")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("PAPER_LEDGER_DUPLICATE_FORECAST_PROVENANCE")
        probability = _decimal(self.model_probability, "model_probability")
        if not Decimal("0") < probability < Decimal("1"):
            raise ValueError("PAPER_LEDGER_MODEL_PROBABILITY_OUT_OF_RANGE")
        forecast_at = _aware_utc(self.forecast_generated_at_utc, "forecast_generated_at_utc")
        selected_at = _aware_utc(self.selected_at_utc, "selected_at_utc")
        quote = self.odds_snapshot
        if self.bet.fixture_id != quote.fixture_id:
            raise ValueError("PAPER_LEDGER_FIXTURE_ID_MISMATCH")
        if _canonical_market(self.bet.market) != _canonical_market(quote.market):
            raise ValueError("PAPER_LEDGER_MARKET_MISMATCH")
        if self.bet.selection.upper() != quote.selection.upper():
            raise ValueError("PAPER_LEDGER_SELECTION_MISMATCH")
        if self.bet.line != quote.line:
            raise ValueError("PAPER_LEDGER_LINE_MISMATCH")
        if self.bet.decimal_odds != quote.decimal_odds:
            raise ValueError("PAPER_LEDGER_ODDS_PRICE_MISMATCH")
        if self.bet.period not in {"REGULATION", "INCLUDING_EXTRA_TIME"}:
            raise ValueError("PAPER_LEDGER_SETTLEMENT_PERIOD_INVALID")
        if forecast_at > selected_at:
            raise ValueError("PAPER_LEDGER_FORECAST_AFTER_SELECTION")
        if quote.captured_at > selected_at:
            raise ValueError("PAPER_LEDGER_ODDS_CAPTURE_AFTER_SELECTION")
        if selected_at >= quote.kickoff_at:
            raise ValueError("PAPER_LEDGER_SELECTION_NOT_PROSPECTIVE")
        if forecast_at >= quote.kickoff_at:
            raise ValueError("PAPER_LEDGER_FORECAST_NOT_PREMATCH")
        if quote.captured_at >= quote.kickoff_at:
            raise ValueError("PAPER_LEDGER_ODDS_NOT_PREMATCH")
        if probability * self.bet.decimal_odds <= Decimal("1"):
            raise ValueError("PAPER_LEDGER_CANDIDATE_HAS_NO_POSITIVE_EXPECTED_VALUE")
        object.__setattr__(self, "model_probability", probability)
        object.__setattr__(self, "forecast_generated_at_utc", forecast_at)
        object.__setattr__(self, "selected_at_utc", selected_at)
        object.__setattr__(self, "forecast_source_observation_ids", source_ids)

    @property
    def market(self) -> str:
        return _canonical_market(self.bet.market)

    @property
    def identity_key(self) -> tuple[str, str, str, Decimal | None, str]:
        return (
            self.bet.fixture_id,
            self.market,
            self.bet.selection,
            self.bet.line,
            self.bet.period,
        )

    @property
    def expected_value_per_unit(self) -> Decimal:
        return self.model_probability * self.bet.decimal_odds - Decimal("1")


@dataclass(frozen=True, slots=True)
class PaperSettlementEvent:
    """Immutable result event attached to one previously recorded selection."""

    event_id: str
    selection_id: str
    settlement: Settlement
    result_observed_at_utc: datetime
    result_source_observation_id: str
    settled_at_utc: datetime

    def __post_init__(self) -> None:
        for field in ("event_id", "selection_id", "result_source_observation_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"PAPER_LEDGER_{field.upper()}_REQUIRED")
        if not isinstance(self.settlement, Settlement):
            raise ValueError("PAPER_LEDGER_SETTLEMENT_REQUIRED")
        observed = _aware_utc(self.result_observed_at_utc, "result_observed_at_utc")
        settled = _aware_utc(self.settled_at_utc, "settled_at_utc")
        if observed > settled:
            raise ValueError("PAPER_LEDGER_SETTLEMENT_PRECEDES_RESULT_OBSERVATION")
        object.__setattr__(self, "result_observed_at_utc", observed)
        object.__setattr__(self, "settled_at_utc", settled)


@dataclass(frozen=True, slots=True)
class PaperLedgerEntry:
    selection: PaperSelection
    settlement_event: PaperSettlementEvent | None


@dataclass(frozen=True, slots=True)
class ProspectiveMarketCounts:
    market: str
    selected_count: int
    settled_count: int
    voided_count: int
    pending_count: int
    distinct_settled_dates: int
    sample_gate_passed: bool


@dataclass(frozen=True, slots=True)
class PaperLedger:
    """Immutable append-only event projection for prospective paper selections."""

    selections: tuple[PaperSelection, ...] = ()
    settlements: tuple[PaperSettlementEvent, ...] = ()

    def __post_init__(self) -> None:
        selections = tuple(self.selections)
        settlements = tuple(self.settlements)
        if any(not isinstance(row, PaperSelection) for row in selections):
            raise ValueError("PAPER_LEDGER_SELECTION_EVENT_TYPE_INVALID")
        if any(not isinstance(row, PaperSettlementEvent) for row in settlements):
            raise ValueError("PAPER_LEDGER_SETTLEMENT_EVENT_TYPE_INVALID")
        selection_ids = [row.selection_id for row in selections]
        if len(selection_ids) != len(set(selection_ids)):
            raise ValueError("PAPER_LEDGER_DUPLICATE_SELECTION_ID")
        identities = [row.identity_key for row in selections]
        if len(identities) != len(set(identities)):
            raise ValueError("PAPER_LEDGER_DUPLICATE_FIXTURE_MARKET_SELECTION")
        event_ids = [row.event_id for row in settlements]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("PAPER_LEDGER_DUPLICATE_SETTLEMENT_EVENT_ID")
        settlement_selection_ids = [row.selection_id for row in settlements]
        if len(settlement_selection_ids) != len(set(settlement_selection_ids)):
            raise ValueError("PAPER_LEDGER_DUPLICATE_SETTLEMENT_FOR_SELECTION")
        selection_by_id = {row.selection_id: row for row in selections}
        for event in settlements:
            selection = selection_by_id.get(event.selection_id)
            if selection is None:
                raise ValueError("PAPER_LEDGER_SETTLEMENT_WITHOUT_SELECTION")
            result = event.settlement
            if result.fixture_id != selection.bet.fixture_id:
                raise ValueError("PAPER_LEDGER_SETTLEMENT_FIXTURE_MISMATCH")
            if _canonical_market(result.market) != selection.market:
                raise ValueError("PAPER_LEDGER_SETTLEMENT_MARKET_MISMATCH")
            if result.selection.upper() != selection.bet.selection:
                raise ValueError("PAPER_LEDGER_SETTLEMENT_SELECTION_MISMATCH")
            if result.period != selection.bet.period:
                raise ValueError("PAPER_LEDGER_SETTLEMENT_PERIOD_MISMATCH")
            if result.stake != selection.bet.stake or result.decimal_odds != selection.bet.decimal_odds:
                raise ValueError("PAPER_LEDGER_SETTLEMENT_PRICE_OR_STAKE_MISMATCH")
            if event.settled_at_utc < selection.selected_at_utc:
                raise ValueError("PAPER_LEDGER_SETTLEMENT_PRECEDES_SELECTION")
            if result.status != "VOID" and event.result_observed_at_utc < selection.odds_snapshot.kickoff_at:
                raise ValueError("PAPER_LEDGER_COMPLETED_RESULT_OBSERVED_BEFORE_KICKOFF")
        object.__setattr__(self, "selections", selections)
        object.__setattr__(self, "settlements", settlements)

    def record_selection(self, selection: PaperSelection) -> "PaperLedger":
        if not isinstance(selection, PaperSelection):
            raise ValueError("PAPER_LEDGER_SELECTION_EVENT_TYPE_INVALID")
        return PaperLedger(self.selections + (selection,), self.settlements)

    def settle_selection(
        self,
        selection_id: str,
        result: MatchResult,
        *,
        event_id: str,
        result_observed_at_utc: datetime,
        result_source_observation_id: str,
        settled_at_utc: datetime,
    ) -> "PaperLedger":
        selection = next((row for row in self.selections if row.selection_id == selection_id), None)
        if selection is None:
            raise ValueError("PAPER_LEDGER_SELECTION_NOT_FOUND")
        if any(row.selection_id == selection_id for row in self.settlements):
            raise ValueError("PAPER_LEDGER_SELECTION_ALREADY_SETTLED")
        settlement = settle_market_bet(selection.bet, result)
        event = PaperSettlementEvent(
            event_id=event_id,
            selection_id=selection_id,
            settlement=settlement,
            result_observed_at_utc=result_observed_at_utc,
            result_source_observation_id=result_source_observation_id,
            settled_at_utc=settled_at_utc,
        )
        return PaperLedger(self.selections, self.settlements + (event,))

    @property
    def entries(self) -> tuple[PaperLedgerEntry, ...]:
        settlement_by_selection = {row.selection_id: row for row in self.settlements}
        return tuple(
            PaperLedgerEntry(row, settlement_by_selection.get(row.selection_id))
            for row in self.selections
        )

    def counts_for_market(self, market: str) -> ProspectiveMarketCounts:
        canonical = _canonical_market(market)
        selected = [row for row in self.selections if row.market == canonical]
        selection_ids = {row.selection_id for row in selected}
        events = [row for row in self.settlements if row.selection_id in selection_ids]
        valid = [row for row in events if row.settlement.status != "VOID"]
        dates = {
            row.settlement.match_date
            for row in valid
            if row.settlement.match_date is not None
        }
        settled_count = len(valid)
        distinct_dates = len(dates)
        return ProspectiveMarketCounts(
            market=canonical,
            selected_count=len(selected),
            settled_count=settled_count,
            voided_count=len(events) - settled_count,
            pending_count=len(selected) - len(events),
            distinct_settled_dates=distinct_dates,
            sample_gate_passed=(
                settled_count >= REQUIRED_PROSPECTIVE_SETTLED
                and distinct_dates >= REQUIRED_PROSPECTIVE_DATES
            ),
        )
