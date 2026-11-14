from __future__ import annotations

import json

import pytest

from veltrix_v2.reporting.artifact_bundle import (
    build_report_surface_bundle,
    persist_report_surface_bundle,
)
from veltrix_v2.reporting.delivery import (
    DeliveryOutcomeUnknown,
    DeliveryReceipt,
    DeliveryState,
    deliver_once,
)
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity, create_report_identity
from veltrix_v2.reporting.telegram import (
    dispatch_public_telegram_bundle,
    dispatch_public_telegram_report,
)


class MemoryStore:
    def __init__(self):
        self.claimed = set()
        self.sent = {}
        self.unknown = {}

    def claim(self, key, report_id, report_sha256, destination):
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    def mark_sent(self, key, receipt):
        self.sent[key] = receipt

    def mark_unknown(self, key, reason_code):
        self.unknown[key] = reason_code


def identity():
    from veltrix_v2.reporting.report_identity import REPORT_SCHEMA
    return create_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "delivery-test-1",
        "as_of_date": "2026-11-14",
        "predictions": [],
    })


def test_first_delivery_claims_sends_and_persists_receipt():
    store = MemoryStore()
    calls = []
    result = deliver_once(
        identity(), "telegram:chat-1", store,
        lambda: (calls.append("sent") or DeliveryReceipt("telegram:chat-1", ("msg-1",))),
    )
    assert result.state is DeliveryState.SENT
    assert calls == ["sent"]
    assert store.sent[result.idempotency_key].message_ids == ("msg-1",)


def test_duplicate_run_is_skipped_without_second_send():
    store = MemoryStore()
    calls = []
    report = identity()
    send = lambda: (calls.append("sent") or DeliveryReceipt("telegram:chat-1", ("msg-1",)))
    first = deliver_once(report, "telegram:chat-1", store, send)
    second = deliver_once(report, "telegram:chat-1", store, send)
    assert first.state is DeliveryState.SENT
    assert second.state is DeliveryState.DUPLICATE_SKIPPED
    assert calls == ["sent"]


def test_uncertain_transport_failure_is_marked_and_never_retried():
    store = MemoryStore()
    calls = []

    def uncertain_send():
        calls.append("attempt")
        raise TimeoutError("network timed out after request dispatch")

    with pytest.raises(DeliveryOutcomeUnknown):
        deliver_once(identity(), "telegram:chat-1", store, uncertain_send)
    second = deliver_once(
        identity(), "telegram:chat-1", store,
        lambda: (calls.append("retry") or DeliveryReceipt("telegram:chat-1", ("msg-2",))),
    )
    assert second.state is DeliveryState.DUPLICATE_SKIPPED
    assert calls == ["attempt"]


def test_receipt_destination_mismatch_becomes_uncertain_and_is_not_retried():
    store = MemoryStore()
    with pytest.raises(DeliveryOutcomeUnknown, match="uncertain"):
        deliver_once(
            identity(), "telegram:chat-1", store,
            lambda: DeliveryReceipt("telegram:chat-2", ("msg-1",)),
        )
    assert len(store.unknown) == 1


def test_receipt_persistence_failure_blocks_automatic_retry():
    class BrokenStore(MemoryStore):
        def mark_sent(self, key, receipt):
            raise OSError("database unavailable")

    store = BrokenStore()
    with pytest.raises(DeliveryOutcomeUnknown, match="persistence failed"):
        deliver_once(
            identity(), "telegram:chat-1", store,
            lambda: DeliveryReceipt("telegram:chat-1", ("msg-1",)),
        )
    second = deliver_once(
        identity(), "telegram:chat-1", store,
        lambda: pytest.fail("automatic retry must not run"),
    )
    assert second.state is DeliveryState.DUPLICATE_SKIPPED


def test_same_report_to_different_destinations_has_separate_idempotency_keys():
    store = MemoryStore()
    first = deliver_once(
        identity(), "telegram:chat-1", store,
        lambda: DeliveryReceipt("telegram:chat-1", ("msg-1",)),
    )
    second = deliver_once(
        identity(), "telegram:chat-2", store,
        lambda: DeliveryReceipt("telegram:chat-2", ("msg-2",)),
    )
    assert first.idempotency_key != second.idempotency_key
    assert first.state is DeliveryState.SENT
    assert second.state is DeliveryState.SENT


def public_report():
    return bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "telegram-e2e-2026-11-14",
        "as_of_date": "2026-11-14",
        "release_mode": "RESTRICTED_PUBLIC",
        "predictions": [{
            "publication_status": "PUBLISHED",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "competition_name": "Example League",
            "kickoff_wat": "17:30 WAT",
            "certified_markets": ["1X2"],
            "markets": {"1X2": {"home": 0.5, "draw": 0.25, "away": 0.25}},
        }],
    })


