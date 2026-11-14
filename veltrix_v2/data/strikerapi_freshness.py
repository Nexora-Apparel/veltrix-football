"""Parse StrikerAPI's public dataset-freshness changelog as timestamp evidence.

This module is offline-only: callers provide the exact archived HTML bytes and
the time those bytes were retrieved. Dataset-level freshness is not a per-record
revision timestamp and never proves historical revision completeness.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, ...]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join(" ".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(tuple(self._row))
            self._row = None
            self._cell = None


@dataclass(frozen=True, slots=True)
class StrikerDatasetFreshnessEvidence:
    dataset_name: str
    through_date: str | None
    written_at: datetime
    retrieved_at: datetime
    changelog_sha256: str
    timestamp_basis: str = "provider_dataset_refresh"


def parse_striker_dataset_freshness(
    raw_changelog: bytes,
    *,
    retrieved_at: datetime,
    dataset_name: str = "Fixtures, results and box scores",
) -> StrikerDatasetFreshnessEvidence:
    """Extract the provider's dataset-level Written timestamp from raw HTML."""
    if not isinstance(raw_changelog, bytes) or not raw_changelog:
        raise ValueError("STRIKER_CHANGELOG_RAW_BYTES_REQUIRED")
    if not isinstance(retrieved_at, datetime) or retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("STRIKER_CHANGELOG_RETRIEVAL_TIME_UNTRUSTED")
    try:
        html = raw_changelog.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("STRIKER_CHANGELOG_ENCODING_INVALID") from None

    parser = _TableParser()
    parser.feed(html)
    parser.close()
    selected = None
    for row in parser.rows:
        if len(row) >= 3 and row[0].startswith(dataset_name):
            selected = row
            break
    if selected is None:
        raise ValueError("STRIKER_DATASET_FRESHNESS_ROW_MISSING")

    through = selected[1] or None
    written_text = selected[2]
    try:
        written_at = datetime.strptime(
            written_text, "%Y-%m-%d %H:%M UTC"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError("STRIKER_DATASET_WRITTEN_TIMESTAMP_INVALID") from None
    if written_at > retrieved_at.astimezone(timezone.utc):
        raise ValueError("STRIKER_DATASET_WRITTEN_AFTER_RETRIEVAL")

    return StrikerDatasetFreshnessEvidence(
        dataset_name=dataset_name,
        through_date=through,
        written_at=written_at,
        retrieved_at=retrieved_at.astimezone(timezone.utc),
        changelog_sha256=sha256(raw_changelog).hexdigest(),
    )
