"""Disabled legacy prediction runner.

The former daily runner depended on app.live_predictions and legacy model heads.
VELTRIX FOOTBALL 2.0 uses the independent model portfolio and its release gate.
"""
from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "LEGACY_PREDICTION_PIPELINE_DISABLED: the old daily runner has been removed. "
        "No fixtures are fetched, no predictions are calculated, and no report is published."
    )


if __name__ == "__main__":
    main()
