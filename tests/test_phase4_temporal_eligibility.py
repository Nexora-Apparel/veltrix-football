from copy import deepcopy
from datetime import datetime, timezone

import pytest

from veltrix_v2.data.temporal_eligibility import (
    evaluate_observation,
    feature_set_sha256,
    select_as_of,
)


CUTOFF = "2026-11-20T12:00:00Z"
RIGHTS = {
    "status": "APPROVED",
    "permitted_purposes": ["model_training"],
    "scope": {
        "provider": "provider-a",
        "product": "football-data",
        "endpoint": "/fixtures",
        "field_family": "team_state",
        "competition": "league-a",
        "season": "2026",
    },
    "effective_from": "2026-01-01T00:00:00Z",
    "expires_at": "2027-01-01T00:00:00Z",
}
BASE = {
    "observation_id": "obs-1",
    "provider": "provider-a",
    "product": "football-data",
    "endpoint": "/fixtures",
    "field_family": "team_state",
    "competition": "league-a",
    "season": "2026",
    "source_published_at": "2026-11-20T10:00:00Z",
    "source_timestamp_basis": "provider_timestamp",
    "source_effective_at": "2026-11-20T09:00:00Z",
    "retrieved_at": "2026-11-20T10:02:00Z",
    "temporal_semantics": "state_as_of_cutoff",
    "revision_history_complete": True,
}


_DEFAULT_RIGHTS = object()


def decision(row=None, rights=_DEFAULT_RIGHTS, cutoff=CUTOFF, **kwargs):
    return evaluate_observation(
        row or deepcopy(BASE),
        cutoff,
        RIGHTS if rights is _DEFAULT_RIGHTS else rights,
        **kwargs,
    )


def test_publication_before_cutoff_is_eligible():
    assert decision().eligible


def test_publication_exactly_at_cutoff_is_inclusive():
    row = deepcopy(BASE)
    row["source_published_at"] = CUTOFF
    row["retrieved_at"] = CUTOFF
    assert decision(row).eligible


def test_one_millisecond_after_cutoff_is_rejected():
    row = deepcopy(BASE)
    row["source_published_at"] = "2026-11-20T12:00:00.001Z"
    assert "PUBLISHED_AFTER_CUTOFF" in decision(row).reason_codes


@pytest.mark.parametrize("stamp", [
    "2026-11-20T13:00:00+01:00",
    "2026-11-20T12:00:00Z",
])
def test_timezone_offsets_normalize_to_same_instant(stamp):
    row = deepcopy(BASE)
    row["source_published_at"] = stamp
    row["retrieved_at"] = stamp
    assert decision(row).eligible


@pytest.mark.parametrize("stamp", [None, "2026-11-20", "2026-11-20T10:00:00", "not-a-time"])
def test_missing_date_only_naive_and_invalid_publication_fail_closed(stamp):
    row = deepcopy(BASE)
    row["source_published_at"] = stamp
    assert not decision(row).eligible
    assert any(code in decision(row).reason_codes for code in (
        "SOURCE_TIMESTAMP_MISSING", "SOURCE_TIMESTAMP_UNTRUSTED"
    ))


def test_event_time_never_substitutes_for_publication_time():
    row = deepcopy(BASE)
    row["source_published_at"] = None
    row["event_at"] = "2026-11-20T08:00:00Z"
    assert "SOURCE_TIMESTAMP_MISSING" in decision(row).reason_codes


def test_effective_time_never_substitutes_for_publication_time():
    row = deepcopy(BASE)
    row["source_published_at"] = None
    row["source_effective_at"] = "2026-11-20T08:00:00Z"
    assert "SOURCE_TIMESTAMP_MISSING" in decision(row).reason_codes


@pytest.mark.parametrize("basis", [None, "unknown", "retrieved_at", "kickoff_time"])
def test_unknown_timestamp_basis_rejected(basis):
    row = deepcopy(BASE)
    row["source_timestamp_basis"] = basis
    assert "SOURCE_TIMESTAMP_UNTRUSTED" in decision(row).reason_codes


def test_retrieval_after_cutoff_requires_verified_archival_proof():
    row = deepcopy(BASE)
    row.update(
        source_timestamp_basis="archival_snapshot_timestamp",
        retrieved_at="2026-11-21T10:00:00Z",
        archive_proof_id="archive-1",
    )
    assert "RETRIEVED_AFTER_CUTOFF_WITHOUT_ARCHIVE_PROOF" in decision(row).reason_codes
    assert decision(row, archive_proof_verified=True).eligible


def test_future_effective_state_rejected_but_explicit_fixture_forecast_allowed():
    row = deepcopy(BASE)
    row["source_effective_at"] = "2026-11-20T13:00:00Z"
    row["fixture_kickoff_at"] = "2026-11-20T18:00:00Z"
    assert "FUTURE_EFFECTIVE_STATE" in decision(row).reason_codes
    row["temporal_semantics"] = "forecast_for_fixture"
    assert decision(row).eligible


