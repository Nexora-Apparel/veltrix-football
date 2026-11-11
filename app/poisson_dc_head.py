"""Quarantined legacy model module. Use app.independent_market_models instead."""
from __future__ import annotations


class LegacyModelDisabled(RuntimeError):
    pass


def _disabled(*args, **kwargs):
    raise LegacyModelDisabled(
        "Legacy model code is disabled; use the independent VELTRIX model portfolio."
    )

_poisson_pmf = _disabled
dixon_coles_markets = _disabled
