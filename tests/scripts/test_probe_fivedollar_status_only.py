from datetime import datetime, timezone

from scripts.probe_fivedollar_status_only import ProbeError, build_evidence


def fake_request(body, status=200, headers=None):
    def call(api_key):
        assert api_key == "test-key"
        return status, body, headers or {}
    return call


def test_ultra_is_confirmed_from_status_plan_only():
    body = b'{"success":true,"data":{"plan":"Ultra","limits":{"rate_limit":300}}}'
    result = build_evidence(
        "test-key",
        request_fn=fake_request(body, headers={"x-ratelimit-remaining": "299"}),
        now_fn=lambda: datetime(2026, 11, 15, tzinfo=timezone.utc),
    )
    assert result["ultra_confirmed"] is True
    assert result["entitlement_decision"] == "ULTRA_CONFIRMED_STATUS_ONLY"
    assert result["request_count"] == 1
    assert result["provider_calls_performed"] == ["/v1/status"]
    assert result["side_effects"]["odds_history_requests"] == 0


def test_community_does_not_confirm_ultra():
    body = b'{"success":true,"data":{"plan":"Community"}}'
    result = build_evidence("test-key", request_fn=fake_request(body))
    assert result["ultra_confirmed"] is False
    assert result["plan"] == "Community"


def test_missing_plan_fails_closed():
    body = b'{"success":true,"data":{"limits":{"rate_limit":300}}}'
    result = build_evidence("test-key", request_fn=fake_request(body))
    assert result["ultra_confirmed"] is False
    assert result["plan"] is None


def test_invalid_schema_does_not_confirm_ultra():
    result = build_evidence("test-key", request_fn=fake_request(b'{"success":false,"data":{"plan":"Ultra"}}'))
    assert result["response_schema_valid"] is False
    assert result["ultra_confirmed"] is False


def test_missing_secret_makes_no_request():
    def must_not_call(_):
        raise AssertionError("provider must not be called without secret")
    try:
        build_evidence("", request_fn=must_not_call)
    except ProbeError as exc:
        assert str(exc) == "MISSING_SECRET"
    else:
        raise AssertionError("expected missing-secret failure")


def test_raw_body_hash_is_exact():
    body = b'{ "success": true, "data": {"plan":"Ultra"} }'
    result = build_evidence("test-key", request_fn=fake_request(body))
    import hashlib
    assert result["raw_response_sha256"] == hashlib.sha256(body).hexdigest()
