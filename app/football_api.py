from __future__ import annotations

from typing import Any
import requests

from app.config import Settings

class FootballAPIError(RuntimeError):
    pass

class FootballAPI:
    def __init__(self, settings: Settings, timeout: int = 20):
        self.settings = settings
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "x-apisports-key": settings.api_key,
            "Accept": "application/json",
            "User-Agent": "VeltrixFootball/0.1",
        })

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.settings.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.get(url, params=params or {}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise FootballAPIError(f"Network request failed: {exc.__class__.__name__}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise FootballAPIError(
                f"API returned non-JSON content (HTTP {response.status_code})."
            ) from exc

        if response.status_code >= 400:
            # Avoid including request headers or the API key in error messages.
            raise FootballAPIError(
                f"API request failed with HTTP {response.status_code}. "
                f"Response errors: {payload.get('errors', 'not provided')}"
            )

        if not isinstance(payload, dict):
            raise FootballAPIError("API response had an unexpected JSON shape.")

        errors = payload.get("errors")
        if errors:
            raise FootballAPIError(f"API reported errors: {errors}")

        payload["_veltrix_meta"] = {
            "http_status": response.status_code,
            "requests_remaining": response.headers.get("x-ratelimit-requests-remaining"),
            "requests_limit": response.headers.get("x-ratelimit-requests-limit"),
            "requests_reset": response.headers.get("x-ratelimit-requests-reset"),
        }
        return payload

    def status(self) -> dict[str, Any]:
        return self.get("status")

    def fixtures(self, date: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        return self.get("fixtures", {"date": date, "timezone": timezone})

    def fixtures_between(self, start_date: str, end_date: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        """Fetch fixtures in an inclusive date range; coverage depends on API plan."""
        return self.get("fixtures", {"from": start_date, "to": end_date, "timezone": timezone})

    def leagues(self, current: bool = True) -> dict[str, Any]:
        return self.get("leagues", {"current": str(current).lower()})