def test_forecast_effective_after_fixture_kickoff_rejected():
    row = deepcopy(BASE)
    row.update(
        source_effective_at="2026-11-20T19:00:00Z",
        fixture_kickoff_at="2026-11-20T18:00:00Z",
        temporal_semantics="forecast_for_fixture",
    )
    assert "FIELD_SEMANTICS_UNVERIFIED" in decision(row).reason_codes


def test_rights_missing_wrong_scope_expired_or_revoked_rejected():
    assert "RIGHTS_NOT_APPROVED" in decision(rights=None).reason_codes
    wrong_scope = deepcopy(RIGHTS)
    wrong_scope["scope"]["provider"] = "other"
    assert "RIGHTS_NOT_APPROVED" in decision(rights=wrong_scope).reason_codes
    expired = deepcopy(RIGHTS)
    expired["expires_at"] = "2026-11-20T11:59:59Z"
    assert "RIGHTS_NOT_APPROVED" in decision(rights=expired).reason_codes
    revoked = deepcopy(RIGHTS)
    revoked["revoked_at"] = "2026-11-20T11:00:00Z"
    assert "RIGHTS_NOT_APPROVED" in decision(rights=revoked).reason_codes


def test_rights_must_explicitly_permit_training():
    rights = deepcopy(RIGHTS)
    rights["permitted_purposes"] = ["internal_analysis"]
    assert "RIGHTS_NOT_APPROVED" in decision(rights=rights).reason_codes


def test_naive_or_missing_cutoff_is_rejected():
    assert not decision(cutoff="2026-11-20T12:00:00").eligible
    assert not decision(cutoff=None).eligible


def test_later_correction_does_not_change_earlier_cutoff_selection():
    original = deepcopy(BASE)
    corrected = deepcopy(BASE)
    corrected.update(
        observation_id="obs-2",
        source_published_at="2026-11-20T14:00:00Z",
        retrieved_at="2026-11-20T14:01:00Z",
        source_effective_at="2026-11-20T14:00:00Z",
    )
    selected_before = select_as_of([original], CUTOFF, RIGHTS)
    selected_after_adding_future_correction = select_as_of([original, corrected], CUTOFF, RIGHTS)
    assert selected_before == selected_after_adding_future_correction == original


def test_correction_published_before_cutoff_supersedes_older_value():
    first = deepcopy(BASE)
    corrected = deepcopy(BASE)
    corrected.update(
        observation_id="obs-2",
        source_published_at="2026-11-20T11:30:00Z",
        retrieved_at="2026-11-20T11:31:00Z",
    )
    assert select_as_of([first, corrected], CUTOFF, RIGHTS) == corrected


def test_incomplete_revision_history_is_rejected():
    row = deepcopy(BASE)
    row["revision_history_complete"] = False
    assert "REVISION_HISTORY_INCOMPLETE" in decision(row).reason_codes


def test_moving_cutoff_earlier_never_selects_later_publication():
    rows = []
    for i, hour in enumerate((8, 9, 10, 11, 12, 13)):
        row = deepcopy(BASE)
        row.update(
            observation_id=f"obs-{i}",
            source_published_at=f"2026-11-20T{hour:02d}:00:00Z",
            retrieved_at=f"2026-11-20T{hour:02d}:01:00Z",
        )
        rows.append(row)
    for hour in range(8, 13):
        cutoff = f"2026-11-20T{hour:02d}:30:00Z"
        selected = select_as_of(rows, cutoff, RIGHTS)
        assert selected is None or selected["source_published_at"] <= cutoff


def test_post_cutoff_additions_never_change_selected_value_for_prior_cutoff():
    rows = []
    for i, hour in enumerate((8, 9, 10)):
        row = deepcopy(BASE)
        row.update(
            observation_id=f"obs-{i}",
            source_published_at=f"2026-11-20T{hour:02d}:00:00Z",
            retrieved_at=f"2026-11-20T{hour:02d}:01:00Z",
        )
        rows.append(row)
    before = select_as_of(rows, CUTOFF, RIGHTS)
    late = deepcopy(BASE)
    late.update(
        observation_id="late",
        source_published_at="2026-11-20T12:00:00.001Z",
        retrieved_at="2026-11-20T12:01:00Z",
    )
    assert select_as_of(rows + [late], CUTOFF, RIGHTS) == before


def test_cutoff_input_is_not_mutated_and_feature_hash_is_replay_stable():
    row = deepcopy(BASE)
    frozen = deepcopy(row)
    first = evaluate_observation(row, CUTOFF, RIGHTS)
    second = evaluate_observation(row, CUTOFF, RIGHTS)
    assert row == frozen
    assert first == second
    payload = {"team_state": {"rating": 1420}, "missing_lineup": None}
    assert feature_set_sha256(payload) == feature_set_sha256(deepcopy(payload))
    assert feature_set_sha256(payload) != feature_set_sha256({"team_state": {"rating": 1421}, "missing_lineup": None})


def test_missing_feature_is_not_imputed_to_zero():
    assert feature_set_sha256({"lineup": None}) != feature_set_sha256({"lineup": 0})
