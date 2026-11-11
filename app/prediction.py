"""Quarantined legacy model module. Use app.independent_market_models instead."""
from __future__ import annotations


class LegacyModelDisabled(RuntimeError):
    pass


def _disabled(*args, **kwargs):
    raise LegacyModelDisabled(
        "Legacy model code is disabled; use the independent VELTRIX model portfolio."
    )

_validate_lambda = _disabled
_validate_max_goals = _disabled
poisson_pmf = _disabled
match_probabilities = _disabled
evaluate_decimal_odds = _disabled
