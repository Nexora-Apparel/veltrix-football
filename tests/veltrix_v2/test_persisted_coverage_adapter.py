from datetime import datetime, timedelta, timezone

from veltrix_v2.data.persisted_coverage_adapter import adapt_persisted_coverage_rows
from veltrix_v2.data.provider_registry import DataDomain

UTC = timezone.utc
AS_OF = datetime(2026, 11, 14, 12, tzinfo=UTC)
KICKOFF = AS_OF + timedelta(days=1)
HASH = "a" * 64


def fixture_row():
    return {"fixture_id": "fx-1", "competition_id": "league-a", "kickoff_at": KICKOFF}


def observation_row(**changes):
    row = {
        "provider": "5DollarFootballAPI",
        "source_id": "5dollarfootball",
        "data_type": "lineup",
        "payload_sha256": HASH,
        "available_at": AS_OF - timedelta(hours=2),
        "recorded_at": AS_OF - timedelta(hours=1),
        "rights_approval_id": "approval-1",
        "payload": {
            "fixture_id": "fx-1",
            "competition_id": "league-a",
            "rights_approved": True,
            "rights_approval_id": "approval-1",
            "rights_evidence_sha256": "b" * 64,
            "rights_evaluated_at": (AS_OF - timedelta(minutes=30)).isoformat(),
            "point_in_time_certifiable": True,
        },
    }
    row.update(changes)
    return row


def test_adapter_preserves_explicit_provenance_and_rights_evidence():
    result = adapt_persisted_coverage_rows([fixture_row()], [observation_row()])
    assert len(result.fixtures) == 1
    assert len(result.evidence) == 1
    item = result.evidence[0]
    assert item.domain is DataDomain.LINEUPS
    assert item.provider == "5DollarFootballAPI"
    assert item.rights_approved is True
    assert item.rights_approval_id == "approval-1"
    assert item.rights_evaluated_at == AS_OF - timedelta(minutes=30)
    assert item.point_in_time_certifiable is True


def test_adapter_does_not_infer_missing_rights_decision_or_timestamp():
    missing_rights = observation_row(payload={
        "fixture_id": "fx-1", "competition_id": "league-a",
        "point_in_time_certifiable": True,
        "rights_evidence_sha256": "b" * 64,
    })
    missing_time = observation_row(payload={
        "fixture_id": "fx-1", "competition_id": "league-a",
        "point_in_time_certifiable": True, "rights_approved": True,
        "rights_evidence_sha256": "b" * 64,
    })
    result = adapt_persisted_coverage_rows(
        [fixture_row()], [missing_rights, missing_time],
    )
    assert result.evidence == ()
    assert result.rejected_observation_rows == 2


def test_adapter_rejects_naive_fixture_and_observation_timestamps():
    bad_fixture = fixture_row()
    bad_fixture["kickoff_at"] = datetime(2026, 11, 15)
    bad_observation = observation_row(available_at=datetime(2026, 11, 14, 10))
    result = adapt_persisted_coverage_rows([bad_fixture], [bad_observation])
    assert result.fixtures == ()
    assert result.evidence == ()
    assert result.rejected_fixture_rows == 1
    assert result.rejected_observation_rows == 1


def test_adapter_reports_unsupported_data_types_without_fabricating_domains():
    result = adapt_persisted_coverage_rows(
        [fixture_row()], [observation_row(data_type="unqualified_metric")],
    )
    assert result.evidence == ()
    assert result.unsupported_data_types == ("unqualified_metric",)


def test_adapter_uses_canonical_identity_from_joined_sql_columns():
    row = observation_row(payload={
        "rights_approved": True,
        "rights_approval_id": "approval-1",
        "rights_evidence_sha256": "b" * 64,
        "rights_evaluated_at": (AS_OF - timedelta(minutes=30)).isoformat(),
    })
    row["fixture_id"] = "fx-1"
    row["competition_id"] = "league-a"
    row["point_in_time_certifiable"] = True
    result = adapt_persisted_coverage_rows([fixture_row()], [row])
    assert len(result.evidence) == 1
    assert result.evidence[0].fixture_id == "fx-1"
    assert result.evidence[0].competition_id == "league-a"


def test_adapter_accepts_json_text_payload_without_changing_values():
    row = observation_row()
    import json
    row["payload"] = json.dumps(row["payload"])
    result = adapt_persisted_coverage_rows([fixture_row()], [row])
    assert len(result.evidence) == 1
