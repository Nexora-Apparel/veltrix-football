from urllib.parse import parse_qs, urlparse

import pytest

from veltrix_v2.ingestion.ports import ProviderRequestSpec
from veltrix_v2.ingestion.providers.errors import ProviderResponseError
from veltrix_v2.ingestion.providers.the_odds_api import TheOddsApiAdapter
from veltrix_v2.ingestion.providers.transport import HttpResponse


class FakeTransport:
    def __init__(self, response=None):
        self.response = response or HttpResponse(
            200, {"x-requests-last": "2", "x-requests-remaining": "498"},
            b'[{"id":"event-1","sport_key":"soccer_england_premier_league","home_team":"A","away_team":"B","bookmakers":[]}]',
        )
        self.calls = []

    def get(self, url, *, headers, timeout_seconds):
        self.calls.append((url, dict(headers), timeout_seconds))
        return self.response


def request(endpoint="sport_odds", params=None, units=2):
    values = params or {
        "sport_key": "soccer_england_premier_league",
        "regions": "uk", "markets": "h2h,totals",
    }
    return ProviderRequestSpec(
        request_id="odds-1", provider="The Odds API", endpoint=endpoint,
        data_class="odds", quota_scope="monthly_credits", quota_units=units,
        competition_ids=("soccer_england_premier_league",),
        history_start_date=None, idempotency_key="odds-1", parameters=values,
    )


def test_adapter_is_disabled_by_default():
    transport = FakeTransport()
    adapter = TheOddsApiAdapter(api_key="secret", transport=transport)
    with pytest.raises(ProviderResponseError, match="TRANSPORT_DISABLED"):
        adapter.fetch(request())
    assert transport.calls == []


def test_adapter_builds_api_key_query_without_logging_or_header_leak():
    transport = FakeTransport()
    adapter = TheOddsApiAdapter(api_key="private-key", transport=transport, enabled=True)
    adapter.fetch(request())
    url, headers, _ = transport.calls[0]
    assert urlparse(url).hostname == "api.the-odds-api.com"
    assert parse_qs(urlparse(url).query)["apiKey"] == ["private-key"]
    assert "apiKey" not in headers
    assert headers["Accept"] == "application/json"


def test_historical_credit_reservation_is_exactly_ten_per_region_market():
    transport = FakeTransport(HttpResponse(
        200, {"x-requests-last": "40"},
        b"[]",
    ))
    adapter = TheOddsApiAdapter(api_key="k", transport=transport, enabled=True)
    req = request(
        endpoint="historical_sport_odds",
        params={
            "sport_key": "soccer_england_premier_league",
            "regions": "uk,eu", "markets": "h2h,totals",
            "date": "2026-11-06T08:00:00Z",
        },
        units=40,
    )
    assert adapter.fetch(req).quota_units_consumed == 40


def test_historical_request_is_blocked_when_credit_reservation_is_low():
    adapter = TheOddsApiAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(
        endpoint="historical_sport_odds",
        params={
            "sport_key": "soccer_england_premier_league",
            "regions": "uk,eu", "markets": "h2h,totals",
            "date": "2026-11-06T08:00:00Z",
        },
        units=20,
    )
    with pytest.raises(ProviderResponseError, match="RESERVATION_MISMATCH"):
        adapter.fetch(req)


def test_live_odds_requires_observed_quota_cost_header():
    transport = FakeTransport(HttpResponse(200, {}, b"[]"))
    adapter = TheOddsApiAdapter(api_key="k", transport=transport, enabled=True)
    with pytest.raises(ProviderResponseError, match="COST_UNOBSERVED"):
        adapter.fetch(request())


def test_live_odds_blocks_cost_above_reserved_units():
    transport = FakeTransport(HttpResponse(200, {"x-requests-last": "3"}, b"[]"))
    adapter = TheOddsApiAdapter(api_key="k", transport=transport, enabled=True)
    with pytest.raises(ProviderResponseError, match="EXCEEDED_RESERVATION"):
        adapter.fetch(request(units=2))


def test_adapter_rejects_unapproved_region():
    adapter = TheOddsApiAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(params={
        "sport_key": "soccer_england_premier_league",
        "regions": "uk,xx", "markets": "h2h",
    }, units=1)
    with pytest.raises(ProviderResponseError, match="REGION_NOT_ALLOWLISTED"):
        adapter.fetch(req)


def test_adapter_rejects_invalid_sport_key():
    adapter = TheOddsApiAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(params={"sport_key": "../private", "regions": "uk", "markets": "h2h"}, units=1)
    with pytest.raises(ProviderResponseError, match="SPORT_KEY_INVALID"):
        adapter.fetch(req)
