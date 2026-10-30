"""Certificate CLI adapter for timestamp-safe screens and frozen calibrator metadata."""
from __future__ import annotations

from copy import deepcopy

from app import goal_market_calibration as calibration_core
from app import value_bets as value_core
from app.value_bets_runtime import attach_value_bet_screens, screen_fixture_value_bets

# Keep both report-generation paths on the timestamp-safe market adapter.
value_core.screen_fixture_value_bets = screen_fixture_value_bets
value_core.attach_value_bet_screens = attach_value_bet_screens

# The actual backtest artifact stores calibration_matches/test_matches at the
# chronological experiment level. The core function expects these counts on
# each market record, so normalize the artifact shape without changing evidence.
_original_apply_calibration = calibration_core.apply_goal_market_calibration


def _apply_calibration_from_artifact(report, backtest):
    payload = deepcopy(backtest)
    live = payload.get("live_pipeline") or {}
    goal = live.get("goal_markets") or {}
    experiment = goal.get("chronological_calibration_experiment") or {}
    market_items = experiment.get("markets") or {}
    if isinstance(market_items, dict):
        for item in market_items.values():
            if isinstance(item, dict):
                item.setdefault("calibration_matches", experiment.get("calibration_matches"))
                item.setdefault("test_matches", experiment.get("test_matches"))
    return _original_apply_calibration(report, payload)


calibration_core.apply_goal_market_calibration = _apply_calibration_from_artifact

from scripts.build_value_certificate import main


if __name__ == "__main__":
    raise SystemExit(main())
