"""Run certificate generation with the timestamp-safe market screen installed."""
from __future__ import annotations

from app import value_bets as core
from app.value_bets_runtime import screen_fixture_value_bets

# The legacy attach helper resolves this module-level function at call time.
# Replace it before importing the certificate CLI so both report-generation
# paths use the same timestamp-safe implementation.
core.screen_fixture_value_bets = screen_fixture_value_bets

from scripts.build_value_certificate import main


if __name__ == "__main__":
    raise SystemExit(main())
