"""Quarantined legacy backtest engine; use the independent walk-forward portfolio."""
from __future__ import annotations


class LegacyBacktestDisabled(RuntimeError):
    pass


def chronological_backtest(*args, **kwargs):
    raise LegacyBacktestDisabled(
        "Legacy backtesting is disabled; use the independent multi-origin walk-forward evaluator."
    )


def write_report(*args, **kwargs):
    raise LegacyBacktestDisabled("Legacy backtest report writing is disabled.")
