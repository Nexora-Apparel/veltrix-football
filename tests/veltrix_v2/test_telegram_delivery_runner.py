from __future__ import annotations

import pytest

from scripts.veltrix_v2.dispatch_public_telegram_bundle import run_dispatch


def _environment(tmp_path, **overrides):
    bundle = tmp_path / "command-data" / "public-data" / "v2_report_bundle.json"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(b"portable bundle")
    env = {
        "VELTRIX_V2_TELEGRAM_DELIVERY_ENABLED": "true",
        "VELTRIX_V2_REPORT_BUNDLE_PATH": str(bundle.relative_to(tmp_path)),
        "VELTRIX_V2_TELEGRAM_DATABASE_URL": "postgresql://unused",
        "VELTRIX_V2_TELEGRAM_EXPECTED_DATABASE": "veltrix_football",
        "VELTRIX_V2_TELEGRAM_EXPECTED_CHAT_ID": "-100123",
        "TELEGRAM_CHAT_ID": "-100123",
    }
    env.update(overrides)
    return env


def test_telegram_delivery_runner_is_locked_by_default():
    with pytest.raises(RuntimeError, match="V2_TELEGRAM_DELIVERY_LOCKED"):
        run_dispatch(environ={})


def test_telegram_delivery_runner_requires_trusted_verifier_factory(tmp_path, monkeypatch):
    env = _environment(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="AUTHORITATIVE_PUBLICATION_VERIFIER_FACTORY_REQUIRED"):
        run_dispatch(environ=env)


def test_telegram_delivery_runner_refuses_staging_database_before_any_send(tmp_path, monkeypatch):
    env = _environment(
        tmp_path,
        VELTRIX_V2_TELEGRAM_EXPECTED_DATABASE="veltrix_football_staging",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="STAGING_DATABASE_CANNOT_RECEIVE_PUBLIC_TELEGRAM_REPORTS"):
        run_dispatch(environ=env, verifier_factory=lambda: (lambda report, identity: True))


def test_telegram_delivery_runner_refuses_wrong_destination_before_any_send(tmp_path, monkeypatch):
    env = _environment(tmp_path, TELEGRAM_CHAT_ID="-100999")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="TELEGRAM_DESTINATION_IDENTITY_MISMATCH"):
        run_dispatch(environ=env, verifier_factory=lambda: (lambda report, identity: True))
