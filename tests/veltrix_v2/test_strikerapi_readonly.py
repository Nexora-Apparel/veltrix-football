from scripts.veltrix_v2 import verify_strikerapi_readonly as verifier


def test_collect_pages_marks_truncation_at_four_page_bound():
    calls = []

    def fake_call(api_key, league, status, start, end, offset):
        calls.append(offset)
        return {
            "games": [{"game_id": f"g-{offset}"}],
            "count": 4,
            "next_offset": offset + verifier.LIMIT,
        }

    rows, pages, truncated, page_counts = verifier.collect_pages(
        "fake", "soccer", "final", "2026-01-01", "2026-02-01",
        call=fake_call,
    )
    assert len(rows) == verifier.MAX_PAGES_PER_CHECK
    assert pages == verifier.MAX_PAGES_PER_CHECK == 4
    assert truncated is True
    assert calls == [0, 50, 100, 150]
    assert page_counts == [4, 4, 4, 4]


def test_collect_pages_rejects_nonadvancing_pagination():
    def fake_call(api_key, league, status, start, end, offset):
        return {"games": [{"game_id": "g"}], "next_offset": offset}

    try:
        verifier.collect_pages(
            "fake", "soccer", "final", "2026-01-01", "2026-02-01",
            call=fake_call,
        )
    except verifier.ProbeError as exc:
        assert "did not advance" in str(exc)
    else:
        raise AssertionError("nonadvancing pagination must fail closed")


def test_main_hard_caps_all_primary_and_nwsl_diagnostic_calls_at_96_credits(
    monkeypatch, capsys
):
    monkeypatch.setenv("STRIKERAPI_API_KEY", "fake-secret")
    calls = []

    def fake_call(api_key, league, status, start, end, offset, **extra):
        calls.append((league, status, offset, extra))
        identity = "-".join(
            str(value)
            for value in (
                league, status, start, end,
                extra.get("season"), extra.get("stage"), offset,
            )
        )
        game = {
            "game_id": identity,
            "date": "2026-11-12",
            "starts_at": "2026-11-12T15:00:00Z",
            "status": status,
            "home": {"team_id": "home-" + identity, "name": "Home"},
            "away": {"team_id": "away-" + identity, "name": "Away"},
        }
        if status == "final":
            game["home"]["score"] = 2
            game["away"]["score"] = 1
        next_offset = (
            offset + verifier.LIMIT
            if offset < (verifier.MAX_PAGES_PER_CHECK - 1) * verifier.LIMIT
            else None
        )
        return {"games": [game], "count": 4, "next_offset": next_offset}

    monkeypatch.setattr(verifier, "call_api", fake_call)
    assert verifier.main() == 0
    output = capsys.readouterr().out
    assert len(calls) == verifier.MAX_CALLS == 48
    assert len(calls) * 2 == 96
    assert "maximum_credits=96" in output
    assert "API_CALLS_ATTEMPTED: 48" not in output
    assert "documented_credit_cost=96" in output
    assert "DATABASE_WRITES: 0" in output


def test_main_blocks_without_secret_before_any_request(monkeypatch, capsys):
    monkeypatch.delenv("STRIKERAPI_API_KEY", raising=False)
    assert verifier.main() == 2
    assert "BLOCKED_MISSING_SECRET" in capsys.readouterr().out
