"""Independent VELTRIX FOOTBALL 2.0 model implementations."""

from .poisson import (
    InsufficientHistoryError,
    MatchObservation,
    PoissonPrediction,
    predict_match,
    observation_eligible_as_of,
)

__all__ = [
    "InsufficientHistoryError",
    "MatchObservation",
    "PoissonPrediction",
    "predict_match",
    "observation_eligible_as_of",
]

from .engine import (
    BatchForecastReport,
    ForecastRecord,
    PredictionTarget,
    predict_batch,
)

__all__ += [
    "BatchForecastReport", "ForecastRecord", "PredictionTarget", "predict_batch",
]
