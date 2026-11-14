"""Compatibility entrypoint for the no-credit Odds API account probe.

Budget activation is deliberately separate: this command never invents a
provider billing period, monthly allowance, or operational hard cap.
"""
from scripts.phase4_odds_account_probe import main


if __name__ == "__main__":
    raise SystemExit(main())
