from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.data.batch import assess_history_batch, reconcile_source_manifest
from veltrix_v2.data.contracts import (
    ApprovalStatus, DataUsePurpose, FixtureStatus, HistoricalFixture,
    ImportOutcomeStatus, ProviderResponse, SourceApproval,
)
from veltrix_v2.data.fivedollar import (
    AVAILABILITY_BASIS, FixturePageError, parse_fixture_page,
)
from veltrix_v2.data.postgres import PostgresHistoryStore
from veltrix_v2.data.rights import evaluate_fixture_import, evaluate_source_use
from scripts import phase2_fivedollar_history_dry_run as history_probe
from scripts import phase3_import_fivedollar_history as phase3_import
from scripts import phase3_audit_staging_import as phase3_audit

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
KICKOFF = NOW - timedelta(days=30)


def approval(**changes):
    values = dict(
        approval_id="approval-test",
        provider="5DollarFootballAPI",
        source_id="5dollarfootballapi",
        competition_scope="4160026622,3118717965",
        data_type="fixture_result",
        status=ApprovalStatus.APPROVED,
        permitted_uses=frozenset({
            DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE,
            DataUsePurpose.HISTORICAL_IMPORT, DataUsePurpose.MODEL_TRAINING,
            DataUsePurpose.CACHE, DataUsePurpose.PUBLIC_DISPLAY,
        }),
        commercial_use_allowed=True,
        terms_url="https://5dollarfootballapi.com/terms",
        terms_version="October 2026",
        evidence_uri="https://example.test/rights-review.md",
        evidence_sha256="a" * 64,
        rights_basis="TERMS",
        reviewed_at_utc=NOW - timedelta(days=1),
        reviewer_id="test-review",
        valid_from_utc=NOW - timedelta(days=1),
        attribution_required=True,
        attribution_text="Football data by 5DollarFootballAPI",
        attribution_url="https://5dollarfootballapi.com",
        raw_redistribution_allowed=False,
    )
    values.update(changes)
    return SourceApproval(**values)


