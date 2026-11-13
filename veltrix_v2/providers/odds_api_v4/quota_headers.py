"""Strict offline parser for The Odds API quota response headers."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from collections.abc import Iterable


_HEADER_NAMES = (
    "x-requests-used",
    "x-requests-remaining",
    "x-requests-last",
)
_DECIMAL = re.compile(r"^[0-9]+$")


@dataclass(frozen=True)
class ParsedQuotaHeaders:
    raw_headers: tuple[tuple[str, str], ...]
    requests_used: int | None
    requests_remaining: int | None
    requests_last: int | None
    evidence_sha256: str
    reason_codes: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return (
            not self.reason_codes
            and self.requests_used is not None
            and self.requests_remaining is not None
            and self.requests_last is not None
        )


def parse_quota_headers(
    headers: Iterable[tuple[str, str]],
) -> ParsedQuotaHeaders:
    """Parse only the three documented quota headers.

    Header names are case-insensitive. Values are retained verbatim after
    UTF-8 decoding by the HTTP boundary; surrounding HTTP whitespace is
    permitted for integer parsing but retained in the evidence record.
    Missing, duplicate, non-string and malformed values remain unknown.
    Unknown header names are ignored and never persisted by this parser.
    """
    selected: dict[str, list[str]] = {name: [] for name in _HEADER_NAMES}
    reasons: list[str] = []

    try:
        pairs = list(headers)
    except (TypeError, ValueError):
        pairs = []
        reasons.append("QUOTA_HEADERS_INPUT_INVALID")

    for pair in pairs:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            reasons.append("QUOTA_HEADER_PAIR_INVALID")
            continue
        name, value = pair
        if not isinstance(name, str) or not isinstance(value, str):
            reasons.append("QUOTA_HEADER_VALUE_TYPE_INVALID")
            continue
        normalized = name.strip().lower()
        if normalized in selected:
            selected[normalized].append(value)

    parsed: dict[str, int | None] = {}
    retained: list[tuple[str, str]] = []
    for name in _HEADER_NAMES:
        values = selected[name]
        if not values:
            reasons.append(f"{name.upper().replace('-', '_')}_MISSING")
            parsed[name] = None
        elif len(values) != 1:
            reasons.append(f"{name.upper().replace('-', '_')}_DUPLICATE")
            parsed[name] = None
        else:
            raw = values[0]
            retained.append((name, raw))
            candidate = raw.strip(" \t")
            if not _DECIMAL.fullmatch(candidate):
                reasons.append(f"{name.upper().replace('-', '_')}_MALFORMED")
                parsed[name] = None
            else:
                parsed[name] = int(candidate)

    evidence = {
        "format": "veltrix-quota-headers-v1",
        "headers": retained,
    }
    encoded = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()

    return ParsedQuotaHeaders(
        raw_headers=tuple(retained),
        requests_used=parsed["x-requests-used"],
        requests_remaining=parsed["x-requests-remaining"],
        requests_last=parsed["x-requests-last"],
        evidence_sha256=digest,
        reason_codes=tuple(sorted(set(reasons))),
    )
