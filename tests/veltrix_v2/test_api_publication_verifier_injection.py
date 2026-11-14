from __future__ import annotations

import pytest

from api import telegram as telegram_api


def test_api_has_no_implicit_publication_verifier(monkeypatch):
    monkeypatch.setattr(telegram_api.app.state, "_state", {}, raising=False)
    assert telegram_api._authoritative_publication_verifier() is None


def test_api_accepts_only_explicit_callable_publication_verifier(monkeypatch):
    monkeypatch.setattr(telegram_api.app.state, "_state", {}, raising=False)
    with pytest.raises(TypeError, match="AUTHORITATIVE_PUBLICATION_VERIFIER_REQUIRED"):
        telegram_api.configure_publication_verifier(None)

    verifier = lambda report, identity: False
    telegram_api.configure_publication_verifier(verifier)
    assert telegram_api._authoritative_publication_verifier() is verifier



def test_dashboard_api_hides_v2_predictions_without_trusted_verifier(monkeypatch):
    monkeypatch.setattr(telegram_api, "_authoritative_publication_verifier", lambda: None)
    monkeypatch.setattr(telegram_api, "load_dashboard_snapshot", lambda verifier=None: None)
    monkeypatch.setattr(telegram_api, "load_latest_report", lambda verifier=None: None)
    result = telegram_api.dashboard_data()
    assert result["status"] == "UNAVAILABLE"
    assert result["predictions"] == []
