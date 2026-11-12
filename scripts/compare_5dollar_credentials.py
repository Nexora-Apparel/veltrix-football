"""Read-only comparison of standard and Community 5DollarFootballAPI credentials.

Both credentials are tested independently against the existing fixture endpoint using
the repository's established Bearer authentication. No fixture payloads or secrets are
printed, and this script does not write to the database or call prediction code.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://api.5dollarfootballapi.com/v1/fixtures"
TIMEOUT = 20


def safe_error(exc: HTTPError) -> str:
    parts = [f"HTTP_{exc.code}"]
    headers = exc.headers or {}
    for source, label in (
        ("Retry-After", "retry_after"),
        ("X-RateLimit-Limit", "limit"),
        ("X-RateLimit-Remaining", "remaining"),
        ("X-RateLimit-Reset", "reset"),
    ):
        value = headers.get(source)
        if value is not None and str(value).strip():
            parts.append(f"{label}={str(value).strip()[:40]}")
    try:
        body = exc.read(1024).decode("utf-8", errors="replace")
        parsed = json.loads(body) if body else {}
        reason = (parsed.get("error") or parsed.get("message")) if isinstance(parsed, dict) else None
        if reason:
            clean = re.sub(r"[^A-Za-z0-9 _-]", "", str(reason))[:80]
            if clean:
                parts.append(f"reason={clean}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return "; ".join(parts)


def probe(label: str, env_name: str) -> dict[str, object]:
    key = os.getenv(env_name, "").strip()
    if not key:
        print(f"{label}: MISSING_SECRET ({env_name})")
        return {"status": "MISSING_SECRET"}

    url = ENDPOINT + "?" + urlencode({"status": "scheduled", "per_page": 1})
    request = Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = response.headers
            if not isinstance(payload, dict) or payload.get("success") != 1:
                print(f"{label}: HTTP_{response.status}; UNEXPECTED_RESPONSE_SCHEMA")
                return {"status": "UNEXPECTED_SCHEMA", "http": response.status}
            data = payload.get("data")
            if not isinstance(data, list):
                print(f"{label}: HTTP_{response.status}; AUTHENTICATED_BUT_DATA_SCHEMA_UNEXPECTED")
                return {"status": "UNEXPECTED_DATA_SCHEMA", "http": response.status}
            quota = {
                "limit": headers.get("X-RateLimit-Limit", "not supplied"),
                "remaining": headers.get("X-RateLimit-Remaining", "not supplied"),
                "reset": headers.get("X-RateLimit-Reset", "not supplied"),
            }
            print(
                f"{label}: AUTH_OK; HTTP_{response.status}; "
                f"sample_rows={len(data)}; quota_limit={quota['limit']}; "
                f"quota_remaining={quota['remaining']}; quota_reset={quota['reset']}"
            )
            return {"status": "AUTH_OK", "http": response.status, "quota": quota, "sample_rows": len(data)}
    except HTTPError as exc:
        detail = safe_error(exc)
        print(f"{label}: {detail}")
        return {"status": "HTTP_ERROR", "http": exc.code, "detail": detail}
    except (URLError, TimeoutError, OSError):
        print(f"{label}: NETWORK_ERROR")
        return {"status": "NETWORK_ERROR"}
    except (UnicodeDecodeError, json.JSONDecodeError):
        print(f"{label}: INVALID_JSON")
        return {"status": "INVALID_JSON"}


def main() -> int:
    print("5DollarFootballAPI credential comparison (one bounded read-only request per key)")
    standard = probe("STANDARD_KEY", "FIVEDOLLARFOOTBALL_API_KEY")
    community = probe("COMMUNITY_KEY", "FIVEDOLLARFOOTBALL_COMMUNITY_API_KEY")

    if standard.get("status") == "AUTH_OK" and community.get("status") == "AUTH_OK":
        if standard.get("quota") == community.get("quota"):
            print("COMPARISON: BOTH_AUTHENTICATED; OBSERVED_QUOTA_HEADERS_MATCH")
        else:
            print("COMPARISON: BOTH_AUTHENTICATED; OBSERVED_QUOTA_HEADERS_DIFFER")
        print("NOTE: Matching endpoint access and headers do not prove identical plan entitlements.")
        return 0
    if standard.get("status") == "AUTH_OK" or community.get("status") == "AUTH_OK":
        print("COMPARISON: PARTIAL_ACCESS; inspect the per-key status above.")
        return 1
    print("COMPARISON: NO_CREDENTIAL_CONFIRMED; inspect the per-key status above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