def fixture(fixture_id="101", competition_id="4160026622", status=FixtureStatus.FINISHED,
            home_score=2, away_score=1, payload_hash=None, approval_id="approval-test"):
    payload = {
        "id": int(fixture_id), "league": {"id": int(competition_id), "name": "England Premier League"},
        "teams": {"home": {"id": 11, "name": "Home"}, "away": {"id": 12, "name": "Away"}},
        "kickoff_utc": KICKOFF.isoformat(), "status": status.value.lower(),
        "goals": {"home": home_score, "away": away_score},
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return HistoricalFixture(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        provider_fixture_id=fixture_id, provider_competition_id=competition_id,
        provider_home_team_id="11", provider_away_team_id="12",
        competition_name="England Premier League", home_team_name="Home", away_team_name="Away",
        kickoff_at_utc=KICKOFF, season_key="2025/2026", status=status,
        home_score=home_score if status is FixtureStatus.FINISHED else None,
        away_score=away_score if status is FixtureStatus.FINISHED else None,
        payload=payload, payload_sha256=payload_hash or hashlib.sha256(raw).hexdigest(),
        retrieved_at_utc=NOW, source_event_time_utc=KICKOFF,
        available_at_utc=KICKOFF + timedelta(days=4) if status is FixtureStatus.FINISHED else None,
        availability_basis=AVAILABILITY_BASIS if status is FixtureStatus.FINISHED else "not_settled",
        point_in_time_certifiable=False, rights_approval_id=approval_id,
    )


def provider_page(rows=None, pagination=None):
    body = {
        "success": 1,
        "data": rows if rows is not None else [{
            "id": 101,
            "league": {"id": 4160026622, "name": "England Premier League", "season": "2025/2026"},
            "teams": {"home": {"id": 11, "name": "Home"}, "away": {"id": 12, "name": "Away"}},
            "kickoff_utc": KICKOFF.isoformat().replace("+00:00", "Z"),
            "kickoff_ts": int(KICKOFF.timestamp()),
            "status": "finished",
            "goals": {"home": 2, "away": 1},
        }],
        "pagination": pagination or {"page": 1, "per_page": 100, "has_more": False},
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def test_phase3_import_requires_explicit_staging_enable(monkeypatch):
    monkeypatch.delenv("VELTRIX_ENABLE_STAGING_IMPORT", raising=False)
    with pytest.raises(RuntimeError, match="STAGING_IMPORT_EXPLICIT_ENABLE_REQUIRED"):
        phase3_import._preflight("not-a-real-database-url", "veltrix_football_staging")


def test_phase3_import_requires_all_staging_tables_empty():
    phase3_import._require_empty_staging_database((0, 0, 0, 0, 0, 0))


@pytest.mark.parametrize("counts", [
    (1, 0, 0, 0, 0, 0),
    (0, 1, 0, 0, 0, 0),
    (0, 0, 1, 0, 0, 0),
    (0, 0, 0, 1, 0, 0),
    (0, 0, 0, 0, 1, 0),
    (0, 0, 0, 0, 0, 1),
    (0, 0, 0, 0, 0),
])
def test_phase3_import_rejects_nonempty_or_incomplete_staging_counts(counts):
    with pytest.raises(RuntimeError, match="STAGING_IMPORT_REQUIRES_EMPTY_DEDICATED_DATABASE"):
        phase3_import._require_empty_staging_database(counts)


def test_phase3_import_rejects_non_staging_database_before_connecting(monkeypatch):
    monkeypatch.setenv("VELTRIX_ENABLE_STAGING_IMPORT", "YES")
    with pytest.raises(RuntimeError, match="STAGING_IMPORT_DATABASE_ALLOWLIST_MISMATCH"):
        phase3_import._preflight("not-a-real-database-url", "veltrix-football")


def test_phase3_import_pins_the_exact_staging_neon_endpoint(monkeypatch):
    monkeypatch.setenv("VELTRIX_ENABLE_STAGING_IMPORT", "YES")
    monkeypatch.setenv("VELTRIX_EXPECTED_DATABASE_HOST", phase3_import.EXPECTED_DATABASE_HOST)
    with pytest.raises(RuntimeError, match="STAGING_DATABASE_HOST_ALLOWLIST_MISMATCH"):
        phase3_import._preflight(
            "postgresql://neondb_owner:fake@ep-wrong.c-16.us-east-1.aws.neon.tech/veltrix_football_staging",
            "veltrix_football_staging",
        )


def test_phase3_audit_requires_explicit_staging_enable(monkeypatch):
    monkeypatch.delenv("VELTRIX_ENABLE_STAGING_IMPORT", raising=False)
    with pytest.raises(RuntimeError, match="STAGING_AUDIT_EXPLICIT_ENABLE_REQUIRED"):
        phase3_audit.run_audit("not-a-real-database-url")


def test_phase3_audit_rejects_non_staging_neon_endpoint(monkeypatch):
    monkeypatch.setenv("VELTRIX_ENABLE_STAGING_IMPORT", "YES")
    with pytest.raises(RuntimeError, match="STAGING_DATABASE_HOST_ALLOWLIST_MISMATCH"):
        phase3_audit.run_audit(
            "postgresql://neondb_owner:fake@ep-wrong.c-16.us-east-1.aws.neon.tech/veltrix_football_staging"
        )


def test_phase3_audit_recursively_rejects_secret_metadata():
    assert not phase3_audit._safe_key_scan({"headers": {"Authorization": "Bearer fake"}})
    assert not phase3_audit._safe_key_scan({"request": [{"api-key": "fake"}]})
    assert phase3_audit._safe_key_scan({"headers": {"x-ratelimit-remaining": "12"}})


def test_phase3_import_rejects_modified_expected_host_configuration(monkeypatch):
    monkeypatch.setenv("VELTRIX_ENABLE_STAGING_IMPORT", "YES")
    monkeypatch.setenv("VELTRIX_EXPECTED_DATABASE_HOST", "ep-production.c-16.us-east-1.aws.neon.tech")
    with pytest.raises(RuntimeError, match="STAGING_EXPECTED_HOST_CONFIGURATION_MISMATCH"):
        phase3_import._preflight(
            "postgresql://neondb_owner:fake@ep-production.c-16.us-east-1.aws.neon.tech/veltrix_football_staging",
            "veltrix_football_staging",
        )


def test_phase3_import_window_and_api_key_are_bounded():
    with pytest.raises(ValueError, match="HISTORY_WINDOW_MUST_BE_1_TO_365_DAYS"):
        phase3_import.run_import("unused", "key", days=366)
    with pytest.raises(RuntimeError, match="FIVEDOLLAR_API_KEY_REQUIRED"):
        phase3_import.run_import("unused", "", days=30)


def test_source_approval_requires_complete_evidence():
    with pytest.raises(ValueError, match="APPROVED_SOURCE_REQUIRES_COMPLETE_RIGHTS_EVIDENCE"):
        approval(evidence_sha256=None)


def test_rights_gate_requires_each_use_and_public_attribution():
    rights = approval()
    assert evaluate_source_use(rights, DataUsePurpose.MODEL_TRAINING, at_utc=NOW, commercial=True).allowed
    public = evaluate_source_use(
        rights, DataUsePurpose.PUBLIC_DISPLAY, at_utc=NOW, commercial=True, public_facing=True
    )
    assert public.allowed and public.attribution_text == "Football data by 5DollarFootballAPI"
    raw = evaluate_source_use(rights, DataUsePurpose.RAW_REDISTRIBUTION, at_utc=NOW)
    assert not raw.allowed and raw.reason_code == "RAW_REDISTRIBUTION_PROHIBITED"


def test_rights_expiry_and_provisional_status_fail_closed():
    expired = approval(valid_until_utc=NOW - timedelta(seconds=1))
    decision = evaluate_source_use(expired, DataUsePurpose.HISTORICAL_IMPORT, at_utc=NOW)
    assert not decision.allowed and decision.reason_code == "SOURCE_APPROVAL_EXPIRED"
    provisional = approval(status=ApprovalStatus.PROVISIONAL)
    decision = evaluate_source_use(provisional, DataUsePurpose.HISTORICAL_IMPORT, at_utc=NOW)
    assert not decision.allowed and decision.reason_code == "SOURCE_RIGHTS_NOT_APPROVED"


def test_parse_fixture_page_preserves_raw_hash_and_four_day_availability_proxy():
    raw = provider_page()
    parsed = parse_fixture_page(
        raw, headers={"X-RateLimit-Remaining": "250"},
        retrieved_at_utc=NOW, rights_approval_id="approval-test",
    )
    assert len(parsed.fixtures) == 1
    row = parsed.fixtures[0]
    assert parsed.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert row.provider_fixture_id == "101"
    assert row.home_score == 2 and row.away_score == 1
    assert row.available_at_utc == KICKOFF + timedelta(days=4)
    assert row.availability_basis == AVAILABILITY_BASIS
    assert row.point_in_time_certifiable is False
    assert parsed.quota_remaining == 250


def test_historical_fixture_rejects_payload_hash_not_matching_content():
    with pytest.raises(ValueError, match="HISTORICAL_FIXTURE_PAYLOAD_HASH_MISMATCH"):
        fixture("109", payload_hash="b" * 64)


def test_postgres_writer_binds_parsed_rows_to_exact_raw_response_before_connecting():
    connection_requested = False
    def connection_factory():
        nonlocal connection_requested
        connection_requested = True
        raise AssertionError("raw-response mismatch must fail before connecting")
    response = ProviderResponse(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        endpoint="/leagues/4160026622/fixtures", request_id="raw-bind-1",
        request_params={"league_id": 4160026622}, http_status=200,
        raw_body=provider_page(), response_headers={}, fetched_at_utc=NOW,
    )
    store = PostgresHistoryStore(connection_factory)
    with pytest.raises(ValueError, match="PROVIDER_RESPONSE_FIXTURE_SET_MISMATCH"):
        store.persist_page(response, [fixture("110")], approval())
    assert not connection_requested


def test_postgres_writer_rechecks_mutable_fixture_payload_and_fetch_timestamp():
    row = fixture("101")
    row.payload["goals"]["home"] = 9
    response = ProviderResponse(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        endpoint="/leagues/4160026622/fixtures", request_id="raw-bind-2",
        request_params={"league_id": 4160026622}, http_status=200,
        raw_body=provider_page(), response_headers={}, fetched_at_utc=NOW,
    )
    store = PostgresHistoryStore(lambda: (_ for _ in ()).throw(AssertionError("must not connect")))
    with pytest.raises(ValueError, match="FIXTURE_PAYLOAD_NOT_BOUND_TO_RAW_PROVIDER_RESPONSE"):
        store.persist_page(response, [row], approval())

    valid = fixture("101")
    later_response = ProviderResponse(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        endpoint="/leagues/4160026622/fixtures", request_id="raw-bind-3",
        request_params={"league_id": 4160026622}, http_status=200,
        raw_body=provider_page(), response_headers={}, fetched_at_utc=NOW + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="FIXTURE_RESPONSE_RETRIEVAL_TIME_MISMATCH"):
        store.persist_page(later_response, [valid], approval())


def test_parse_rejects_missing_pagination_metadata():
    raw = provider_page(pagination={"page": 1, "per_page": 100})
    with pytest.raises(FixturePageError, match="PAGINATION_METADATA_INCOMPLETE"):
        parse_fixture_page(raw, headers={}, retrieved_at_utc=NOW, rights_approval_id="approval-test")


def test_parse_rejects_naive_kickoff_and_duplicate_ids():
    row = json.loads(provider_page())["data"][0]
    row["kickoff_utc"] = "2026-10-13T12:00:00"
    raw = provider_page(rows=[row])
    with pytest.raises(FixturePageError, match="FIXTURE_KICKOFF_NOT_TIMEZONE_AWARE"):
        parse_fixture_page(raw, headers={}, retrieved_at_utc=NOW, rights_approval_id="approval-test")
    with pytest.raises(FixturePageError, match="DUPLICATE_FIXTURE_ID_IN_PAGE"):
        parse_fixture_page(provider_page(rows=[json.loads(provider_page())["data"][0]] * 2),
                           headers={}, retrieved_at_utc=NOW, rights_approval_id="approval-test")


def test_finished_fixture_with_invalid_score_is_not_treated_as_settled():
    row = json.loads(provider_page())["data"][0]
    row["goals"] = {"home": True, "away": 1}
    parsed = parse_fixture_page(provider_page(rows=[row]), headers={},
                                retrieved_at_utc=NOW, rights_approval_id="approval-test")
    assert parsed.fixtures[0].status is FixtureStatus.UNKNOWN
    assert parsed.fixtures[0].home_score is None


def test_wildcard_and_out_of_scope_competitions_are_quarantined():
    wildcard = approval(competition_scope="*")
    decision = evaluate_fixture_import(fixture("105"), wildcard, evaluated_at_utc=NOW)
    assert decision.status is ImportOutcomeStatus.QUARANTINED
    assert decision.reason_code == "COMPETITION_OUTSIDE_SOURCE_APPROVAL"

    scoped = approval(competition_scope="3118717965")
    decision = evaluate_fixture_import(fixture("106", competition_id="4160026622"), scoped,
                                       evaluated_at_utc=NOW)
    assert decision.status is ImportOutcomeStatus.QUARANTINED
    assert decision.reason_code == "COMPETITION_OUTSIDE_SOURCE_APPROVAL"


def test_history_batch_imports_only_approved_settled_rows_and_reconciles_manifest():
    rights = approval()
    rows = [fixture("101"), fixture("102")]
    assessed = assess_history_batch(
        rows, rights, evaluated_at_utc=NOW, request_count=3, request_budget=40
    )
    assert assessed.report.status == "COMPLETE"
    assert assessed.report.importable_count == 2
    assert assessed.report.rejected_count == 0
    assert assessed.report.quarantined_count == 0
    reconciliation = reconcile_source_manifest(
        ["101", "102"], assessed.decisions
    )
    assert reconciliation.complete
    assert reconciliation.expected_count == 2
    assert reconciliation.manifest_sha256


def test_duplicate_fixture_ids_are_quarantined_and_reported():
    assessed = assess_history_batch(
        [fixture("101"), fixture("101")], approval(),
        evaluated_at_utc=NOW, request_count=2, request_budget=40,
    )
    assert assessed.report.quarantined_count == 1
    assert assessed.report.duplicate_provider_fixture_ids == ("101",)
    reconciliation = reconcile_source_manifest(["101"], assessed.decisions)
    assert not reconciliation.complete
    assert reconciliation.duplicate_outcome_ids == ("101",)


def test_unsettled_or_unapproved_records_never_enter_import_batch():
    unsettled = fixture("101", status=FixtureStatus.SCHEDULED, home_score=None, away_score=None)
    assessed = assess_history_batch(
        [unsettled], approval(), evaluated_at_utc=NOW, request_count=1, request_budget=40
    )
    assert assessed.report.rejected_count == 1
    no_rights = assess_history_batch(
        [fixture("102")], approval(status=ApprovalStatus.PROVISIONAL),
        evaluated_at_utc=NOW, request_count=1, request_budget=40,
    )
    assert no_rights.report.quarantined_count == 1


def test_batch_request_budget_is_hard_capped():
    with pytest.raises(ValueError, match="HISTORY_REQUEST_BUDGET_INVALID"):
        assess_history_batch([fixture()], approval(), evaluated_at_utc=NOW,
                             request_count=41, request_budget=40)


def test_postgres_writer_refuses_to_persist_secret_response_headers():
    connection_requested = False

    def connection_factory():
        nonlocal connection_requested
        connection_requested = True
        raise AssertionError("must reject secret headers before opening a database connection")
    response = ProviderResponse(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        endpoint="/leagues/1/fixtures", request_id="req-1",
        request_params={"league_id": 1}, http_status=200,
        raw_body=b'{"success":1,"data":[]}',
        response_headers={"Authorization": "Bearer secret"},
        fetched_at_utc=NOW,
    )
    with pytest.raises(ValueError, match="PROVIDER_RESPONSE_SECRET_HEADER_MUST_NOT_BE_STORED"):
        PostgresHistoryStore(connection_factory).persist_page(response, [], approval())
    assert not connection_requested



def test_fixture_cannot_reference_a_different_rights_approval():
    row = fixture("103", approval_id="another-approval")
    decision = evaluate_fixture_import(row, approval(), evaluated_at_utc=NOW)
    assert decision.status is ImportOutcomeStatus.QUARANTINED
    assert decision.reason_code == "RIGHTS_APPROVAL_REFERENCE_MISMATCH"



def _fake_365_day_provider():
    def request(path, key):
        if path == "/status":
            body = {
                "success": 1,
                "data": {
                    "plan": "community",
                    "limits": {"rate_limit": 300, "burst_per_minute": 20},
                    "usage": {"today": 34},
                },
            }
            headers = {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "250"}
        elif path == "/leagues":
            rows = []
            country_by_name = {
                "Brazil Serie A": "Brazil", "Brazil Serie B": "Brazil",
                "England Premier League": "England", "France Ligue 1": "France",
                "Germany Bundesliga I": "Germany", "Italy Serie A": "Italy",
                "Spain La Liga": "Spain",
            }
            for league_id, name in history_probe.EXPECTED_COMPETITIONS.items():
                rows.append({"id": int(league_id), "name": name, "country": country_by_name[name]})
            body = {"success": 1, "data": rows, "pagination": {"has_more": False}}
            headers = {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "249"}
        else:
            from urllib.parse import urlparse
            from datetime import datetime, timezone
            league_id = path.split("/")[2]
            name = history_probe.EXPECTED_COMPETITIONS[league_id]
            kickoff = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
            row = {
                "id": 100000 + int(league_id) % 100000,
                "league": {"id": int(league_id), "name": name, "season": "2025/2026"},
                "teams": {
                    "home": {"id": 200000 + int(league_id) % 100000, "name": "Home " + name},
                    "away": {"id": 300000 + int(league_id) % 100000, "name": "Away " + name},
                },
                "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
                "kickoff_ts": int(kickoff.timestamp()),
                "status": "finished",
                "goals": {"home": 2, "away": 1},
            }
            body = {"success": 1, "data": [row],
                    "pagination": {"page": 1, "per_page": 100, "has_more": False}}
            headers = {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "248"}
        return 200, json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), headers
    return request


def test_365_day_history_probe_qualifies_all_seven_allowlisted_competitions():
    report = history_probe.run_probe(
        "not-a-real-key",
        now=NOW,
        request_fn=_fake_365_day_provider(),
        sleep=lambda _: None,
    )
    history_probe.validate_report(report)
    assert report["status"] == "QUALIFIED"
    assert report["fixture_count"] == 7
    assert report["importable_count"] == 7
    assert report["pagination_complete"] is True
    assert report["request_count"] == 9
    assert report["account"]["country_pack_country_inferred"] == ["Brazil"]
    assert report["side_effects"]["database_writes"] == 0
    assert "not-a-real-key" not in str(report)


def test_365_day_probe_fails_closed_when_quota_is_insufficient():
    request = _fake_365_day_provider()
    def low_quota(path, key):
        status, raw, headers = request(path, key)
        if path == "/status":
            headers["X-RateLimit-Remaining"] = "10"
        return status, raw, headers
    report = history_probe.run_probe(
        "not-a-real-key", now=NOW, request_fn=low_quota, sleep=lambda _: None
    )
    assert report["status"] == "NOT_QUALIFIED"
    assert report["failure_reason"] == "INSUFFICIENT_REMAINING_QUOTA_FOR_BOUNDED_PROBE"
    assert report["request_count"] == 1
    assert report["fixture_count"] == 0


def test_365_day_probe_stops_at_request_budget_without_claiming_complete_pagination(monkeypatch):
    monkeypatch.setattr(history_probe, "REQUEST_BUDGET", 3)
    report = history_probe.run_probe(
        "not-a-real-key",
        now=NOW,
        request_fn=_fake_365_day_provider(),
        sleep=lambda _: None,
    )
    assert report["status"] == "NOT_QUALIFIED"
    assert report["failure_reason"] == "REQUEST_BUDGET_EXHAUSTED"
    assert report["request_count"] == 3
    assert report["pagination_complete"] is False



def test_postgres_writer_refuses_nested_secret_request_parameters():
    connection_requested = False

    def connection_factory():
        nonlocal connection_requested
        connection_requested = True
        raise AssertionError("must reject nested secret parameters before connecting")

    response = ProviderResponse(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        endpoint="/leagues/1/fixtures", request_id="req-secret",
        request_params={"filters": {"api_key": "must-never-persist"}},
        http_status=200, raw_body=b'{"success":1,"data":[]}',
        response_headers={"X-RateLimit-Remaining": "200"},
        fetched_at_utc=NOW,
    )
    with pytest.raises(ValueError, match="PROVIDER_REQUEST_SECRET_PARAMETER_MUST_NOT_BE_STORED"):
        PostgresHistoryStore(connection_factory).persist_page(response, [], approval())
    assert not connection_requested



def test_postgres_history_writer_is_read_only_by_default():
    connection_requested = False

    def connection_factory():
        nonlocal connection_requested
        connection_requested = True
        raise AssertionError("default writer must not connect")

    with pytest.raises(RuntimeError, match="HISTORY_DATABASE_WRITES_DISABLED"):
        PostgresHistoryStore(connection_factory).persist_source_approval(approval())
    assert not connection_requested


def test_postgres_history_writer_requires_explicit_expected_database():
    with pytest.raises(ValueError, match="EXPECTED_HISTORY_WRITE_DATABASE_REQUIRED"):
        PostgresHistoryStore(lambda: None, allow_writes=True)



def test_postgres_history_writer_hard_blocks_production_database_name():
    with pytest.raises(RuntimeError, match="PRODUCTION_DATABASE_WRITES_DISABLED"):
        PostgresHistoryStore(lambda: None, allow_writes=True, expected_database="veltrix-football")



def test_finished_fixture_availability_cannot_precede_kickoff():
    with pytest.raises(ValueError, match="FIXTURE_RESULT_AVAILABILITY_PRECEDES_KICKOFF"):
        fixture("104").__class__(
            **{
                field: getattr(fixture("104"), field)
                for field in fixture("104").__dataclass_fields__
                if field != "available_at_utc"
            },
            available_at_utc=KICKOFF - timedelta(seconds=1),
        )
