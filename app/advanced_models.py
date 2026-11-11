"""Quarantined legacy model module. Use app.independent_market_models instead."""
from __future__ import annotations


class LegacyModelDisabled(RuntimeError):
    pass


def _disabled(*args, **kwargs):
    raise LegacyModelDisabled(
        "Legacy model code is disabled; use the independent VELTRIX model portfolio."
    )

recency_weighted_mean = _disabled
dixon_coles_1x2 = _disabled
rest_congestion_context = _disabled
blend_1x2 = _disabled
