import pytest


@pytest.fixture(autouse=True)
def isolate_runtime_adapter_import_side_effects(request):
    if request.node.name != "test_runtime_adapter_reads_sample_counts_from_real_backtest_shape":
        yield
        return

    from app import goal_market_calibration, value_bets

    original_apply = goal_market_calibration.apply_goal_market_calibration
    original_screen = value_bets.screen_fixture_value_bets
    original_attach = value_bets.attach_value_bet_screens
    try:
        yield
    finally:
        goal_market_calibration.apply_goal_market_calibration = original_apply
        value_bets.screen_fixture_value_bets = original_screen
        value_bets.attach_value_bet_screens = original_attach
