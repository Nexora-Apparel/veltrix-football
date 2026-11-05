from app import research_evidence as research


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, body):
        self.body = body
        self.calls = []

    def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        return FakeResponse(self.body)


def _fixture(**overrides):
    fixture = {
        "fixture_id": "provider-123",
        "home_team": "Alpha FC U19",
        "away_team": "Beta FC U19",
        "competition": "National U19 League",
        "squad_category": "U19",
        "kickoff": "2026-11-06T15:00:00Z",
        "status": "INSUFFICIENT_HISTORY",
    }
    fixture.update(overrides)
    return fixture


def test_search_without_credential_is_disabled_and_does_not_call_provider(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    session = FakeSession({"results": []})
    result = research.search_fixture_evidence(_fixture(), api_key="", session=session)

    assert result["status"] == "DISABLED_MISSING_CREDENTIAL"
    assert result["sources"] == []
    assert result["model_eligible"] is False
    assert session.calls == []


def test_search_keeps_only_public_https_sources_and_quarantines_them():
    session = FakeSession({"results": [
        {
            "url": "https://www.uefa.com/example",
            "title": "Alpha FC U19 results",
            "content": "Alpha FC U19 won 2-1.",
            "published_date": "2026-11-01",
            "score": 0.91,
        },
        {"url": "https://www.uefa.com/example", "title": "Duplicate"},
        {"url": "http://example.com/insecure", "title": "Insecure"},
        {"url": "https://127.0.0.1/private", "title": "Private IP"},
        {"url": "https://user:pass@example.com/private", "title": "Credentials"},
    ]})

    result = research.search_fixture_evidence(_fixture(), api_key="test-key", session=session)

    assert result["status"] == "SOURCES_FOUND"
    assert result["source_count"] == 1
    source = result["sources"][0]
    assert source["domain"] == "www.uefa.com"
    assert source["verification_status"] == "SOURCE_CANDIDATE_UNVERIFIED"
    assert source["model_eligible"] is False
    assert result["fixture_identity"]["provider_fixture_id"] == "provider-123"
    assert session.calls[0][1]["query"].find("U19") >= 0
    assert session.calls[0][1]["include_answer"] is False


def test_research_batch_only_queries_low_history_fixtures():
    session = FakeSession({"results": []})
    fixtures = [
        _fixture(status="INSUFFICIENT_HISTORY"),
        _fixture(status="UNSUPPORTED_COMPETITION", fixture_id="unsupported"),
        _fixture(status="LOW_HISTORY_FORECAST", fixture_id="sparse"),
    ]

    result = research.research_missing_fixtures(fixtures, api_key="test-key", max_fixtures=1, session=session)

    assert result["fixtures_searched"] == 1
    assert result["model_eligible_facts"] == 0
    assert result["results"][0]["fixture_identity"]["provider_fixture_id"] == "provider-123"
    assert result["safety"].startswith("No search result")


def test_provider_failure_returns_safe_status_without_leaking_credentials():
    class BrokenSession:
        def post(self, *args, **kwargs):
            raise research.requests.Timeout("timeout")

    result = research.search_fixture_evidence(_fixture(), api_key="secret", session=BrokenSession())

    assert result["status"] == "PROVIDER_UNAVAILABLE"
    assert "secret" not in str(result)
    assert result["model_eligible"] is False


def test_report_annotation_records_disabled_research_without_changing_predictions(tmp_path, monkeypatch):
    import json

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    source = tmp_path / "daily_predictions.json"
    original = {
        "as_of_date": "2026-11-06",
        "predictions": [_fixture(), _fixture(status="UNSUPPORTED_COMPETITION")],
    }
    source.write_text(json.dumps(original), encoding="utf-8")

    result = research.annotate_report_file(str(source))

    saved = json.loads(source.read_text(encoding="utf-8"))
    assert result["status"] == "DISABLED_MISSING_CREDENTIAL"
    assert result["fixtures_searched"] == 1
    assert saved["predictions"] == original["predictions"]
    assert saved["research_evidence"]["model_eligible_facts"] == 0
