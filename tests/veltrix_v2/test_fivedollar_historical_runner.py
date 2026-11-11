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



def test_schedule_selector_can_evaluate_actual_three_month_provider_window():
    rows = synthetic_matches(competitions=5, days=90)
    first_start, window, splits, scheduled = RUNNER._choose_schedule(rows)
    assert first_start - min(row.kickoff_utc for row in rows) <= timedelta(days=75)
    assert window.days < 30
    assert splits >= 3
    assert scheduled > 0



def test_history_entitlement_is_read_from_supported_provider_plan():
    assert RUNNER._history_limit_for_plan("free") == 90
    assert RUNNER._history_limit_for_plan("community") == 365
    assert RUNNER._history_limit_for_plan("pro") == 365


def test_unknown_provider_plan_fails_closed():
    import pytest

    with pytest.raises(RuntimeError, match="ACCOUNT_PLAN_UNRECOGNIZED"):
        RUNNER._history_limit_for_plan("trial-unknown")


def test_free_plan_cannot_request_12_month_history(monkeypatch):
    from types import SimpleNamespace

    calls = []

    class FakeBudget:
        actual = 0
        remaining_header = 59

        def __init__(self, maximum, api_key):
            self.maximum = maximum
            self.api_key = api_key

        def get(self, endpoint, params):
            calls.append(endpoint)
            self.actual += 1
            return {"success": 1, "data": {"plan": "free"}} if endpoint == "status" else {}

    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "test-key")
    monkeypatch.setattr(RUNNER, "RequestBudget", FakeBudget)
    report = RUNNER.run(SimpleNamespace(
        days=365,
        max_requests=50,
        max_pages=5,
        min_history_days=300,
        min_training_rows=200,
        min_test_sample=1000,
        max_iterations=6000,
    ))
    assert report["status"] == "BLOCKED_PLAN_HISTORY_LIMIT"
    assert report["provider_plan"] == "free"
    assert report["plan_history_limit_days"] == 90
    assert calls == ["status"]


def test_community_country_pack_filter_supports_argentina_brazil_and_nigeria():
    assert RUNNER._is_target_league("Argentina Liga Profesional")
    assert RUNNER._is_target_league("Brazil Serie A")
    assert RUNNER._is_target_league("Nigeria Premier Football League")
    assert not RUNNER._is_target_league("Portugal Primeira Liga")
