from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts import phase4_odds_account_probe as probe
from veltrix_v2.data.contracts import ProviderResponse
from veltrix_v2.data.postgres import PostgresHistoryStore
from veltrix_v2.providers.odds_api_v4.transport_contract import (
    RawTransportResponse, validate_transport_response,
)


EXPECTED = (
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
)


class _Headers:
    def __init__(self, rows):
        self._rows = rows

    def items(self):
        return list(self._rows)


class _Response:
    status = 200

    def __init__(self, body, headers):
        self._body = body
        self.headers = _Headers(headers)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=-1):
        return self._body[:limit]


class _Opener:
    def __init__(self, response):
        self.response = response
        self.request = None

    def open(self, request, timeout):
        self.request = request
        assert timeout == 15
        return self.response


def test_fetch_sports_uses_header_auth_and_parses_quota(monkeypatch):
    body = json.dumps([{"key": key, "title": key, "active": True} for key in EXPECTED]).encode()
    opener = _Opener(_Response(body, [
        ("x-requests-used", "12"),
        ("x-requests-remaining", "988"),
        ("x-requests-last", "0"),
    ]))
    monkeypatch.setattr(probe, "build_opener", lambda handler: opener)

    requested, retrieved, raw, headers, envelope, keys = probe._fetch_sports("test-secret")

    assert requested.tzinfo is not None
    assert retrieved.tzinfo is not None
    assert raw == body
    assert keys == tuple(sorted(EXPECTED))
    assert envelope.quota_evidence.complete
    assert envelope.quota_evidence.requests_last == 0
    assert opener.request.full_url == probe.API_URL + "?all=true"
    assert opener.request.get_header("X-api-key") == "test-secret"
    assert "apiKey" not in opener.request.full_url
    assert headers["x-requests-remaining"] == "988"


def test_fetch_sports_rejects_duplicate_sport_keys(monkeypatch):
    body = json.dumps([{"key": "soccer_epl"}, {"key": "soccer_epl"}]).encode()
    opener = _Opener(_Response(body, [
        ("x-requests-used", "1"),
        ("x-requests-remaining", "99"),
        ("x-requests-last", "0"),
    ]))
    monkeypatch.setattr(probe, "build_opener", lambda handler: opener)
    with pytest.raises(ValueError, match="ODDS_API_SPORT_KEY_EMPTY_OR_DUPLICATED"):
        probe._fetch_sports("test-secret")


def test_fetch_sports_rejects_incomplete_quota_headers(monkeypatch):
    body = json.dumps([{"key": "soccer_epl"}]).encode()
    opener = _Opener(_Response(body, [
        ("x-requests-used", "1"),
        ("x-requests-remaining", "99"),
    ]))
    monkeypatch.setattr(probe, "build_opener", lambda handler: opener)
    *_, envelope, keys = probe._fetch_sports("test-secret")
    assert keys == ("soccer_epl",)
    assert not envelope.quota_evidence.complete


class _FakeCursor:
    def __init__(self, raw_body):
        self.raw_body = raw_body
        self.rowcount = 1
        self.last_query = ""
        self.last_params = None
        self.queries = []

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params
        self.queries.append((query, params))

    def fetchone(self):
        q = " ".join(self.last_query.lower().split())
        if q.startswith("select id,raw_body,http_status"):
            return (101, self.raw_body, 200)
        if "metadata->>'provider_account_ref'" in q:
            return ("veltrix-primary-the-odds-api",)
        if "returning id" in q:
            return (202,)
        return None


class _FakeConnection:
    def __init__(self, raw_body):
        self.cursor_value = _FakeCursor(raw_body)
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    ("observed", "quota_values", "expected_status"),
    [
        (EXPECTED, [
            ("x-requests-used", "12"),
            ("x-requests-remaining", "988"),
            ("x-requests-last", "0"),
        ], "ACTIVE"),
        (EXPECTED, [
            ("x-requests-used", "12"),
            ("x-requests-remaining", "988"),
            ("x-requests-last", "1"),
        ], "UNVERIFIED"),
        (("soccer_epl",), [
            ("x-requests-used", "12"),
            ("x-requests-remaining", "988"),
            ("x-requests-last", "0"),
        ], "UNVERIFIED"),
        (EXPECTED, [
            ("x-requests-used", "12"),
            ("x-requests-remaining", "988"),
        ], "UNVERIFIED"),
    ],
)
def test_persist_probe_updates_only_verified_scope(
    observed, quota_values, expected_status
):
    body = json.dumps([{"key": key} for key in observed]).encode()
    retrieved = datetime.now(timezone.utc)
    decision = validate_transport_response(RawTransportResponse(
        status_code=200,
        headers=dict(quota_values),
        body=body,
        retrieved_at=retrieved,
    ))
    assert decision.accepted and decision.envelope is not None
    response = ProviderResponse(
        provider="the_odds_api",
        source_id="odds_api_v4",
        endpoint="/v4/sports/",
        request_id="test-run-sports-all",
        request_params={"all": "true"},
        http_status=200,
        raw_body=body,
        response_headers=dict(quota_values),
        fetched_at_utc=retrieved,
    )
    connection = _FakeConnection(body)
    store = PostgresHistoryStore(lambda: connection, allow_writes=True,
                                 expected_database="veltrix_football_staging")
    store._connect_for_write = lambda: connection

    response_id, entitlement_id = store.persist_provider_account_probe(
        response, decision.envelope,
        provider_account_ref="veltrix-primary-the-odds-api",
        expected_competition_keys=EXPECTED,
        observed_competition_keys=observed,
    )

    assert (response_id, entitlement_id) == (101, 202)
    assert connection.committed and not connection.rolled_back and connection.closed
    update = next(params for query, params in connection.cursor_value.queries
                  if "UPDATE provider_accounts" in query)
    assert update[0] == expected_status
    assert update[1] == retrieved
    assert update[2] is not None
    assert not any("provider_credit_budget_snapshots" in query
                   for query, _ in connection.cursor_value.queries)


def test_execute_requires_staging_persistence_before_provider_access(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["phase4_odds_account_probe", "--execute"])
    with pytest.raises(RuntimeError, match="STAGING_PERSISTENCE_REQUIRED_FOR_ODDS_API_PROBE"):
        probe.main()
