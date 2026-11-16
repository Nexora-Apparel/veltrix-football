"""Fail-closed V2 Telegram bundle dispatcher.

This runner is deliberately inert unless an operator explicitly enables it and
supplies a trusted publication-verifier factory, an immutable portable bundle,
a production database identity, and Telegram credentials. It never retries an
uncertain send; delivery claims are reconciled separately.
"""
from __future__ import annotations

import importlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from veltrix_v2.reporting.artifact_bundle import (
    PORTABLE_BUNDLE_MAX_BYTES,
    load_authorized_portable_report_surface_bundle,
)
from veltrix_v2.reporting.postgres_delivery_store import PostgresTelegramDeliveryStore
from veltrix_v2.reporting.report_identity import verify_report_identity
from veltrix_v2.reporting.telegram import dispatch_public_telegram_portable_bundle


def _load_verifier_factory(spec: str) -> Callable[[], Callable]:
    if not isinstance(spec, str) or ":" not in spec:
        raise RuntimeError("AUTHORITATIVE_PUBLICATION_VERIFIER_FACTORY_REQUIRED")
    module_name, attribute = spec.split(":", 1)
    if not module_name.startswith("veltrix_v2.") or not attribute.isidentifier():
        raise RuntimeError("PUBLICATION_VERIFIER_FACTORY_NOT_ALLOWLISTED")
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute, None)
    if not callable(factory):
        raise RuntimeError("PUBLICATION_VERIFIER_FACTORY_NOT_CALLABLE")
    return factory


def _telegram_sender(token: str) -> Callable[[str, str], str]:
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("TELEGRAM_BOT_TOKEN_REQUIRED")

    def send_message(destination: str, message: str) -> str:
        payload = json.dumps(
            {"chat_id": destination, "text": message, "disable_web_page_preview": True},
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            status = int(getattr(response, "status", 200))
            body = response.read(1_000_001)
        if status != 200 or len(body) > 1_000_000:
            raise RuntimeError("TELEGRAM_HTTP_SEND_FAILED")
        result = json.loads(body.decode("utf-8"))
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("TELEGRAM_SEND_NOT_CONFIRMED")
        message_id = result.get("result", {}).get("message_id")
        if not isinstance(message_id, (str, int)) or not str(message_id).strip():
            raise RuntimeError("TELEGRAM_MESSAGE_ID_MISSING")
        return str(message_id)

    return send_message


def run_dispatch(
    environ: Mapping[str, str] | None = None,
    *,
    connect_factory: Callable | None = None,
    verifier_factory: Callable[[], Callable] | None = None,
    send_message: Callable[[str, str], str] | None = None,
):
    env = os.environ if environ is None else environ
    if env.get("VELTRIX_V2_TELEGRAM_DELIVERY_ENABLED", "").lower() != "true":
        raise RuntimeError("V2_TELEGRAM_DELIVERY_LOCKED")

    bundle_path_value = env.get("VELTRIX_V2_REPORT_BUNDLE_PATH", "")
    database_url = env.get("VELTRIX_V2_TELEGRAM_DATABASE_URL", "")
    expected_database = env.get("VELTRIX_V2_TELEGRAM_EXPECTED_DATABASE", "")
    destination = env.get("TELEGRAM_CHAT_ID", "")
    expected_destination = env.get("VELTRIX_V2_TELEGRAM_EXPECTED_CHAT_ID", "")
    if not all((bundle_path_value, database_url, expected_database, destination, expected_destination)):
        raise RuntimeError("V2_TELEGRAM_DELIVERY_CONFIGURATION_INCOMPLETE")
    if expected_database.endswith("_staging"):
        raise RuntimeError("STAGING_DATABASE_CANNOT_RECEIVE_PUBLIC_TELEGRAM_REPORTS")
    if destination != expected_destination:
        raise RuntimeError("TELEGRAM_DESTINATION_IDENTITY_MISMATCH")

    bundle_path = Path(bundle_path_value)
    # Website and Telegram must read the exact same immutable publication bytes.
    # Do not accept per-surface or versioned copies in the delivery runner.
    if bundle_path != Path("command-data/public-data/v2_report_bundle.json"):
        raise RuntimeError("PORTABLE_REPORT_BUNDLE_PATH_NOT_ALLOWLISTED")
    raw_bundle = bundle_path.read_bytes()
    if not raw_bundle or len(raw_bundle) > PORTABLE_BUNDLE_MAX_BYTES:
        raise ValueError("PORTABLE_REPORT_BUNDLE_SIZE_INVALID")

    if verifier_factory is None:
        spec = env.get("VELTRIX_V2_PUBLICATION_VERIFIER_FACTORY", "")
        verifier_factory = _load_verifier_factory(spec)
    verifier = verifier_factory()
    if not callable(verifier):
        raise RuntimeError("AUTHORITATIVE_PUBLICATION_VERIFIER_REQUIRED")

    bundle = load_authorized_portable_report_surface_bundle(raw_bundle, verifier)
    identity = verify_report_identity(bundle.canonical_report)
    today_wat = datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
    if identity.as_of_date != today_wat:
        raise RuntimeError("TELEGRAM_REPORT_NOT_CURRENT_WAT_DATE")

    if connect_factory is None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PSYCOPG_REQUIRED_FOR_DURABLE_TELEGRAM_DELIVERY") from exc
        connect_factory = lambda: psycopg.connect(database_url)

    with connect_factory() as connection:
        actual_database = connection.execute("SELECT current_database()").fetchone()[0]
    if actual_database != expected_database:
        raise RuntimeError("TELEGRAM_DATABASE_IDENTITY_MISMATCH")

    if send_message is None:
        send_message = _telegram_sender(env.get("TELEGRAM_BOT_TOKEN", ""))

    store = PostgresTelegramDeliveryStore(connect_factory)
    return dispatch_public_telegram_portable_bundle(
        raw_bundle,
        destination,
        verifier,
        store,
        send_message,
    )


def main() -> int:
    attempt = run_dispatch()
    print(
        json.dumps(
            {
                "state": getattr(attempt, "state", "UNKNOWN"),
                "idempotency_key": getattr(attempt, "idempotency_key", None),
                "message_count": (
                    len(attempt.receipt.message_ids)
                    if getattr(attempt, "receipt", None) is not None
                    else 0
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
