import hashlib
import json
import unittest
from unittest.mock import patch

from app.provider_adapters import (
    ProviderAPIError, TheOddsAPIClient, _json_request,
)


class FakeResponse:
    status = 200
    headers = {
        "x-requests-remaining": "90",
        "x-requests-used": "10",
        "x-requests-last": "3",
    }

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.raw


class TheOddsApiRawEvidenceClientTests(unittest.TestCase):
    def test_json_request_can_return_exact_response_bytes_without_changing_default_shape(self):
        raw = b'{"events":[{"id":"event-1"}]}'
        with patch("app.provider_adapters.urlopen", return_value=FakeResponse(raw)):
            status, headers, payload = _json_request("https://example.test/data", retries=0)
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"events": [{"id": "event-1"}]})
        with patch("app.provider_adapters.urlopen", return_value=FakeResponse(raw)):
            status, headers, payload, raw_bytes = _json_request(
                "https://example.test/data", retries=0, include_raw=True,
            )
        self.assertEqual(raw_bytes, raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw_bytes).hexdigest())

    @patch("app.provider_adapters._json_request")
    def test_sport_odds_method_returns_exact_payload_digest_and_quota(self, request):
        raw = b'[{"id":"event-1"}]'
        request.return_value = (
            200,
            {
                "x-requests-remaining": "88",
                "x-requests-used": "12",
                "x-requests-last": "4",
            },
            [{"id": "event-1"}],
            raw,
        )
        client = TheOddsAPIClient(api_key="test-key")
        result = client.odds_for_sport_with_raw("soccer_epl")
        self.assertEqual(result["payload"], [{"id": "event-1"}])
        self.assertEqual(result["raw_payload_bytes"], raw)
        self.assertEqual(result["raw_payload_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["quota"]["remaining"], "88")
        self.assertTrue(result["retrieved_at"].endswith("+00:00"))
        self.assertEqual(request.call_args.kwargs["include_raw"], True)
        self.assertEqual(request.call_args.kwargs["retries"], 0)

    @patch("app.provider_adapters._json_request")
    def test_event_btts_method_normalizes_single_event_object(self, request):
        raw = b'{"id":"event-1","bookmakers":[]}'
        request.return_value = (200, {}, {"id": "event-1", "bookmakers": []}, raw)
        result = TheOddsAPIClient(api_key="test-key").event_btts_with_raw(
            "soccer_epl", "event-1",
        )
        self.assertEqual(result["payload"], [{"id": "event-1", "bookmakers": []}])

    def test_raw_capture_requires_api_key_and_bytes(self):
        with self.assertRaisesRegex(ProviderAPIError, "KEY is missing"):
            TheOddsAPIClient(api_key="").odds_for_sport_with_raw("soccer_epl")
        with patch("app.provider_adapters._json_request", return_value=(200, {}, [], "not-bytes")):
            with self.assertRaisesRegex(ProviderAPIError, "not bytes"):
                TheOddsAPIClient(api_key="test-key").odds_for_sport_with_raw("soccer_epl")


if __name__ == "__main__":
    unittest.main()
