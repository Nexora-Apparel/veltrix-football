from datetime import datetime, timezone
from pathlib import Path

import pytest

from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose
from veltrix_v2.data.provider_rights_registry import load_provider_rights_registry
from veltrix_v2.data.rights import evaluate_source_use


ROOT = Path(__file__).resolve().parents[1]
REVIEWED = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


def _registry():
    return {
        (item.provider, item.data_type): item
        for item in load_provider_rights_registry(ROOT, reviewed_at_utc=REVIEWED)
    }


def test_registry_hash_binds_every_approved_source_to_its_review_document():
    approvals = load_provider_rights_registry(ROOT, reviewed_at_utc=REVIEWED)
    assert len(approvals) == 4
    for approval in approvals:
        assert approval.evidence_sha256
        assert len(approval.evidence_sha256) == 64
        assert "/blob/main/" in approval.evidence_uri
        assert approval.reviewed_at_utc == REVIEWED


def test_fivedollar_commercial_fixture_result_use_requires_linked_attribution():
    approval = _registry()[("5DollarFootballAPI", "fixture_result")]
    assert approval.status is ApprovalStatus.APPROVED
    assert approval.commercial_use_allowed is True
    assert approval.attribution_required is True
    assert approval.attribution_text == "Football data by 5DollarFootballAPI"

    storage = evaluate_source_use(approval, DataUsePurpose.STORAGE, at_utc=REVIEWED)
    training = evaluate_source_use(approval, DataUsePurpose.MODEL_TRAINING, at_utc=REVIEWED)
    display = evaluate_source_use(
        approval, DataUsePurpose.PUBLIC_DISPLAY, at_utc=REVIEWED, public_facing=True
    )
    raw = evaluate_source_use(approval, DataUsePurpose.RAW_REDISTRIBUTION, at_utc=REVIEWED)

    assert storage.allowed and training.allowed
    assert display.allowed and display.reason_code == "APPROVED_WITH_ATTRIBUTION"
    assert display.attribution_text == "Football data by 5DollarFootballAPI"
    assert not raw.allowed and raw.reason_code == "RAW_REDISTRIBUTION_PROHIBITED"


def test_odds_api_current_odds_allowed_but_historical_archive_fails_closed():
    approvals = _registry()
    current = approvals[("The Odds API", "bookmaker_odds_current")]
    historical = approvals[("The Odds API", "bookmaker_odds_historical")]

    assert current.status is ApprovalStatus.APPROVED
    assert evaluate_source_use(
        current, DataUsePurpose.MODEL_TRAINING, at_utc=REVIEWED
    ).allowed
    assert evaluate_source_use(
        current, DataUsePurpose.PUBLIC_DISPLAY, at_utc=REVIEWED, public_facing=True
    ).allowed
    assert current.attribution_required is False
    assert current.raw_redistribution_allowed is False

    denied = evaluate_source_use(
        historical, DataUsePurpose.HISTORICAL_IMPORT, at_utc=REVIEWED
    )
    assert historical.status is ApprovalStatus.PROVISIONAL
    assert not denied.allowed
    assert denied.reason_code == "SOURCE_RIGHTS_NOT_APPROVED"


def test_wyscout_cc_by_source_requires_attribution_and_blocks_raw_redistribution():
    approval = _registry()[("Pappalardo et al. Wyscout Open Event Dataset", "historical_shot_events")]
    assert approval.status is ApprovalStatus.APPROVED
    assert approval.rights_basis == "OPEN_LICENSE"
    assert approval.commercial_use_allowed is True

    training = evaluate_source_use(
        approval, DataUsePurpose.MODEL_TRAINING, at_utc=REVIEWED
    )
    display = evaluate_source_use(
        approval, DataUsePurpose.PUBLIC_DISPLAY, at_utc=REVIEWED, public_facing=True
    )
    raw = evaluate_source_use(
        approval, DataUsePurpose.RAW_REDISTRIBUTION, at_utc=REVIEWED
    )

    assert training.allowed
    assert display.allowed and display.reason_code == "APPROVED_WITH_ATTRIBUTION"
    assert "CC BY 4.0" in (display.attribution_text or "")
    assert not raw.allowed and raw.reason_code == "RAW_REDISTRIBUTION_PROHIBITED"


def test_registry_rejects_naive_review_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        load_provider_rights_registry(ROOT, reviewed_at_utc=datetime(2026, 11, 12, 12))