def test_end_to_end_v2_telegram_dispatch_formats_then_sends_once():
    store = MemoryStore()
    calls = []

    def send(destination, message):
        calls.append((destination, message))
        return f"message-{len(calls)}"

    report = public_report()
    verifier = lambda value, identity: identity.report_sha256 == value["report_sha256"]
    first = dispatch_public_telegram_report(
        report, "telegram:chat-1", verifier, store, send
    )
    second = dispatch_public_telegram_report(
        report, "telegram:chat-1", verifier, store, send
    )
    assert first.state is DeliveryState.SENT
    assert second.state is DeliveryState.DUPLICATE_SKIPPED
    assert len(calls) == 1
    assert "Alpha FC vs Beta FC" in calls[0][1]


def test_end_to_end_shadow_report_never_calls_telegram_transport():
    store = MemoryStore()
    report = public_report()
    report["release_mode"] = "INTERNAL_SHADOW"
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    with pytest.raises(PermissionError):
        dispatch_public_telegram_report(
            report, "telegram:chat-1", lambda *_: True, store,
            lambda *_: pytest.fail("shadow report must never be sent"),
        )
    assert store.claimed == set()


def test_partial_telegram_send_failure_is_unknown_and_never_replayed():
    store = MemoryStore()
    report = public_report()
    report["predictions"] = [
        {**report["predictions"][0], "home_team": f"Home {index:02d}"}
        for index in range(80)
    ]
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    attempts = []

    def send(destination, message):
        attempts.append(message)
        if len(attempts) == 2:
            raise TimeoutError("second chunk timed out")
        return "first-message"

    verifier = lambda value, identity: identity.report_sha256 == value["report_sha256"]
    with pytest.raises(DeliveryOutcomeUnknown):
        dispatch_public_telegram_report(
            report, "telegram:chat-1", verifier, store, send
        )
    prior_attempts = len(attempts)
    result = dispatch_public_telegram_report(
        report, "telegram:chat-1", verifier, store,
        lambda *_: pytest.fail("uncertain partial delivery must not be replayed"),
    )
    assert result.state is DeliveryState.DUPLICATE_SKIPPED
    assert len(attempts) == prior_attempts
    assert len(store.unknown) == 1


def test_legacy_telegram_entrypoint_refuses_v2_report_before_network(monkeypatch, tmp_path):
    import json
    import sys
    import types

    class RequestException(Exception):
        pass

    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(
        RequestException=RequestException,
        post=lambda *args, **kwargs: pytest.fail("legacy sender must not contact Telegram")
    ))
    from scripts import send_telegram_report

    report_path = tmp_path / "v2-report.json"
    report_path.write_text(json.dumps({
        "schema": REPORT_SCHEMA,
        "report_id": "legacy-block-test",
        "as_of_date": "2026-11-14",
        "predictions": [],
    }), encoding="utf-8")
    calls = []
    monkeypatch.setattr(send_telegram_report, "send_message", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "not-a-real-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "not-a-real-chat")
    monkeypatch.setattr(sys, "argv", ["send_telegram_report.py", "--report", str(report_path)])
    with pytest.raises(SystemExit) as exc:
        send_telegram_report.main()
    assert exc.value.code == 1
    assert calls == []



def test_telegram_dispatch_consumes_only_a_verified_four_surface_bundle(tmp_path):
    store = MemoryStore()
    report = public_report()
    bundle = build_report_surface_bundle(report)
    persist_report_surface_bundle(bundle, tmp_path)
    calls = []
    verifier = lambda value, identity: value.get("release_mode") == "RESTRICTED_PUBLIC"
    result = dispatch_public_telegram_bundle(
        tmp_path,
        bundle.identity.report_id,
        "telegram:chat-1",
        verifier,
        store,
        lambda destination, message: (calls.append((destination, message)) or "bundle-message-1"),
    )
    assert result.state is DeliveryState.SENT
    assert len(calls) == 1
    assert "Alpha FC vs Beta FC" in calls[0][1]


def test_telegram_bundle_dispatch_rejects_surface_drift_before_claim_or_send(tmp_path):
    store = MemoryStore()
    report = public_report()
    bundle = build_report_surface_bundle(report)
    paths = persist_report_surface_bundle(bundle, tmp_path)
    dashboard = json.loads(paths["dashboard"].read_text())
    dashboard["predictions"] = []
    paths["dashboard"].write_text(json.dumps(dashboard))
    calls = []
    with pytest.raises(ValueError, match="WEBSITE_REPORT_PROJECTION_IDENTITY_MISMATCH"):
        dispatch_public_telegram_bundle(
            tmp_path,
            bundle.identity.report_id,
            "telegram:chat-1",
            lambda *_: True,
            store,
            lambda *args: calls.append(args),
        )
    assert calls == []
    assert store.claimed == set()
