"""Optional OddsPapi market-odds enrichment; never replaces API-Football fixtures or forecasts."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone\nfrom zoneinfo import ZoneInfo
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class OddsPapiError(RuntimeError):
    """Sanitized OddsPapi configuration/network/schema error."""


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(re.findall(r"[a-z0-9]+", text))


def _decimal(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 1 and number < 1000 else None


class OddsPapiClient:
    base_url = "https://api.oddspapi.io/v4"

    def __init__(self, api_key: str | None = None, timeout: int = 20):
        self.api_key = (api_key if api_key is not None else os.getenv("ODDSPAPI_API_KEY", "")).strip()
        self.timeout = timeout

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.api_key:
            raise OddsPapiError("ODDSPAPI_API_KEY is not configured.")
        query = dict(params or {})
        query["apiKey"] = self.api_key
        url = f"{self.base_url}/{path.lstrip('/')}?{urlencode(query)}"
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "VeltrixFootball/1.0"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # Never echo the request URL because it contains the API key.
            raise OddsPapiError(f"OddsPapi returned HTTP {exc.code} for /v4/{path}.") from None
        except (URLError, OSError, TimeoutError):
            raise OddsPapiError(f"OddsPapi network request failed for /v4/{path}.") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise OddsPapiError(f"OddsPapi returned invalid JSON for /v4/{path}.") from None
        return payload


def _active_prices(market: dict[str, Any]) -> dict[str, float]:
    prices: dict[str, float] = {}
    outcomes = market.get("outcomes") or {}
    if isinstance(outcomes, list):
        outcomes = {str(i): item for i, item in enumerate(outcomes)}
    if not isinstance(outcomes, dict):
        return prices
    for outcome in outcomes.values():
        if not isinstance(outcome, dict):
            continue
        name = str(outcome.get("outcomeName") or outcome.get("name") or "").strip().casefold()
        players = outcome.get("players") or {}
        if isinstance(players, list):
            players = {str(i): item for i, item in enumerate(players)}
        if isinstance(players, dict):
            for player in players.values():
                if not isinstance(player, dict) or not player.get("active", False):
                    continue
                price = _decimal(player.get("price") or player.get("odds"))
                if price is not None and name:
                    # Prefer the first available active price per outcome/bookmaker/market.
                    prices.setdefault(name, price)
    return prices


def normalize_fixture_odds(
    fixture: dict[str, Any],
    odds_payload: dict[str, Any],
    markets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return compact BTTS and full-time totals prices without inventing missing outcomes."""
    market_defs = {str(m.get("marketId")): m for m in markets if isinstance(m, dict)}
    boards = odds_payload.get("bookmakerOdds", {})
    result: dict[str, Any] = {"provider": "OddsPapi", "fixture_id": str(fixture.get("fixtureId") or ""),
                              "bookmakers": {}, "btts": [], "over_under": []}
    if not isinstance(boards, dict):
        return result
    for bookmaker, board in boards.items():
        if not isinstance(board, dict):
            continue
        market_map = board.get("markets") or {}
        if not isinstance(market_map, dict):
            continue
        for market_id, market in market_map.items():
            if not isinstance(market, dict):
                continue
            definition = market_defs.get(str(market_id), {})
            market_name = str(definition.get("marketName") or "").casefold()
            period = str(definition.get("period") or "").casefold()
            if period and period not in {"fulltime", "ft", "full_time"}:
                continue
            prices = _active_prices(market)
            if "both teams to score" in market_name or "bothteamsscore" == str(definition.get("marketType", "")).casefold():
                yes = prices.get("yes")
                no = prices.get("no")
                if yes or no:
                    result["btts"].append({"bookmaker": str(bookmaker), "yes": yes, "no": no, "market_id": str(market_id)})
            elif "over under" in market_name and not definition.get("playerProp", False):
                line = definition.get("handicap")
                over, under = prices.get("over"), prices.get("under")
                if over or under:
                    result["over_under"].append({"bookmaker": str(bookmaker), "line": line,
                                                  "over": over, "under": under, "market_id": str(market_id)})
    return result


def enrich_report(report: dict[str, Any], client: OddsPapiClient | None = None) -> dict[str, Any]:
    """Attach market prices only to exact same-day team matches; failures stay non-fatal to caller."""
    client = client or OddsPapiClient()
    target = date.fromisoformat(str(report["as_of_date"]))
    start = datetime.combine(target, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    markets = client.get("markets", {"language": "en"})
    if not isinstance(markets, list):
        raise OddsPapiError("OddsPapi markets response had an unexpected shape.")
    soccer_markets = [m for m in markets if isinstance(m, dict) and str(m.get("sportId")) == "10"]
    btts_defs = [m for m in soccer_markets if "both teams to score" in str(m.get("marketName", "")).casefold()]
    ou_defs = [m for m in soccer_markets if "over under" in str(m.get("marketName", "")).casefold()
               and not m.get("playerProp", False) and str(m.get("period", "")).casefold() == "fulltime"]
    if not btts_defs or not ou_defs:
        raise OddsPapiError("OddsPapi did not return soccer full-time BTTS and Over/Under market definitions.")
    fixtures = client.get("fixtures", {
        "sportId": 10, "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "statusId": 0, "hasOdds": "true",
    })
    if not isinstance(fixtures, list):
        raise OddsPapiError("OddsPapi fixtures response had an unexpected shape.")
    report_predictions = report.get("predictions", [])
    by_teams = {
        (_key(row.get("home_team")), _key(row.get("away_team"))): row
        for row in report_predictions if isinstance(row, dict)
    }
    attached = 0
    for fixture in fixtures:
        if not isinstance(fixture, dict) or str(fixture.get("sportId")) != "10" or not fixture.get("hasOdds"):
            continue
        key = (_key(fixture.get("participant1Name")), _key(fixture.get("participant2Name")))
        prediction = by_teams.get(key)
        if prediction is None:
            continue
        raw_start = str(fixture.get("startTime") or "")
        if raw_start:
            try:
                fixture_date = datetime.fromisoformat(raw_start.replace("Z", "+00:00")).astimezone(local_zone).date()
                if fixture_date != target:
                    continue
            except ValueError:
                continue
        odds_payload = client.get("odds", {"fixtureId": fixture.get("fixtureId"), "verbosity": 3})
        if not isinstance(odds_payload, dict):
            continue
        normalized = normalize_fixture_odds(fixture, odds_payload, btts_defs + ou_defs)
        if normalized["btts"] or normalized["over_under"]:
            prediction["oddspapi_market_odds"] = normalized
            attached += 1
    report["oddspapi_odds"] = {
        "provider": "OddsPapi",
        "status": "AVAILABLE" if attached else "NO_MATCHED_MARKET_ODDS",
        "fixtures_with_market_odds": attached,
        "markets_checked": ["BTTS", "Over/Under full time"],
        "note": "Market prices are informational; model outputs remain experimental and are not betting advice.",
    }
    return report
