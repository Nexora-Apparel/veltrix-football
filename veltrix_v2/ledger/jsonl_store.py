"""Durable append-only JSONL adapter for the prospective paper ledger.

The adapter writes only to an explicitly supplied local path. It never opens a
database, network connection, provider, or production service. A process lock,
O_APPEND, fsync and hash-chain verification protect each append.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Callable

from .paper_predictions import PaperLedgerEvent, PaperPrediction, ProspectivePaperLedger


class JsonlPaperLedgerStore:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> ProspectivePaperLedger:
        if not self.path.exists():
            return ProspectivePaperLedger()
        events = self._decode(self.path.read_text(encoding="utf-8"))
        return ProspectivePaperLedger(events)

    def append_prediction(self, prediction: PaperPrediction) -> PaperLedgerEvent:
        return self._locked_append(lambda ledger: ledger.append_prediction(prediction))

    def append_settlement(self, **kwargs) -> PaperLedgerEvent:
        return self._locked_append(lambda ledger: ledger.append_settlement(**kwargs))

    def _locked_append(self, operation: Callable[[ProspectivePaperLedger], PaperLedgerEvent]) -> PaperLedgerEvent:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_APPEND, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            os.lseek(descriptor, 0, os.SEEK_SET)
            chunks = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            current = b"".join(chunks).decode("utf-8")
            ledger = ProspectivePaperLedger(self._decode(current))
            event = operation(ledger)
            line = json.dumps({
                "sequence": event.sequence, "event_type": event.event_type,
                "fixture_id": event.fixture_id, "model_version": event.model_version,
                "recorded_at": event.recorded_at, "payload": event.payload,
                "previous_event_sha256": event.previous_event_sha256,
                "event_sha256": event.event_sha256,
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
            written = 0
            while written < len(line):
                written += os.write(descriptor, line[written:])
            os.fsync(descriptor)
            return event
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    @staticmethod
    def _decode(raw: str) -> list[PaperLedgerEvent]:
        events: list[PaperLedgerEvent] = []
        if not raw:
            return events
        for line_number, line in enumerate(raw.splitlines(), start=1):
            try:
                value = json.loads(line)
                event = PaperLedgerEvent(
                    sequence=value["sequence"], event_type=value["event_type"],
                    fixture_id=value["fixture_id"], model_version=value["model_version"],
                    recorded_at=value["recorded_at"], payload=value["payload"],
                    previous_event_sha256=value["previous_event_sha256"],
                    event_sha256=value["event_sha256"],
                )
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"PAPER_LEDGER_JSONL_CORRUPT_LINE_{line_number}") from exc
            events.append(event)
        return events
