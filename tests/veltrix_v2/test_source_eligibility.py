from datetime import datetime, timedelta, timezone

from veltrix_v2.contracts import ForecastCutoff, ProviderObservation
from veltrix_v2.quality import SourceApproval, evaluate_observation

T = datetime(2026, 11, 11, 6, tzinfo=timezone.utc)


def observation():
    return ProviderObservation(
        provider="strikerapi", endpoint="list_games", entity_type="fixture",
        provider_entity_id="fx-1", competition_key="EPL", season="2026",
        retrieved_at_utc=T, source_event_time_utc=T, available_at_utc=T,
        payload_sha256="b" * 64, schema_version="1",
        rights_approval_id="approval-epl-fixtures", values={},
    )


def approval(**overrides):
    values = dict(approval_id="approval-epl-fixtures", provider="strikerapi",
                  competition_key="EPL", data_type="fixtures_results", status="approved",
                  valid_from_utc=T - timedelta(days=1),
                  permitted_uses=("collection", "storage", "model_training", "benchmarking", "public_display", "commercial_use"))
    values.update(overrides)
    values.setdefault("evidence_uri", "https://example.test/provider-terms")
    values.setdefault("evidence_sha256", "a" * 64)
    values.setdefault("reviewed_at_utc", values["valid_from_utc"] + timedelta(minutes=1))
    values.setdefault("reviewer_id", "test-rights-reviewer")
    values.setdefault("rights_basis", "terms")
    return SourceApproval(**values)


def decide(obs=None, approvals=None, cutoff=None):
    return evaluate_observation(
        obs or observation(), data_type="fixtures_results",
        cutoff=ForecastCutoff(cutoff or T), approvals=tuple(approvals or (approval(),)),
        max_age=timedelta(days=2),
    )


def test_approved_exact_scope_is_eligible():
    assert decide().eligible


def test_provisional_or_wrong_data_type_is_rejected():
    assert not decide(approvals=(approval(status="provisional"),)).eligible
    assert not decide(approvals=(approval(data_type="odds"),)).eligible


def test_future_observation_is_rejected():
    late = ProviderObservation(
        provider="strikerapi", endpoint="list_games", entity_type="fixture",
        provider_entity_id="fx-2", competition_key="EPL", season="2026",
        retrieved_at_utc=T + timedelta(minutes=1),
        source_event_time_utc=T, available_at_utc=T + timedelta(minutes=1),
        payload_sha256="c" * 64, schema_version="1",
        rights_approval_id="approval-epl-fixtures", values={},
    )
    assert not decide(obs=late).eligible


def test_stale_observation_is_rejected():
    old = T - timedelta(days=10)
    stale = ProviderObservation(
        provider="strikerapi", endpoint="list_games", entity_type="fixture",
        provider_entity_id="fx-3", competition_key="EPL", season="2026",
        retrieved_at_utc=old, source_event_time_utc=old, available_at_utc=old,
        payload_sha256="d" * 64, schema_version="1",
        rights_approval_id="approval-epl-fixtures", values={},
    )
    assert decide(
        obs=stale,
        approvals=(approval(valid_from_utc=old - timedelta(days=1)),),
    ).reason == "observation_stale_at_forecast_cutoff"


def test_expired_approval_is_rejected():
    assert decide(
        approvals=(approval(valid_until_utc=T + timedelta(hours=1)),),
        cutoff=T + timedelta(hours=2),
    ).reason == "approval_expired_at_cutoff"



def test_approval_must_be_valid_when_observation_was_retrieved():
    approval_after_retrieval = approval(valid_from_utc=T + timedelta(minutes=1))
    assert decide(approvals=(approval_after_retrieval,)).reason == "approval_not_valid_at_observation_retrieval"

    approval_expired_before_retrieval = approval(
        valid_from_utc=T - timedelta(days=2),
        valid_until_utc=T - timedelta(minutes=1),
    )
    assert decide(approvals=(approval_expired_before_retrieval,)).reason == "approval_expired_at_observation_retrieval"


def test_negative_max_age_is_rejected():
    import pytest
    from veltrix_v2.quality.eligibility import evaluate_observation

    with pytest.raises(ValueError, match="MAX_AGE_MUST_BE_NON_NEGATIVE"):
        evaluate_observation(
            observation(), data_type="fixtures_results",
            cutoff=ForecastCutoff(T), approvals=(approval(),),
            max_age=-timedelta(seconds=1),
        )


def test_model_training_permission_does_not_implicitly_grant_public_display():
    restricted = approval(permitted_uses=("collection", "storage", "model_training"))
    assert decide(approvals=(restricted,)).eligible
    public = evaluate_observation(
        observation(), data_type="fixtures_results",
        cutoff=ForecastCutoff(T), approvals=(restricted,),
        max_age=timedelta(days=2),
        required_uses=("collection", "storage", "model_training", "public_display", "commercial_use"),
    )
    assert not public.eligible
    assert public.reason == "required_source_use_not_approved:public_display,commercial_use"


def test_source_without_model_training_permission_is_not_training_eligible():
    restricted = approval(permitted_uses=("collection", "storage", "public_display"))
    decision = decide(approvals=(restricted,))
    assert not decision.eligible
    assert decision.reason == "required_source_use_not_approved:model_training"


def test_unknown_or_duplicate_required_uses_are_rejected():
    import pytest
    with pytest.raises(ValueError, match="REQUIRED_USES_INVALID"):
        evaluate_observation(
            observation(), data_type="fixtures_results",
            cutoff=ForecastCutoff(T), approvals=(approval(),),
            max_age=timedelta(days=2), required_uses=("model_training", "model_training"),
        )
    with pytest.raises(ValueError, match="invalid or duplicate source permission"):
        approval(permitted_uses=("model_training", "not_a_real_permission"))



def test_approved_source_requires_auditable_rights_document_and_review():
    import pytest

    values = {
        "approval_id": "approval-unverified",
        "provider": "provider-a",
        "competition_key": "league-a",
        "data_type": "match_result",
        "status": "approved",
        "valid_from_utc": T - timedelta(days=1),
        "permitted_uses": ("collection", "storage", "model_training"),
    }
    with pytest.raises(ValueError, match="traceable rights evidence"):
        SourceApproval(**values)
