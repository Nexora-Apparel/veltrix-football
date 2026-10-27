"""API-Football (API-Sports v3) adapter for live account and prematch-odds checks.

This is distinct from Highlightly and from APIFootball.com. It reads
API_FOOTBALL_KEY and sends it only in the x-apisports-key request header.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import math
from typing import Any

import requests


class APIFootballError(RuntimeError):
    """Sanitized provider/configuration error; never includes the API key."""


class APIFootballClient:
    base_url = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str | None = None, timeout: int = 15, session: Any = None):
        self.api_key = (api_key if api_key is not None else os.getenv("API_FOOTBALL_KEY", "")).strip()
        self.timeout = timeout
        self.session = session or requests.Session()
        if self.api_key:
            self.session.headers.update({
                "x-apisports-key": self.api_key,
                "Accept": "application/json",
                "User-Agent": "VeltrixFootball/1.0",
            })

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise APIFootballError("API_FOOTBALL_KEY is not configured in the deployment environment.")
        try:
            response = self.session.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                params=params or {},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise APIFootballError(f"API-Football network error: {exc.__class__.__name__}.") from None
        try:
            payload = response.json()
        except ValueError:
            raise APIFootballError(f"API-Football returned non-JSON data (HTTP {response.status_code}).") from None

        if response.status_code >= 400:
            if response.status_code in (401, 403):
                reason = "API key rejected or account/subscription does not permit this request."
            elif response.status_code == 429:
                reason = "API-Football request quota or rate limit reached."
            else:
                reason = f"HTTP {response.status_code}."
            raise APIFootballError(f"API-Football request failed: {reason}")
        if not isinstance(payload, dict):
            raise APIFootballError("API-Football response had an unexpected JSON shape.")

        errors = payload.get("errors")
        if errors:
            # Provider errors can include arbitrary text; do not echo it or any request URL.
            if isinstance(errors, dict):
                keys = ", ".join(str(key) for key in list(errors)[:5])
                detail = f"Provider reported an error in: {keys or 'request parameters'}."
            elif isinstance(errors, list):
                detail = "Provider rejected the request parameters or account access."
            else:
                detail = "Provider rejected the request."
            raise APIFootballError(detail)
        payload["_veltrix_meta"] = {
            "provider": "API-Football (API-Sports)",
            "http_status": response.status_code,
            "requests_limit": response.headers.get("x-ratelimit-requests-limit"),
            "requests_remaining": response.headers.get("x-ratelimit-requests-remaining"),
        }
        return payload

    def status(self) -> dict[str, Any]:
        """Check key/account/subscription using the provider's quota-exempt status endpoint."""
        payload = self._get("status")
        response = payload.get("response")
        if not isinstance(response, dict):
            raise APIFootballError("API-Football status response is missing account/subscription details.")
        subscription = response.get("subscription") or {}
        account = response.get("account") or {}
        requests_info = response.get("requests") or {}
        return {
            "provider": "API-Football (API-Sports)",
            "authenticated": True,
            "account": {
                "name_available": bool(account.get("firstname") or account.get("name")),
                "email_available": bool(account.get("email")),
            },
            "subscription": {
                "active": subscription.get("active"),
                "plan": subscription.get("plan"),
                "end": subscription.get("end"),
            },
            "requests": {
                "current": requests_info.get("current"),
                "daily_limit": requests_info.get("limit_day"),
            },
            "_veltrix_meta": payload.get("_veltrix_meta", {}),
        }

    @staticmethod
    def _decimal_price(value: Any) -> float | None:
        try:
            price = float(str(value).strip())
        except (TypeError, ValueError, OverflowError):
            return None
        return price if math.isfinite(price) and 1.0 < price < 1000.0 else None

    @staticmethod
    def _fixture_datetime(raw: Any, timezone: str) -> tuple[str, str]:
        if not isinstance(raw, str) or not raw.strip():
            return "", ""
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            target = ZoneInfo(timezone)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=target)
            else:
                parsed = parsed.astimezone(target)
            return parsed.date().isoformat(), parsed.strftime("%H:%M")
        except (ValueError, OverflowError, KeyError):
            return raw[:10], ""

    @classmethod
    def normalize_odds(cls, raw_rows: list[Any], timezone: str) -> list[dict[str, Any]]:
        """Flatten API-Sports fixture/bookmaker/bet nesting into Veltrix's odds-row shape."""
        normalized: list[dict[str, Any]] = []
        for fixture_row in raw_rows:
            if not isinstance(fixture_row, dict):
                continue
            fixture = fixture_row.get("fixture") or {}
            teams = fixture_row.get("teams") or {}
            league = fixture_row.get("league") or {}
            home = str((teams.get("home") or {}).get("name") or "").strip()
            away = str((teams.get("away") or {}).get("name") or "").strip()
            fixture_id = str(fixture.get("id") or "").strip()
            match_date, match_time = cls._fixture_datetime(fixture.get("date"), timezone)
            if not (fixture_id and home and away and match_date):
                continue
            for bookmaker in fixture_row.get("bookmakers") or []:
                if not isinstance(bookmaker, dict):
                    continue
                prices: dict[str, float] = {}
                for bet in bookmaker.get("bets") or []:
                    if not isinstance(bet, dict):
                        continue
                    market = str(bet.get("name") or "").casefold().strip()
                    for selection in bet.get("values") or []:
                        if not isinstance(selection, dict):
                            continue
                        label = str(selection.get("value") or "").casefold().strip()
                        price = cls._decimal_price(selection.get("odd"))
                        if price is None:
                            continue
                        if market in {"match winner", "1x2", "fulltime result", "winner"}:
                            if label in {"home", home.casefold(), "1"}:
                                prices["home"] = price
                            elif label in {"draw", "x"}:
                                prices["draw"] = price
                            elif label in {"away", away.casefold(), "2"}:
                                prices["away"] = price
                        elif market in {"both teams score", "both teams to score", "btts"}:
                            if label in {"yes", "no"}:
                                prices["yes" if label == "yes" else "no"] = price
                        elif market in {"goals over/under", "over/under", "total goals"}:
                            parts = label.split()
                            if len(parts) == 2 and parts[0] in {"over", "under"}:
                                try:
                                    line = float(parts[1])
                                except ValueError:
                                    continue
                                if line in {0.5, 1.5, 2.5, 3.5, 4.5}:
                                    prices[f"{parts[0]}_{str(line).replace('.', '_')}"] = price
                if not prices:
                    continue
                normalized.append({
                    "provider": "API-Football (API-Sports)",
                    "match_id": fixture_id,
                    "home_team": home,
                    "away_team": away,
                    "league": str(league.get("name") or "Competition unavailable"),
                    "date": match_date,
                    "time": match_time,
                    "bookmaker": str(bookmaker.get("name") or "Unknown bookmaker"),
                    "odd_date": None,
                    "odds": prices,
                })
        return normalized

    _STATUS_MAP = {
        "NS": "NS", "TBD": "TBD", "1H": "LIVE", "HT": "LIVE", "2H": "LIVE",
        "ET": "LIVE", "BT": "LIVE", "P": "LIVE", "LIVE": "LIVE",
        "FT": "FT", "AET": "FT", "PEN": "FT", "PST": "PST", "CANC": "CANC",
        "SUSP": "SUSP", "INT": "SUSP", "ABD": "ABD", "AWD": "FT", "WO": "FT",
    }
    _LEAGUE_CODES = {
        "PREMIER LEAGUE": "PL", "ENGLISH PREMIER LEAGUE": "PL",
        "CHAMPIONSHIP": "ELC", "LEAGUE ONE": "EL1", "LEAGUE TWO": "EL2",
        "LA LIGA": "PD", "LALIGA": "PD", "SERIE A": "SA", "SERIE B": "SB",
        "BUNDESLIGA": "BL1", "2. BUNDESLIGA": "BL2", "LIGUE 1": "FL1",
        "LIGUE 2": "FL2", "EREDIVISIE": "DED", "PRIMEIRA LIGA": "PPL",
        "LIGA PORTUGAL": "PPL", "SCOTTISH PREMIERSHIP": "SPL",
        "BRASILEIRAO": "BSA", "BRAZIL SERIE A": "BSA",
    }

    @classmethod
    def normalize_fixtures(cls, raw_rows: list[Any]) -> list[dict[str, Any]]:
        """Normalize API-Football fixtures to the stable Veltrix internal fixture shape."""
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            fixture = raw.get("fixture") or {}
            teams = raw.get("teams") or {}
            home, away = teams.get("home") or {}, teams.get("away") or {}
            league = raw.get("league") or {}
            goals = raw.get("goals") or {}
            status = (fixture.get("status") or {}).get("short") or "TBD"
            league_name = str(league.get("name") or "")
            try:
                fixture_id = int(fixture.get("id"))
            except (TypeError, ValueError):
                fixture_id = fixture.get("id")
            try:
                league_id = int(league.get("id"))
            except (TypeError, ValueError):
                league_id = league.get("id")
            rows.append({
                "fixture": {
                    "id": fixture_id, "date": fixture.get("date"),
                    "status": {"short": cls._STATUS_MAP.get(str(status).upper(), str(status).upper())},
                },
                "teams": {
                    "home": {"id": home.get("id"), "name": home.get("name")},
                    "away": {"id": away.get("id"), "name": away.get("name")},
                },
                "league": {
                    "id": league_id, "name": league_name,
                    "code": cls._LEAGUE_CODES.get(league_name.strip().upper()),
                    "season": league.get("season"),
                },
                "goals": {"home": goals.get("home"), "away": goals.get("away")},
                "_api_football_status": (fixture.get("status") or {}).get("long"),
            })
        return rows

    def _fixtures_query(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch paginated API-Football fixtures without silently truncating results."""
        first = self._get("fixtures", params)
        raw = first.get("response")
        if not isinstance(raw, list):
            raise APIFootballError("API-Football fixtures response is missing its response list.")
        all_rows = list(raw)
        paging = first.get("paging") or {}
        try:
            total_pages = max(1, int(paging.get("total", 1)))
        except (TypeError, ValueError):
            total_pages = 1
        if total_pages > 20:
            raise APIFootballError("API-Football returned more than 20 fixture pages for one query; refusing to publish a truncated list.")
        for page in range(2, total_pages + 1):
            payload = self._get("fixtures", {**params, "page": page})
            batch = payload.get("response")
            if not isinstance(batch, list):
                raise APIFootballError("API-Football pagination response is missing its response list.")
            all_rows.extend(batch)
        return {
            "response": self.normalize_fixtures(all_rows),
            "results": len(all_rows),
            "paging": {"current": total_pages, "total": total_pages},
            "provider": "API-Football (API-Sports)",
            "_veltrix_meta": {
                **(first.get("_veltrix_meta") or {}),
                "provider": "API-Football (API-Sports)",
                "pages_fetched": total_pages,
                "raw_fixture_rows": len(all_rows),
            },
        }

    def fixtures(self, day: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        """Fetch fixtures for a local calendar day from the primary API-Football feed."""
        try:
            parsed_day = date.fromisoformat(day)
            ZoneInfo(timezone)
        except (TypeError, ValueError, KeyError):
            raise APIFootballError("Date must use YYYY-MM-DD format and timezone must be valid.") from None
        return self._fixtures_query({"date": parsed_day.isoformat(), "timezone": timezone})

    def fixtures_between(
        self, start_date: str, end_date: str, timezone: str = "Africa/Lagos"
    ) -> dict[str, Any]:
        """Fetch an inclusive range with one supported date-filtered request per day.

        The account can reject some older dates on plan coverage. Query newest-first,
        retain successful days, and report every plan-limited date so callers never
        mistake partial history for a complete range.
        """
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
            ZoneInfo(timezone)
        except (TypeError, ValueError, KeyError):
            raise APIFootballError("Dates must use YYYY-MM-DD format and timezone must be valid.") from None
        if end < start:
            raise APIFootballError("end date must be on or after start date.")
        if (end - start).days >= 7:
            raise APIFootballError("API-Football history refresh ranges are capped at 7 calendar days.")
        combined: list[dict[str, Any]] = []
        metas: list[dict[str, Any]] = []
        successful_dates: list[str] = []
        failed_dates: list[str] = []
        cursor = end
        while cursor >= start:
            day = cursor.isoformat()
            try:
                payload = self.fixtures(day, timezone)
            except APIFootballError as exc:
                if "reported an error in: plan" not in str(exc).lower():
                    raise
                failed_dates.append(day)
                cursor -= timedelta(days=1)
                continue
            combined.extend(payload.get("response") or [])
            metas.append(payload.get("_veltrix_meta") or {})
            successful_dates.append(day)
            cursor -= timedelta(days=1)
        meta = {
            "provider": "API-Football (API-Sports)",
            "requests_made": sum(int(item.get("requests_made", item.get("pages_fetched", 1)) or 1) for item in metas),
            "requests_remaining": next(
                (item.get("requests_remaining") for item in metas
                 if item.get("requests_remaining") is not None), None
            ),
            "date_queries": len(successful_dates) + len(failed_dates),
            "successful_dates": sorted(successful_dates),
            # These are explicit subscription/plan restrictions, not transient
            # transport failures. Persist them separately so we do not spend a
            # request every week retrying dates the account cannot access.
            "failed_dates": sorted(failed_dates),
            "plan_limited_dates": sorted(failed_dates),
        }
        if failed_dates:
            meta["warning"] = (
                "API-Football plan did not return historical fixtures for "
                + ", ".join(sorted(failed_dates))
                + "; those dates are recorded as history gaps."
            )
        return {
            "response": combined,
            "results": len(combined),
            "provider": "API-Football (API-Sports)",
            "_veltrix_meta": meta,
        }

    def leagues(self, current: bool = True) -> dict[str, Any]:
        """List competitions available through API-Football for the selected season."""
        season = date.today().year if current else date.today().year - 1
        payload = self._get("leagues", {"season": season})
        rows = payload.get("response")
        if not isinstance(rows, list):
            raise APIFootballError("API-Football leagues response is missing its response list.")
        return {
            "provider": "API-Football (API-Sports)",
            "results": len(rows),
            "response": rows,
            "_veltrix_meta": payload.get("_veltrix_meta", {}),
        }

    def odds_for_date(self, day: str, *, timezone: str = "Africa/Lagos", page: int = 1) -> dict[str, Any]:
        """Fetch one page of prematch odds and normalize prices for command/report use.

        API-Football exposes 10 fixture records per page. Availability depends on
        fixture timing, league coverage, bookmaker, and subscription. Odds are
        normally published 1–14 days before a fixture; historical retention is
        limited, so an empty response is not by itself an authentication failure.
        """
        try:
            parsed_day = date.fromisoformat(day)
            ZoneInfo(timezone)
        except (TypeError, ValueError, KeyError):
            raise APIFootballError("Date must use YYYY-MM-DD format and timezone must be valid.") from None
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise APIFootballError("Page must be a positive integer.")
        payload = self._get("odds", {"date": parsed_day.isoformat(), "timezone": timezone, "page": page})
        raw_rows = payload.get("response")
        if not isinstance(raw_rows, list):
            raise APIFootballError("API-Football odds response is missing its response list.")
        # The API-Sports /odds response commonly omits team names. Some plans
        # reject the batch `ids` fixture filter, so fall back to the supported
        # date filter rather than losing all odds rows.
        enrichment_status = "NOT_NEEDED"
        enrichment_detail = ""
        missing_team_rows = [
            row for row in raw_rows
            if isinstance(row, dict)
            and not (
                str(((row.get("teams") or {}).get("home") or {}).get("name") or "").strip()
                and str(((row.get("teams") or {}).get("away") or {}).get("name") or "").strip()
            )
        ]
        if missing_team_rows:
            fixture_ids = [
                str(((row.get("fixture") or {}).get("id") or "")).strip()
                for row in missing_team_rows
            ]
            fixture_ids = list(dict.fromkeys(fid for fid in fixture_ids if fid.isdigit()))
            fixture_teams: dict[str, dict[str, Any]] = {}

            def collect_fixture_teams(fixtures_response: Any) -> None:
                if not isinstance(fixtures_response, list):
                    return
                for fixture_row in fixtures_response:
                    if not isinstance(fixture_row, dict):
                        continue
                    fid = str(((fixture_row.get("fixture") or {}).get("id") or "")).strip()
                    teams = fixture_row.get("teams") or {}
                    home = teams.get("home") or {}
                    away = teams.get("away") or {}
                    if fid and home.get("name") and away.get("name"):
                        fixture_teams[fid] = {"home": home, "away": away}

            if fixture_ids:
                try:
                    fixtures_payload = self._get("fixtures", {
                        "ids": "-".join(fixture_ids[:20]),
                        "timezone": timezone,
                    })
                    collect_fixture_teams(fixtures_payload.get("response"))
                except APIFootballError as exc:
                    enrichment_detail = f"Batch fixture lookup failed: {str(exc)[:140]}"

                # The API's documentation notes that batch IDs may depend on
                # plan access. A date lookup is a lower-cost fallback and can
                # still enrich the 10 odds fixtures returned for this date.
                if not fixture_teams:
                    try:
                        fixtures_payload = self._get("fixtures", {
                            "date": parsed_day.isoformat(),
                            "timezone": timezone,
                        })
                        collect_fixture_teams(fixtures_payload.get("response"))
                        if fixture_teams:
                            enrichment_detail = ""
                    except APIFootballError as exc:
                        fallback_detail = f"Date fixture lookup failed: {str(exc)[:140]}"
                        enrichment_detail = (
                            f"{enrichment_detail}; {fallback_detail}"
                            if enrichment_detail else fallback_detail
                        )

                for row in raw_rows:
                    if not isinstance(row, dict):
                        continue
                    fid = str(((row.get("fixture") or {}).get("id") or "")).strip()
                    if fid in fixture_teams:
                        row["teams"] = fixture_teams[fid]

                named_rows = [
                    row for row in raw_rows
                    if isinstance(row, dict)
                    and str(((row.get("teams") or {}).get("home") or {}).get("name") or "").strip()
                    and str(((row.get("teams") or {}).get("away") or {}).get("name") or "").strip()
                ]
                if len(named_rows) == len(raw_rows):
                    enrichment_status = "SUCCESS"
                elif named_rows:
                    enrichment_status = "PARTIAL"
                else:
                    enrichment_status = "FAILED"
                    if not enrichment_detail:
                        enrichment_detail = "Fixture lookups returned no matching team names."
            else:
                enrichment_status = "NO_FIXTURE_IDS"

        rows = self.normalize_odds(raw_rows, timezone)
        meta = dict(payload.get("_veltrix_meta", {}))
        meta["team_name_enrichment"] = enrichment_status
        if enrichment_detail:
            meta["team_name_enrichment_detail"] = enrichment_detail
        bookmaker_count = 0
        fixtures_with_bookmakers = 0
        market_names: list[str] = []
        fixture_examples: list[dict[str, str]] = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            fixture = raw_row.get("fixture") or {}
            teams = raw_row.get("teams") or {}
            home = str((teams.get("home") or {}).get("name") or "").strip()
            away = str((teams.get("away") or {}).get("name") or "").strip()
            if len(fixture_examples) < 3:
                fixture_examples.append({
                    "fixture_id": str(fixture.get("id") or ""),
                    "match": f"{home} vs {away}" if home and away else "Team names missing from odds response",
                    "date": str(fixture.get("date") or "")[:10],
                    "league": str((raw_row.get("league") or {}).get("name") or "Unknown"),
                })
            bookmakers = raw_row.get("bookmakers") or []
            if bookmakers:
                fixtures_with_bookmakers += 1
            for bookmaker in bookmakers:
                if not isinstance(bookmaker, dict):
                    continue
                bookmaker_count += 1
                for bet in bookmaker.get("bets") or []:
                    if not isinstance(bet, dict):
                        continue
                    market = str(bet.get("name") or "").strip()
                    if market and market not in market_names and len(market_names) < 8:
                        market_names.append(market)
        meta.update({
            "status": "AVAILABLE" if rows else "NO_ODDS_RETURNED",
            "raw_fixture_rows": len(raw_rows),
            "fixtures_with_bookmakers": fixtures_with_bookmakers,
            "bookmaker_count": bookmaker_count,
            "sample_market_names": market_names,
            "fixture_examples": fixture_examples,
        })
        return {
            "provider": "API-Football (API-Sports)",
            "date": parsed_day.isoformat(),
            "timezone": timezone,
            "results": len(rows),
            "paging": payload.get("paging") or {},
            "response": rows,
            "_veltrix_meta": meta,
        }
