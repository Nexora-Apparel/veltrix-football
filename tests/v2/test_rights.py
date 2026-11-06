from datetime import datetime, timezone

import pytest

from veltrix_v2.domain.contracts import (
    DataUsePurpose,
    RightsStatus,
    SourceRights,
)
from veltrix_v2.domain.rights import evaluate_source_use, require_source_use


VERIFIED_AT = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def source_rights(**overrides):
    values = dict(
        source_id="provider-5dollar",
        rights_status=RightsStatus.VERIFIED,
        commercial_use_allowed=True,
        permitted_uses=frozenset({
            DataUsePurpose.HISTORICAL_IMPORT,
            DataUsePurpose.MODEL_TRAINING,
            DataUsePurpose.CALIBRATION,
            DataUsePurpose.INFERENCE,
            DataUsePurpose.PUBLIC_DISPLAY,
            DataUsePurpose.CACHE,
            DataUsePurpose.PAPER_EVALUATION,
        }),
        terms_url="https://example.invalid/terms",
        terms_version="2026-11",
        verified_at_utc=VERIFIED_AT,
    )
    values.update(overrides)
    return SourceRights(**values)


def test_unknown_rights_are_withheld_even_when_use_is_requested():
    rights = source_rights(rights_status=RightsStatus.UNVERIFIED)
    decision = evaluate_source_use(rights, DataUsePurpose.MODEL_TRAINING)
    assert not decision.allowed
    assert decision.reason_code == "RIGHTS_UNVERIFIED"


def test_commercial_training_is_rejected_when_only_research_use_is_allowed():
    rights = source_rights(commercial_use_allowed=False)
    decision = evaluate_source_use(rights, DataUsePurpose.MODEL_TRAINING)
    assert not decision.allowed
    assert decision.reason_code == "COMMERCIAL_USE_NOT_PERMITTED"


def test_purpose_not_in_license_is_rejected():
    rights = source_rights(permitted_uses=frozenset({DataUsePurpose.INFERENCE}))
    decision = evaluate_source_use(rights, DataUsePurpose.MODEL_TRAINING)
    assert not decision.allowed
    assert decision.reason_code == "PURPOSE_NOT_PERMITTED"


def test_raw_feed_redistribution_is_not_assumed_from_model_use_permission():
    rights = source_rights()
    decision = evaluate_source_use(rights, DataUsePurpose.RAW_REDISTRIBUTION)
    assert not decision.allowed
    assert decision.reason_code == "PURPOSE_NOT_PERMITTED"


def test_free_plan_attribution_is_returned_for_public_display():
    rights = source_rights(
        attribution_required=True,
        attribution_text="Football data by 5DollarFootballAPI",
        attribution_url="https://5dollarfootballapi.com",
    )
    decision = require_source_use(
        rights, DataUsePurpose.PUBLIC_DISPLAY, public_facing=True
    )
    assert decision.allowed
    assert decision.attribution_text == "Football data by 5DollarFootballAPI"
    assert decision.attribution_url == "https://5dollarfootballapi.com"


def test_public_display_fails_if_required_attribution_is_missing():
    rights = source_rights(attribution_required=True)
    decision = evaluate_source_use(
        rights, DataUsePurpose.PUBLIC_DISPLAY, public_facing=True
    )
    assert not decision.allowed
    assert decision.reason_code == "ATTRIBUTION_REQUIREMENT_UNSATISFIED"


def test_noncommercial_research_use_can_be_allowed_when_commercial_use_is_not():
    rights = source_rights(commercial_use_allowed=False)
    decision = evaluate_source_use(
        rights, DataUsePurpose.PAPER_EVALUATION, commercial=False
    )
    assert decision.allowed


def test_require_source_use_raises_for_blocked_source():
    rights = source_rights(rights_status=RightsStatus.UNVERIFIED)
    with pytest.raises(ValueError, match="RIGHTS_UNVERIFIED"):
        require_source_use(rights, DataUsePurpose.CACHE)
