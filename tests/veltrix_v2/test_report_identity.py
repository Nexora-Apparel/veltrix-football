from __future__ import annotations

from copy import deepcopy

import pytest

from veltrix_v2.reporting.report_identity import (
    REPORT_SCHEMA,
    assert_report_surface_bundle,
    assert_same_report,
    bind_report_identity,
    create_report_identity,
    delivery_idempotency_key,
    verify_report_identity,
)


def report():
    return {
        "schema": REPORT_SCHEMA,
        "report_id": "veltrix-2026-11-14-main",
        "as_of_date": "2026-11-14",
        "release_mode": "INTERNAL_SHADOW",
        "predictions": [
            {"fixture_ref": "fx-1", "status": "SHADOW_ONLY", "probabilities": None},
        ],
    }


def test_identity_is_stable_across_json_key_order():
    first = report()
    second = dict(reversed(list(first.items())))
    assert create_report_identity(first) == create_report_identity(second)


def test_binding_adds_hash_and_verification_accepts_exact_bytes():
    bound = bind_report_identity(report())
    identity = verify_report_identity(bound)
    assert bound["report_sha256"] == identity.report_sha256
    assert len(identity.report_sha256) == 64


def test_content_mutation_after_binding_is_rejected():
    bound = bind_report_identity(report())
    changed = deepcopy(bound)
    changed["predictions"][0]["status"] = "PUBLISHED"
    with pytest.raises(ValueError, match="content hash"):
        verify_report_identity(changed)


def test_all_surfaces_must_reference_same_report_identity():
    canonical = bind_report_identity(report())
    website = deepcopy(canonical)
    scheduled = deepcopy(canonical)
    telegram = deepcopy(canonical)
    identity = assert_same_report([website, scheduled, telegram])
    assert identity.report_id == "veltrix-2026-11-14-main"


def test_surface_drift_is_rejected_even_when_report_id_matches():
    canonical = bind_report_identity(report())
    drifted = deepcopy(canonical)
    drifted["predictions"][0]["status"] = "PUBLISHED"
    drifted["report_sha256"] = bind_report_identity({
        **{key: value for key, value in drifted.items() if key != "report_sha256"}
    })["report_sha256"]
    with pytest.raises(ValueError, match="same immutable report"):
        assert_same_report([canonical, drifted])


def test_destination_is_part_of_delivery_idempotency_key():
    identity = create_report_identity(report())
    assert delivery_idempotency_key(identity, "telegram:chat-a") != delivery_idempotency_key(identity, "telegram:chat-b")


def test_nan_and_non_json_values_are_rejected():
    invalid = report()
    invalid["diagnostic"] = float("nan")
    with pytest.raises(ValueError, match="non-canonical JSON"):
        create_report_identity(invalid)


@pytest.mark.parametrize("as_of_date", ["14-11-2026", "2026-2-03", "2026-02-30"])
def test_noncanonical_or_invalid_report_dates_are_rejected(as_of_date):
    invalid = report()
    invalid["as_of_date"] = as_of_date
    with pytest.raises(ValueError):
        create_report_identity(invalid)


def test_report_hash_cannot_be_constructed_from_missing_schema_or_identity():
    with pytest.raises(ValueError):
        create_report_identity({"report_id": "r1", "as_of_date": "2026-11-14"})


def test_canonical_scheduled_telegram_and_website_surfaces_share_one_report():
    canonical = bind_report_identity(report())
    scheduled = deepcopy(canonical)
    telegram = deepcopy(canonical)
    website = {
        "snapshot_schema": "VELTRIX_DASHBOARD_V1",
        "as_of_date": canonical["as_of_date"],
        "report_id": canonical["report_id"],
        "report_sha256": canonical["report_sha256"],
        "status": canonical.get("status"),
        "release_mode": canonical.get("release_mode"),
        "predictions": canonical["predictions"],
    }
    identity = assert_report_surface_bundle(canonical, scheduled, telegram, website)
    assert identity.report_sha256 == canonical["report_sha256"]


def test_four_surface_parity_rejects_dashboard_from_another_revision():
    canonical = bind_report_identity(report())
    website = {
        "snapshot_schema": "VELTRIX_DASHBOARD_V1",
        "as_of_date": canonical["as_of_date"],
        "report_id": canonical["report_id"],
        "report_sha256": "f" * 64,
        "status": canonical.get("status"),
        "release_mode": canonical.get("release_mode"),
        "predictions": canonical["predictions"],
    }
    with pytest.raises(ValueError, match="WEBSITE_REPORT_PROJECTION_IDENTITY_MISMATCH"):
        assert_report_surface_bundle(canonical, deepcopy(canonical), deepcopy(canonical), website)
