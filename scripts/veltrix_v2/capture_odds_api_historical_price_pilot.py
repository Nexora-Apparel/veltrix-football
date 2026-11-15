#!/usr/bin/env python3
"""One-time historical 1X2 pilot for an already-approved The Odds API league.

Maximum cost: 1 credit event discovery + 1 credit market discovery + 10 credits
for one region/market odds snapshot. The raw odds body is stored only in the
isolated staging database. Artifacts and logs contain metadata only, never odds.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.phase4_odds_account_probe import _fetch_sports, _load_approval
from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target
from veltrix_v2.data.contracts import ProviderResponse
from veltrix_v2.data.postgres import PostgresHistoryStore
from veltrix_v2.providers.odds_api_v4.transport_contract import (
    RawTransportResponse, validate_transport_response,
)

API_BASE = "https://api.the-odds-api.com/v4"
PROVIDER = "the_odds_api"
SOURCE_ID = "odds_api_v4"
SPORT = "soccer_spain_la_liga"
SNAPSHOT_AT = "2026-11-08T19:55:00Z"
KICKOFF_AT = "2026-11-08T20:00:00Z"
HOME_TEAM = "Atletico Madrid"
AWAY_TEAM = "Barcelona"
CANONICAL_FIXTURE_ID = "1426"
CANONICAL_PROVIDER_FIXTURE_ID = "3405776829"
REGION = "eu"
MARKET = "h2h_3_way"
APPROVAL_ID = "approval-the-odds-api-v4-owner-authorized-2026-11-14"
MIN_REMAINING_BEFORE_SPEND = 100
MAX_CREDITS = 12
EXCHANGE_KEYS = {"betfair_ex_eu", "matchbook"}
USER_AGENT = "VELTRIX-FOOTBALL-2.0-APPROVED-ODDS-HISTORICAL-PILOT/1.0"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _normalize(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold().strip()


def _fetch_json(path: str, api_key: str):
    request = Request(
        API_BASE + path,
        headers={"x-api-key": api_key, "Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    requested_at = datetime.now(timezone.utc)
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=25) as response:
            body = response.read(5_000_001)
            headers = {key.lower(): str(value) for key, value in response.headers.items()
                       if key.lower() in {"x-requests-used", "x-requests-remaining", "x-requests-last"}}
            status = int(response.status)
    except HTTPError as exc:
        raise RuntimeError(f"ODDS_API_HISTORICAL_HTTP_{exc.code}_NO_RETRY") from None
    except URLError:
        raise RuntimeError("ODDS_API_HISTORICAL_NETWORK_ERROR_NO_RETRY") from None
    retrieved_at = datetime.now(timezone.utc)
    if status != 200:
        raise RuntimeError(f"ODDS_API_HISTORICAL_HTTP_{status}_NO_RETRY")
    if len(body) > 5_000_000:
        raise RuntimeError("ODDS_API_HISTORICAL_RESPONSE_TOO_LARGE")
    decision = validate_transport_response(RawTransportResponse(
        status_code=status, headers=headers, body=body, retrieved_at=retrieved_at,
    ))
    if not decision.accepted or decision.envelope is None:
        raise RuntimeError(decision.reason_code or "ODDS_API_TRANSPORT_UNVERIFIED")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("ODDS_API_HISTORICAL_INVALID_JSON") from None
    return payload, body, headers, decision.envelope, requested_at, retrieved_at


def _data(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"], payload.get("timestamp")
    return payload, None


def _assert_approved_scope(staging_dsn: str):
    validate_staging_dsn_target(staging_dsn)
    approval = _load_approval(staging_dsn)
    if approval.provider != PROVIDER or approval.source_id != SOURCE_ID:
        raise PermissionError("ODDS_API_SOURCE_APPROVAL_IDENTITY_MISMATCH")
    scope = {item.strip() for item in approval.competition_scope.split(",") if item.strip()}
    if SPORT not in scope:
        raise PermissionError("ODDS_API_COMPETITION_OUTSIDE_APPROVED_SCOPE")
    if approval.approval_id != APPROVAL_ID or approval.data_type != "odds_quote":
        raise PermissionError("ODDS_API_APPROVAL_OR_DATA_TYPE_MISMATCH")
    return approval


def _market_summary(data: dict, kickoff: datetime, home: str, away: str) -> dict:
    if not isinstance(data, dict):
        raise RuntimeError("ODDS_API_ODDS_DATA_NOT_OBJECT")
    bookmakers_raw = data.get("bookmakers", [])
    if not isinstance(bookmakers_raw, list):
        raise RuntimeError("ODDS_API_BOOKMAKERS_NOT_LIST")
    details = []
    all_market_keys = set()
    post_kickoff_quotes = 0
    missing_quote_timestamps = 0
    complete_three_way = 0
    sportsbook_three_way = 0
    update_times = []
    for bookmaker in bookmakers_raw:
        if not isinstance(bookmaker, dict):
            continue
        bkey = str(bookmaker.get("key") or "")
        btitle = str(bookmaker.get("title") or bkey)
        markets = bookmaker.get("markets", [])
        if not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, dict):
                continue
            mkey = str(market.get("key") or "")
            all_market_keys.add(mkey)
            if mkey != MARKET:
                continue
            last_update_raw = market.get("last_update") or bookmaker.get("last_update")
            last_update = _utc(last_update_raw) if isinstance(last_update_raw, str) else None
            if last_update is None:
                missing_quote_timestamps += 1
            else:
                update_times.append(last_update)
                if last_update > kickoff:
                    post_kickoff_quotes += 1
            outcomes = market.get("outcomes", [])
            if not isinstance(outcomes, list):
                outcomes = []
            names = [str(item.get("name") or "") for item in outcomes if isinstance(item, dict)]
            normalized = {_normalize(name) for name in names}
            complete = (
                _normalize(home) in normalized
                and _normalize(away) in normalized
                and "draw" in normalized
                and len(outcomes) == 3
                and all(
                    isinstance(item, dict)
                    and isinstance(item.get("price"), (int, float))
                    and float(item["price"]) > 1.0
                    for item in outcomes
                )
            )
            if complete:
                complete_three_way += 1
                if bkey not in EXCHANGE_KEYS:
                    sportsbook_three_way += 1
            age_seconds = (kickoff - last_update).total_seconds() if last_update else None
            details.append({
                "bookmaker_key": bkey,
                "bookmaker_title": btitle,
                "market_key": mkey,
                "last_update": last_update.isoformat() if last_update else None,
                "seconds_before_kickoff": age_seconds,
                "outcome_count": len(outcomes),
                "outcome_names": sorted(names),
                "complete_three_way": complete,
                "provider_class": "EXCHANGE" if bkey in EXCHANGE_KEYS else "BOOKMAKER",
            })
    return {
        "bookmaker_market_rows": details,
        "bookmaker_count": len({item["bookmaker_key"] for item in details}),
        "sportsbook_count": len({item["bookmaker_key"] for item in details if item["provider_class"] == "BOOKMAKER"}),
        "exchange_count": len({item["bookmaker_key"] for item in details if item["provider_class"] == "EXCHANGE"}),
        "complete_three_way_bookmakers": complete_three_way,
        "complete_three_way_sportsbooks": sportsbook_three_way,
        "market_keys": sorted(value for value in all_market_keys if value),
        "missing_quote_timestamps": missing_quote_timestamps,
        "post_kickoff_quote_count": post_kickoff_quotes,
        "quote_update_min": min(update_times).isoformat() if update_times else None,
        "quote_update_max": max(update_times).isoformat() if update_times else None,
        "raw_prices_in_summary": False,
    }


def _persist_staging(dsn: str, approval, response: ProviderResponse, payload: dict,
                     provider_entity_id: str, snapshot: datetime, kickoff: datetime) -> tuple[int, int]:
    import psycopg

    validate_staging_dsn_target(dsn)
    store = PostgresHistoryStore(
        lambda: psycopg.connect(dsn),
        allow_writes=True,
        expected_database="veltrix_football_staging",
    )
    metadata = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload_hash = hashlib.sha256(metadata.encode("utf-8")).hexdigest()
    with psycopg.connect(dsn, autocommit=False) as conn:
        conn.execute("SET TRANSACTION READ WRITE")
        identity = conn.execute(
            "SELECT current_database(),current_user,current_setting('transaction_read_only')"
        ).fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner", "off"):
            raise PermissionError("ODDS_API_STAGING_WRITE_TARGET_MISMATCH")
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (response.request_id,))
        existing = conn.execute(
            """SELECT id,response_sha256,raw_body FROM provider_responses
               WHERE provider=%s AND source_id=%s AND request_id=%s ORDER BY id""",
            (PROVIDER, SOURCE_ID, response.request_id),
        ).fetchall()
        if existing:
            if len(existing) != 1 or bytes(existing[0][2]) != response.raw_body:
                raise RuntimeError("ODDS_API_PILOT_IDEMPOTENCY_CONFLICT")
            source = conn.execute(
                """SELECT id FROM source_observations
                   WHERE provider=%s AND endpoint=%s AND entity_type='odds_snapshot'
                     AND provider_entity_id=%s AND payload_sha256=%s""",
                (PROVIDER, response.endpoint, provider_entity_id, payload_hash),
            ).fetchone()
            if not source:
                raise RuntimeError("ODDS_API_EXISTING_RESPONSE_WITHOUT_SOURCE_OBSERVATION")
            conn.commit()
            return int(existing[0][0]), int(source[0])

        # The source approval is re-evaluated immediately before immutable storage.
        current_approval = _assert_approved_scope(dsn)
        if current_approval.approval_id != approval.approval_id:
            raise PermissionError("ODDS_API_APPROVAL_CHANGED_DURING_CAPTURE")
        cur = conn.cursor()
        response_id = store._persist_provider_response(cur, response)
        now = datetime.now(timezone.utc)
        cur.execute(
            """INSERT INTO source_observations (
                provider,endpoint,entity_type,provider_entity_id,payload_sha256,
                retrieved_at,payload,source_id,data_type,season_key,source_event_time,
                available_at,availability_basis,rights_approval_id,schema_version,
                provider_response_id,point_in_time_certifiable,source_published_at,
                source_effective_at,recorded_at,source_timestamp_raw,source_timestamp_basis
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,
                      NULL,NULL,%s,%s,%s)
            ON CONFLICT DO NOTHING""",
            (
                PROVIDER, response.endpoint, "odds_snapshot", provider_entity_id,
                payload_hash, response.fetched_at_utc, metadata, SOURCE_ID,
                "historical_odds_snapshot", "2026", kickoff, snapshot,
                "archival_snapshot_timestamp", approval.approval_id,
                "veltrix-v2-the-odds-api-historical-snapshot-v1", response_id,
                now, snapshot.isoformat(), "archival_snapshot_timestamp",
            ),
        )
        source = cur.execute(
            """SELECT id FROM source_observations
               WHERE provider=%s AND endpoint=%s AND entity_type='odds_snapshot'
                 AND provider_entity_id=%s AND payload_sha256=%s""",
            (PROVIDER, response.endpoint, provider_entity_id, payload_hash),
        ).fetchone()
        if not source:
            raise RuntimeError("ODDS_API_SOURCE_OBSERVATION_INSERT_FAILED")
        conn.commit()
        return int(response_id), int(source[0])


def run_capture(api_key: str, staging_dsn: str) -> dict:
    approval = _assert_approved_scope(staging_dsn)
    request_id = "veltrix-v2-historical-odds-pilot-la-liga-atletico-madrid-barcelona-h2h3way-eu-2026-11-08T20:00:00Z"
    endpoint = f"/v4/historical/sports/{SPORT}/events/{{event_id}}/odds"
    # Check idempotency before any paid requests.
    import psycopg
    with psycopg.connect(staging_dsn, autocommit=False) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        identity = conn.execute("SELECT current_database(),current_user").fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner"):
            raise PermissionError("ODDS_API_STAGING_READ_TARGET_MISMATCH")
        existing = conn.execute(
            """SELECT id,response_sha256 FROM provider_responses
               WHERE provider=%s AND source_id=%s AND request_id=%s""",
            (PROVIDER, SOURCE_ID, request_id),
        ).fetchall()
        if existing:
            if len(existing) != 1:
                raise RuntimeError("ODDS_API_PILOT_EXISTING_RESPONSE_AMBIGUOUS")
            obs = conn.execute(
                """SELECT id FROM source_observations
                   WHERE provider=%s AND endpoint LIKE %s AND entity_type='odds_snapshot'
                   ORDER BY retrieved_at DESC LIMIT 1""",
                (PROVIDER, f"/v4/historical/sports/{SPORT}/events/%/odds"),
            ).fetchone()
            return {
                "status": "ALREADY_CAPTURED",
                "provider_response_id": int(existing[0][0]),
                "response_sha256": existing[0][1].strip(),
                "source_observation_id": int(obs[0]) if obs else None,
                "credits_spent_this_run": 0,
                "database_writes_this_run": 0,
                "raw_prices_in_artifact": False,
            }

    requested_at, retrieved_at, sports_body, _, envelope, sports = _fetch_sports(api_key)
    if SPORT not in sports:
        raise RuntimeError("APPROVED_SPORT_KEY_NOT_IN_ACCOUNT_CATALOGUE")
    quota = envelope.quota_evidence
    if not quota.complete or quota.requests_last != 0 or quota.requests_remaining is None:
        raise RuntimeError("ODDS_API_QUOTA_PREFLIGHT_UNVERIFIED")
    if quota.requests_remaining < MIN_REMAINING_BEFORE_SPEND:
        raise RuntimeError("ODDS_API_QUOTA_BUFFER_BELOW_100")

    events_path = f"/historical/sports/{SPORT}/events?" + urlencode({"date": SNAPSHOT_AT})
    events_payload, events_body, events_headers, events_env, events_req, events_got = _fetch_json(events_path, api_key)
    if events_env.quota_evidence.requests_last != 1:
        raise RuntimeError("ODDS_API_EVENT_DISCOVERY_COST_NOT_ONE")
    if events_env.quota_evidence.requests_remaining != quota.requests_remaining - 1:
        raise RuntimeError("ODDS_API_EVENT_DISCOVERY_QUOTA_DELTA_UNEXPECTED")
    events_data, events_snapshot = _data(events_payload)
    if not isinstance(events_data, list):
        raise RuntimeError("ODDS_API_EVENT_DISCOVERY_DATA_NOT_LIST")
    target_events = [
        item for item in events_data if isinstance(item, dict)
        and _normalize(item.get("home_team", "")) == _normalize(HOME_TEAM)
        and _normalize(item.get("away_team", "")) == _normalize(AWAY_TEAM)
        and item.get("commence_time") == KICKOFF_AT
    ]
    if len(target_events) != 1:
        return {
            "status": "APPROVED_LEAGUE_EVENT_NOT_UNIQUELY_FOUND",
            "sport_key": SPORT,
            "target_fixture": {"canonical_fixture_id": CANONICAL_FIXTURE_ID, "home": HOME_TEAM,
                               "away": AWAY_TEAM, "kickoff": KICKOFF_AT},
            "event_snapshot_timestamp": events_snapshot,
            "events_returned": len(events_data),
            "target_event_candidates": len(target_events),
            "credits_spent_this_run": events_env.quota_evidence.requests_last,
            "database_writes_this_run": 0,
            "raw_prices_in_artifact": False,
        }
    if not isinstance(events_snapshot, str) or _utc(events_snapshot) > _utc(KICKOFF_AT):
        raise RuntimeError("ODDS_API_EVENT_DISCOVERY_SNAPSHOT_NOT_PRE_KICKOFF")
    event = target_events[0]
    event_id = str(event.get("id") or "")
    if not event_id:
        raise RuntimeError("ODDS_API_EVENT_ID_MISSING")

    markets_path = (
        f"/historical/sports/{SPORT}/events/{event_id}/markets?"
        + urlencode({"regions": REGION, "date": SNAPSHOT_AT})
    )
    markets_payload, markets_body, markets_headers, markets_env, markets_req, markets_got = _fetch_json(markets_path, api_key)
    if markets_env.quota_evidence.requests_last != 1:
        raise RuntimeError("ODDS_API_MARKET_DISCOVERY_COST_NOT_ONE")
    if markets_env.quota_evidence.requests_remaining != events_env.quota_evidence.requests_remaining - 1:
        raise RuntimeError("ODDS_API_MARKET_DISCOVERY_QUOTA_DELTA_UNEXPECTED")
    markets_data, markets_snapshot = _data(markets_payload)
    if not isinstance(markets_data, dict):
        raise RuntimeError("ODDS_API_MARKET_DISCOVERY_DATA_NOT_OBJECT")
    market_bookmakers = markets_data.get("bookmakers", [])
    if not isinstance(market_bookmakers, list):
        raise RuntimeError("ODDS_API_MARKET_DISCOVERY_BOOKMAKERS_NOT_LIST")
    available_markets = {
        str(market.get("key"))
        for bookmaker in market_bookmakers if isinstance(bookmaker, dict)
        for market in (bookmaker.get("markets") or []) if isinstance(market, dict) and market.get("key")
    }
    if not isinstance(markets_snapshot, str) or _utc(markets_snapshot) > _utc(KICKOFF_AT):
        raise RuntimeError("ODDS_API_MARKET_DISCOVERY_SNAPSHOT_NOT_PRE_KICKOFF")
    if MARKET not in available_markets:
        return {
            "status": "APPROVED_LEAGUE_THREE_WAY_MARKET_NOT_AVAILABLE",
            "sport_key": SPORT,
            "event_id": event_id,
            "markets_snapshot_timestamp": markets_snapshot,
            "available_market_keys": sorted(available_markets),
            "credits_spent_this_run": events_env.quota_evidence.requests_last + markets_env.quota_evidence.requests_last,
            "database_writes_this_run": 0,
            "raw_prices_in_artifact": False,
        }

    if markets_env.quota_evidence.requests_remaining is None or markets_env.quota_evidence.requests_remaining < MIN_REMAINING_BEFORE_SPEND:
        return {
            "status": "PRICE_CAPTURE_SKIPPED_LOW_QUOTA",
            "sport_key": SPORT,
            "event_id": event_id,
            "available_market_keys": sorted(available_markets),
            "credits_spent_this_run": 2,
            "quota_requests_remaining": markets_env.quota_evidence.requests_remaining,
            "database_writes_this_run": 0,
            "raw_prices_in_artifact": False,
        }

    odds_path = (
        f"/historical/sports/{SPORT}/events/{event_id}/odds?"
        + urlencode({"date": KICKOFF_AT, "regions": REGION, "markets": MARKET})
    )
    odds_payload, odds_body, odds_headers, odds_env, odds_req, odds_got = _fetch_json(odds_path, api_key)
    expected_cost = 10
    if odds_env.quota_evidence.requests_last != expected_cost:
        raise RuntimeError("ODDS_API_HISTORICAL_PRICE_COST_NOT_TEN")
    if odds_env.quota_evidence.requests_remaining != markets_env.quota_evidence.requests_remaining - expected_cost:
        raise RuntimeError("ODDS_API_HISTORICAL_PRICE_QUOTA_DELTA_UNEXPECTED")
    total_credits = (
        events_env.quota_evidence.requests_last
        + markets_env.quota_evidence.requests_last
        + odds_env.quota_evidence.requests_last
    )
    if total_credits > MAX_CREDITS:
        raise RuntimeError("ODDS_API_PILOT_CREDIT_CAP_EXCEEDED")
    odds_data, snapshot_raw = _data(odds_payload)
    if not isinstance(odds_data, dict):
        raise RuntimeError("ODDS_API_HISTORICAL_ODDS_DATA_NOT_OBJECT")
    snapshot = _utc(snapshot_raw) if isinstance(snapshot_raw, str) else None
    kickoff = _utc(KICKOFF_AT)
    if snapshot is None or snapshot > kickoff:
        raise RuntimeError("ODDS_API_SNAPSHOT_NOT_PRE_KICKOFF")
    if odds_data.get("id") != event_id:
        raise RuntimeError("ODDS_API_HISTORICAL_ODDS_EVENT_ID_MISMATCH")
    if odds_data.get("commence_time") != KICKOFF_AT:
        raise RuntimeError("ODDS_API_HISTORICAL_ODDS_KICKOFF_MISMATCH")
    if _normalize(odds_data.get("home_team", "")) != _normalize(HOME_TEAM) or _normalize(odds_data.get("away_team", "")) != _normalize(AWAY_TEAM):
        raise RuntimeError("ODDS_API_HISTORICAL_ODDS_TEAM_IDENTITY_MISMATCH")

    summary = _market_summary(odds_data, kickoff, HOME_TEAM, AWAY_TEAM)
    if (
        MARKET not in summary["market_keys"]
        or summary["bookmaker_count"] == 0
        or summary["complete_three_way_sportsbooks"] == 0
    ):
        raise RuntimeError("ODDS_API_HISTORICAL_NO_COMPLETE_BOOKMAKER_1X2")
    quality = (
        "QUARANTINED_POST_KICKOFF_QUOTE_TIMESTAMPS"
        if summary["post_kickoff_quote_count"] else
        "QUARANTINED_MISSING_QUOTE_TIMESTAMPS"
        if summary["missing_quote_timestamps"] else
        "PRE_KICKOFF_TIMESTAMPED_SAMPLE_REVIEW_REQUIRED"
    )
    endpoint = f"/v4/historical/sports/{SPORT}/events/{event_id}/odds"
    request_params = {
        "sport_key": SPORT, "event_id": event_id, "date": KICKOFF_AT,
        "regions": REGION, "markets": MARKET,
    }
    response = ProviderResponse(
        provider=PROVIDER, source_id=SOURCE_ID, endpoint=endpoint,
        request_id=request_id, request_params=request_params, http_status=200,
        raw_body=odds_body, response_headers=odds_headers, fetched_at_utc=odds_got,
    )
    provider_entity_id = f"{event_id}:{MARKET}:{REGION}:{snapshot.isoformat()}"
    payload = {
        "schema_version": "veltrix-v2-the-odds-api-historical-snapshot-v1",
        "source_approval_id": approval.approval_id,
        "sport_key": SPORT,
        "canonical_fixture_id": CANONICAL_FIXTURE_ID,
        "canonical_provider_fixture_id": CANONICAL_PROVIDER_FIXTURE_ID,
        "event_id": event_id,
        "home_team": HOME_TEAM,
        "away_team": AWAY_TEAM,
        "kickoff_at": KICKOFF_AT,
        "snapshot_timestamp": snapshot.isoformat(),
        "requested_snapshot_at": KICKOFF_AT,
        "region": REGION,
        "market": MARKET,
        "provider_response_sha256": response.response_sha256,
        "quota": {
            "requests_used": odds_env.quota_evidence.requests_used,
            "requests_remaining": odds_env.quota_evidence.requests_remaining,
            "requests_last": odds_env.quota_evidence.requests_last,
        },
        "event_discovery": {
            "snapshot_timestamp": events_snapshot,
            "response_sha256": hashlib.sha256(events_body).hexdigest(),
            "request_cost": events_env.quota_evidence.requests_last,
        },
        "market_discovery": {
            "snapshot_timestamp": markets_snapshot,
            "response_sha256": hashlib.sha256(markets_body).hexdigest(),
            "request_cost": markets_env.quota_evidence.requests_last,
            "available_market_keys": sorted(available_markets),
        },
        "quality_status": quality,
        **summary,
        "point_in_time_certifiable": False,
        "raw_prices_stored_in_staging_only": True,
        "raw_prices_in_artifact": False,
    }
    response_id, observation_id = _persist_staging(
        staging_dsn, approval, response, payload, provider_entity_id, snapshot, kickoff,
    )
    return {
        "status": "CAPTURED_STAGING_RAW_ONLY_PIT_REVIEW_REQUIRED",
        "provider": PROVIDER,
        "source_id": SOURCE_ID,
        "approval_id": approval.approval_id,
        "canonical_fixture_id": CANONICAL_FIXTURE_ID,
        "canonical_provider_fixture_id": CANONICAL_PROVIDER_FIXTURE_ID,
        "event_id": event_id,
        "sport_key": SPORT,
        "market": MARKET,
        "region": REGION,
        "snapshot_timestamp": snapshot.isoformat(),
        "kickoff_at": KICKOFF_AT,
        "seconds_before_kickoff": (kickoff - snapshot).total_seconds(),
        "quality_status": quality,
        "bookmaker_count": summary["bookmaker_count"],
        "sportsbook_count": summary["sportsbook_count"],
        "exchange_count": summary["exchange_count"],
        "complete_three_way_sportsbooks": summary["complete_three_way_sportsbooks"],
        "market_keys": summary["market_keys"],
        "quote_update_min": summary["quote_update_min"],
        "quote_update_max": summary["quote_update_max"],
        "post_kickoff_quote_count": summary["post_kickoff_quote_count"],
        "missing_quote_timestamps": summary["missing_quote_timestamps"],
        "quota_requests_used": odds_env.quota_evidence.requests_used,
        "quota_requests_remaining": odds_env.quota_evidence.requests_remaining,
        "credits_spent_this_run": (
            events_env.quota_evidence.requests_last
            + markets_env.quota_evidence.requests_last
            + odds_env.quota_evidence.requests_last
        ),
        "provider_response_id": response_id,
        "source_observation_id": observation_id,
        "provider_response_sha256": response.response_sha256,
        "source_payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "point_in_time_certifiable": False,
        "normalized_odds_quote_rows_written": 0,
        "production_writes": 0,
        "predictions_changed": 0,
        "telegram_sent": False,
        "value_betting": "LOCKED",
        "raw_prices_in_artifact": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_capture(
        os.environ.get("THE_ODDS_API_KEY", ""),
        os.environ.get("VELTRIX_STAGING_DATABASE_URL", ""),
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {
        "CAPTURED_STAGING_RAW_ONLY_PIT_REVIEW_REQUIRED",
        "ALREADY_CAPTURED",
        "APPROVED_LEAGUE_EVENT_NOT_UNIQUELY_FOUND",
        "APPROVED_LEAGUE_THREE_WAY_MARKET_NOT_AVAILABLE",
        "PRICE_CAPTURE_SKIPPED_LOW_QUOTA",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
