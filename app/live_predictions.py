"""Quarantined legacy prediction module.

The former heuristic/Poisson/Elo prediction pipeline has been removed from the
runtime. Shared fixture/history identity utilities now live in
app.fixture_history_utils. Use the independent model portfolio for inference.
"""
from __future__ import annotations


class LegacyPredictionDisabled(RuntimeError):
    pass


def predict_fixtures(*args, **kwargs):
    raise LegacyPredictionDisabled(
        "Legacy prediction logic is disabled; use the independent inference service."
    )


def build_daily_report(*args, **kwargs):
    raise LegacyPredictionDisabled(
        "Legacy daily report generation is disabled; use the independently certified publication pipeline."
    )
