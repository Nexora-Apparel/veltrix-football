#!/usr/bin/env python3
"""Offline ingestion of an archived The Odds API event into a local odds ledger.

No network, provider credentials, database, prediction publication or Telegram
side effects are available from this command.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bookmaker_odds_evidence import (
    BookmakerOddsEvidenceError, append_odds_observations,
)
from app.the_odds_api_evidence_adapter import (
    OddsProviderAdapterError, adapt_the_odds_api_event,
)


class OfflineOddsIngestError(RuntimeError):
    pass


def _read_json(path: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise OfflineOddsIngestError("input_json_unreadable") from None
    if not isinstance(value, dict):
        raise OfflineOddsIngestError("input_json_must_be_object")
    return value


def _atomic_write_json(path: str, value: dict) -> None:
    destination = Path(path)
    if destination.is_symlink():
        raise OfflineOddsIngestError("ledger_destination_symlink_rejected")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not destination.is_file():
        raise OfflineOddsIngestError("ledger_destination_not_regular_file")
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def ingest(*, event_path: str, crosswalk_path: str, retrieved_at: str,
           source_payload_sha256: str, ledger_path: str,
           max_quote_age_seconds: int = 86400) -> dict:
    event = _read_json(event_path)
    crosswalk = _read_json(crosswalk_path)
    destination = Path(ledger_path)
    if destination.exists():
        ledger = _read_json(ledger_path)
    else:
        ledger = {"schema_version": 1, "observations": []}
    try:
        collection = adapt_the_odds_api_event(
            event_payload=event,
            crosswalk=crosswalk,
            retrieved_at=retrieved_at,
            source_payload_sha256=source_payload_sha256,
            max_quote_age_seconds=max_quote_age_seconds,
        )
        merged = append_odds_observations(
            ledger=ledger, observations=collection["observations"],
        )
    except (OddsProviderAdapterError, BookmakerOddsEvidenceError) as exc:
        raise OfflineOddsIngestError(str(exc)) from None
    _atomic_write_json(ledger_path, merged["ledger"])
    return {
        "valid": True,
        "provider_event_id": collection["provider_event_id"],
        "fixture_id": collection["fixture_id"],
        "observations_received": collection["observation_count"],
        "observations_rejected": collection["rejected_count"],
        "observations_added": merged["added_count"],
        "total_observations": merged["total_observation_count"],
        "rejected_reasons": collection["rejected"],
        "network_requests": 0,
        "database_writes": 0,
        "prediction_publications": 0,
        "telegram_deliveries": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-json", required=True)
    parser.add_argument("--crosswalk-json", required=True)
    parser.add_argument("--retrieved-at", required=True,
                        help="Timezone-aware ISO-8601 retrieval timestamp")
    parser.add_argument("--source-payload-sha256", required=True,
                        help="SHA-256 of the exact archived HTTP response bytes")
    parser.add_argument("--ledger-json", required=True)
    parser.add_argument("--max-quote-age-seconds", type=int, default=86400)
    args = parser.parse_args()
    try:
        result = ingest(
            event_path=args.event_json,
            crosswalk_path=args.crosswalk_json,
            retrieved_at=args.retrieved_at,
            source_payload_sha256=args.source_payload_sha256,
            ledger_path=args.ledger_json,
            max_quote_age_seconds=args.max_quote_age_seconds,
        )
        print("ODDS_EVIDENCE_INGEST: PASS; " + json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, OfflineOddsIngestError) as exc:
        print(f"ODDS_EVIDENCE_INGEST: FAIL ({type(exc).__name__}: {str(exc)[:160]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
