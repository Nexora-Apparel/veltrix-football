from __future__ import annotations

from veltrix_v2.reporting.artifact_bundle import (
    build_report_surface_bundle,
    serialize_portable_report_surface_bundle,
    load_authorized_scheduled_report_from_portable,
)
from veltrix_v2.reporting.delivery import DeliveryState
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity
from veltrix_v2.reporting.telegram import dispatch_public_telegram_portable_bundle
from app.report_artifacts import load_v2_portable_report_bundle


class MemoryStore:
    def __init__(self):
        self.claimed = set()
        self.sent = {}

    def claim(self, key, report_id, report_sha256, destination):
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    def mark_sent(self, key, receipt):
        self.sent[key] = receipt

    def mark_unknown(self, key, reason_code):
        raise AssertionError("stub transport must not produce uncertain outcomes")


def public_report():
    return bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "veltrix-portable-cross-surface-2026-11-14",
        "as_of_date": "2026-11-14",
        "release_mode": "RESTRICTED_PUBLIC",
        "predictions": [{
            "fixture_id": "fixture-veltrix-001",
            "publication_status": "PUBLISHED",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "competition_id": "competition-1",
            "competition_name": "Example League",
            "model_build_id": "model-build-1",
            "kickoff_wat": "17:30 WAT",
            "certified_markets": ["1X2"],
            "markets": {"1X2": {"home": 0.50, "draw": 0.25, "away": 0.25}},
        }],
    })


def test_website_scheduler_and_telegram_consume_identical_portable_report_bytes():
    report = public_report()
    raw = serialize_portable_report_surface_bundle(build_report_surface_bundle(report))
    verifier = lambda value, identity: (
        value.get("report_id") == identity.report_id
        and value.get("report_sha256") == identity.report_sha256
    )

    website = load_v2_portable_report_bundle(raw, verifier)
    scheduled = load_authorized_scheduled_report_from_portable(raw, verifier)

    store = MemoryStore()
    sent = []
    attempt = dispatch_public_telegram_portable_bundle(
        raw,
        "telegram:integration-test",
        verifier,
        store,
        lambda destination, message: (
            sent.append((destination, message)) or f"message-{len(sent)}"
        ),
    )

    assert website is not None
    assert website["report"] == report
    assert scheduled == website["scheduled"] == report
    assert website["telegram"] == report
    assert website["identity"].report_id == scheduled["report_id"]
    assert website["identity"].report_sha256 == scheduled["report_sha256"]
    assert attempt.state == DeliveryState.SENT
    assert len(store.claimed) == 1
    assert len(sent) == 1
    assert sent[0][0] == "telegram:integration-test"
    assert "Alpha FC vs Beta FC" in sent[0][1]
    assert report["report_id"] in sent[0][1]
