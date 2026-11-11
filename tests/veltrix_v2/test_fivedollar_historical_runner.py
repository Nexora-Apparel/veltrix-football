from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from veltrix_v2.models.poisson_strength import TrainingMatch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "veltrix_v2" / "run_fivedollar_historical_walk_forward.py"
SPEC = spec_from_file_location("veltrix_fivedollar_historical_runner", SCRIPT)
RUNNER = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)

UTC = timezone.utc


def synthetic_matches(competitions=5, days=350):
    start = datetime(2025, 11, 1, 12, 0, tzinfo=UTC)
    rows = []
    for comp in range(competitions):
        for index in range(days):
            kickoff = start + timedelta(days=index)
            rows.append(TrainingMatch(
                fixture_id=f"comp-{comp}-fixture-{index}",
                competition_key=f"5dollar:{comp}",
                season="rolling-365d",
                kickoff_utc=kickoff,
                available_at_utc=kickoff + timedelta(days=4),
                home_team_id=f"5dollar:{comp}:home-{index % 20}",
                away_team_id=f"5dollar:{comp}:away-{(index + 1) % 20}",
                home_goals=index % 4,
                away_goals=(index + 1) % 3,
                source_observation_id=f"obs-{comp}-{index}",
                availability_basis="provider_finished_status_conservative_4d",
            ))
    return rows


def test_schedule_selector_finds_1000_plus_test_universe():
    rows = synthetic_matches()
    first_start, window, splits, scheduled = RUNNER._choose_schedule(rows)
    assert window.days >= 30
    assert splits >= 3
    assert scheduled >= 1000
    assert first_start > min(row.kickoff_utc for row in rows)


def test_schedule_selector_rejects_insufficient_training_history():
    rows = synthetic_matches(competitions=1, days=45)
    import pytest
    with pytest.raises(RuntimeError, match="NO_VALID_CHRONOLOGICAL_FOLD_SCHEDULE"):
        RUNNER._choose_schedule(rows)
