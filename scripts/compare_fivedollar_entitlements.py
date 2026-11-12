#!/usr/bin/env python3
"""Bounded, read-only comparison of Standard and Community 5Dollar credentials.

Only endpoints already used by the repository are probed. No response bodies or
credential material are written to logs. Unknown statistics endpoints are not guessed.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.5dollarfootballapi.com/v1"
MAX_REQUESTS_PER_KEY = 8
MAX_PAGES = 3
WINDOW_DAYS = 90


class Probe:
    def __init__(self, alias: str, key: str):
        self.alias = alias
        self.key = key
        self.requests = 0
        self.endpoint_counts = {}
        self.quota = {"limit": None, "remaining": None, "reset": None}
        self.results = {}

    def get(self, endpoint: str, params=None):
        if self.requests >= MAX_REQUESTS_PER_KEY:
            raise RuntimeError("request_budget_exhausted")
        self.requests += 1
        self.endpoint_counts[endpoint] = self.endpoint_counts.get(endpoint, 0) + 1
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{BASE}/{endpoint.lstrip('/')}" + (f"?{query}" if query else "")
        request = Request(url, headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {self.key}",
            "User-Agent": "VeltrixFootball-EntitlementComparison/1.0",
        })
        try:
            with urlopen(request, timeout=15) as response:
                headers = response.headers
                payload = json.loads(response.read().decode("utf-8"))
                status = response.status
        except HTTPError as exc:
            headers = exc.headers or {}
            self._quota(headers)
            return {"http_status": exc.code, "access": "DENIED" if exc.code in (401, 403) else "ERROR"}
        except (URLError, TimeoutError, OSError):
            return {"http_status": None, "access": "NETWORK_ERROR"}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"http_status": status, "access": "INVALID_JSON"}
        self._quota(headers)
        if status != 200 or not isinstance(payload, dict) or payload.get("success") != 1:
            return {"http_status": status, "access": "UNSUCCESSFUL_RESPONSE"}
        return {"http_status": status, "access": "OK", "payload": payload}

    def _quota(self, headers):
        for field, header in (("limit", "X-RateLimit-Limit"),
                              ("remaining", "X-RateLimit-Remaining"),
                              ("reset", "X-RateLimit-Reset")):
            value = headers.get(header)
            if value is not None:
                self.quota[field] = str(value)

    def run(self):
        catalogue = self.get("leagues", {"page": 1, "per_page": 100})
        cat = catalogue["access"]
        competitions = []
        catalogue_complete = False
        if cat == "OK":
            payload = catalogue["payload"]
            rows = payload.get("data")
            if isinstance(rows, list):
                competitions = [
                    {"id": str(x["id"]), "name": str(x["name"])}
                    for x in rows if isinstance(x, dict) and x.get("id") is not None and x.get("name")
                ]
                pagination = payload.get("pagination") or {}
                catalogue_complete = pagination.get("has_more") is False
            else:
                cat = "INVALID_DATA_SHAPE"
        self.results["competition_catalogue"] = {
            "access": cat, "rows_on_page_1": len(competitions),
            "pagination_complete": catalogue_complete,
            "sample_competitions": competitions[:10],
        }

        # Probe one recent historical competition fixture page, using only a
        # competition returned by this credential's own catalogue.
        history = {"access": "NOT_TESTED_NO_COMPETITION"}
        sample_fixture_id = None
        if competitions and self.requests < MAX_REQUESTS_PER_KEY:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            response = self.get(f"leagues/{competitions[0]['id']}/fixtures", {
                "start_time": int((now - timedelta(days=WINDOW_DAYS)).timestamp()),
                "end_time": int(now.timestamp()), "status": "finished",
                "page": 1, "per_page": 20,
            })
            history = {"access": response["access"], "http_status": response.get("http_status"),
                       "competition_tested": competitions[0]["name"], "window_days": WINDOW_DAYS,
                       "rows_returned": 0, "sample_fixture_available": False}
            if response["access"] == "OK":
                rows = response["payload"].get("data")
                if isinstance(rows, list):
                    history["rows_returned"] = len(rows)
                    for row in rows:
                        if isinstance(row, dict) and row.get("id") is not None:
                            sample_fixture_id = row["id"]
                            history["sample_fixture_available"] = True
                            break
                else:
                    history["access"] = "INVALID_DATA_SHAPE"
        self.results["historical_fixtures"] = history

        odds = {"access": "NOT_TESTED_NO_SAMPLE_FIXTURE"}
        if sample_fixture_id is not None and self.requests < MAX_REQUESTS_PER_KEY:
            response = self.get(f"fixtures/{sample_fixture_id}/odds")
            odds = {"access": response["access"], "http_status": response.get("http_status")}
            if response["access"] == "OK":
                data = response["payload"].get("data")
                odds["data_shape"] = "OBJECT" if isinstance(data, dict) else "INVALID"
                odds["rows_or_keys"] = len(data) if isinstance(data, dict) else 0
                if odds["data_shape"] == "INVALID":
                    odds["access"] = "INVALID_DATA_SHAPE"
        self.results["fixture_odds"] = odds

        self.results["team_match_statistics"] = {
            "access": "NOT_PROBED",
            "reason": "No verified team/match-statistics endpoint is currently used or documented in repository code; endpoint guessing is prohibited.",
        }
        self.results["quota_headers"] = self.quota
        self.results["request_count"] = self.requests
        self.results["request_budget"] = MAX_REQUESTS_PER_KEY
        self.results["endpoint_request_counts"] = self.endpoint_counts
        return self.results


def main():
    aliases = (
        ("STANDARD_KEY", os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()),
        ("COMMUNITY_KEY", os.getenv("FIVEDOLLARFOOTBALL_COMMUNITY_API_KEY", "").strip()),
    )
    output = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "window_days": WINDOW_DAYS, "max_requests_per_key": MAX_REQUESTS_PER_KEY,
              "credentials": {}}
    for alias, key in aliases:
        if not key:
            output["credentials"][alias] = {"status": "MISSING_SECRET"}
            continue
        try:
            probe = Probe(alias, key)
            output["credentials"][alias] = {"status": "PROBED", **probe.run()}
        except Exception as exc:
            output["credentials"][alias] = {"status": "PROBE_FAILED", "error_class": type(exc).__name__}
    print(json.dumps(output, sort_keys=True))
    standard = output["credentials"].get("STANDARD_KEY", {})
    community = output["credentials"].get("COMMUNITY_KEY", {})
    if standard.get("status") != "PROBED" or community.get("status") != "PROBED":
        print("COMPARISON: INCOMPLETE_MISSING_OR_FAILED_CREDENTIAL", file=sys.stderr)
        return 1
    print("COMPARISON: EVIDENCE_CAPTURED; review endpoint scope and quota headers; no key is promoted automatically", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
