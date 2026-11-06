from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

import pytest

from veltrix_v2.ingestion.ports import ProviderRequestSpec
from veltrix_v2.ingestion.providers.five_dollar import FiveDollarFixtureAdapter
from veltrix_v2.ingestion.providers.errors import ProviderResponseError
from veltrix_v2.ingestion.providers.transport import HttpResponse


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self, response=None):
        self.response = response or HttpResponse(
            200, {},
            b'{"success":1,"data":[],"pagination":{"page":1,"per_page":100,"has_more":false}}',
        )
        self.calls = []

    def get(self, url, *, headers, timeout_seconds):
        self.calls.append((url, dict(headers), timeout_seconds))
        return self.response


def request(endpoint="fixtures", parameters=None, competitions=()):
    return ProviderRequestSpec(
        request_id="req-1", provider="5DollarFootballAPI", endpoint=endpoint,
        data_class="fixtures", quota_scope="hourly", quota_units=1,
        competition_ids=competitions, history_start_date=None,
        idempotency_key="req-1", parameters=parameters or {
            "start_time": 1793923200, "end_time": 1794009600,
            "page": 1, "per_page": 100,
        },
    )


def test_adapter_is_disabled_by_default_and_never_calls_transport():
    transport = FakeTransport()
    adapter = FiveDollarFixtureAdapter(api_key="secret", transport=transport)
    with pytest.raises(ProviderResponseError, match="TRANSPORT_DISABLED"):
        adapter.fetch(request())
    assert transport.calls == []


def test_adapter_requires_credential_only_when_enabled():
    adapter = FiveDollarFixtureAdapter(transport=FakeTransport(), enabled=True)
    with pytest.raises(ProviderResponseError, match="CREDENTIAL_MISSING"):
        adapter.fetch(request())


def test_adapter_builds_fixed_host_and_bearer_auth():
    transport = FakeTransport()
    adapter = FiveDollarFixtureAdapter(
        api_key="test-secret", transport=transport, enabled=True,
    )
    result = adapter.fetch(request())
    url, headers, _ = transport.calls[0]
    assert urlparse(url).hostname == "api.5dollarfootballapi.com"
    assert headers["Authorization"] == "Bearer test-secret"
    assert "test-secret" not in url
    assert result.request_id == "req-1"


def test_adapter_rejects_fixture_window_longer_than_24_hours():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(parameters={"start_time": 100, "end_time": 100 + 86401})
    with pytest.raises(ProviderResponseError, match="24_HOURS"):
        adapter.fetch(req)


def test_adapter_rejects_unallowlisted_endpoint():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(endpoint="arbitrary_url")
    with pytest.raises(ProviderResponseError, match="NOT_ALLOWLISTED"):
        adapter.fetch(req)


def test_adapter_rejects_league_outside_request_scope():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(
        endpoint="league_fixtures",
        parameters={"league_id": 99, "page": 1, "per_page": 100},
        competitions=("55",),
    )
    with pytest.raises(ProviderResponseError, match="OUTSIDE_REQUEST_SCOPE"):
        adapter.fetch(req)


def test_adapter_rejects_invalid_page_size():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(parameters={"start_time": 100, "end_time": 200, "per_page": 101})
    with pytest.raises(ProviderResponseError, match="PER_PAGE_OUT_OF_RANGE"):
        adapter.fetch(req)


def test_adapter_classifies_provider_403_without_retry():
    transport = FakeTransport(HttpResponse(403, {}, b'{"success":0}'))
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=transport, enabled=True)
    with pytest.raises(ProviderResponseError) as caught:
        adapter.fetch(request())
    assert caught.value.retryable is False



def test_adapter_rejects_path_injection_in_provider_ids():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(
        endpoint="league_fixtures",
        parameters={"league_id": "../private", "page": 1, "per_page": 100},
        competitions=(),
    )
    with pytest.raises(ProviderResponseError, match="LEAGUE_ID_REQUIRED"):
        adapter.fetch(req)


def test_adapter_rejects_non_numeric_pagination_values():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(parameters={"start_time": 100, "end_time": 200, "page": "not-a-page"})
    with pytest.raises(ProviderResponseError, match="PAGE_INVALID"):
        adapter.fetch(req)


def test_adapter_rejects_reversed_league_history_window():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(
        endpoint="league_fixtures",
        parameters={"league_id": 55, "start_time": 200, "end_time": 100},
        competitions=("55",),
    )
    with pytest.raises(ProviderResponseError, match="WINDOW_INVALID"):
        adapter.fetch(req)



def test_fixture_endpoint_accepts_only_in_scope_league_filter():
    transport = FakeTransport()
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=transport, enabled=True)
    req = request(parameters={
        "start_time": 100, "end_time": 200, "league": 55, "page": 1,
        "per_page": 100,
    }, competitions=("55",))
    adapter.fetch(req)
    assert "league=55" in transport.calls[0][0]
    assert "esports=false" in transport.calls[0][0]


def test_fixture_endpoint_rejects_esports_for_real_football_source():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(parameters={
        "start_time": 100, "end_time": 200, "esports": "true",
    })
    with pytest.raises(ProviderResponseError, match="ESPORTS_DISABLED"):
        adapter.fetch(req)


def test_league_endpoint_requires_season_or_bounded_window():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(
        endpoint="league_fixtures",
        parameters={"league_id": 55, "page": 1, "per_page": 100},
        competitions=("55",),
    )
    with pytest.raises(ProviderResponseError, match="SEASON_OR_WINDOW"):
        adapter.fetch(req)


def test_team_endpoint_requires_explicit_bounded_window():
    adapter = FiveDollarFixtureAdapter(api_key="k", transport=FakeTransport(), enabled=True)
    req = request(endpoint="team_fixtures", parameters={"team_id": 11, "page": 1})
    with pytest.raises(ProviderResponseError, match="WINDOW_REQUIRED"):
        adapter.fetch(req)
