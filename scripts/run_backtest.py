"""Disabled legacy backtest CLI."""
from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "LEGACY_BACKTEST_DISABLED: use the independent walk-forward evaluation and certification pipeline."
    )


if __name__ == "__main__":
    main()
