"""Public CSV adapter for Open Matchday (2026/27, non-commercial use).

This optional source supplements fixtures/results; it does not replace the archive
and does not provide bookmaker odds.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from typing import Any, Iterable

import requests

from app.multi_source import FixtureRecord


class OpenMatchdayError(RuntimeError):
    """Safe, source-specific data error."""


class OpenMatchdayClient:
    BASE_URL = "https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data"
    TREE_URL = "https://api.github.com/repos/oladeeayo/open-matchday/git/trees/master?recursive=1"
    SEASON = "2627"
    SOURCE = "open-matchday"
    # The dataset documents a fixed UTC+1 convention for kickoff times.
    DATA_TIMEZONE = timezone(timedelta(hours=1))

    def __init__(self, timeout: int = 20, session: Any = None):
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "text/csv, application/json", "User-Agent": "VeltrixFootball/1.0"})

    def competition_paths(self) -> list[str]:
        """Discover folders with at least one current-season CSV."""
        try:
            response = self.session.get(self.TREE_URL, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OpenMatchdayError(f"Open Matchday index request failed: {exc.__class__.__name__}.") from None
        tree = payload.get("tree") if isinstance(payload, dict) else None
        if not isinstance(tree, list):
            raise OpenMatchdayError("Open Matchday index had an unexpected shape.")
        return sorted({
            item["path"].split("/")[1]
            for item in tree
            if isinstance(item, dict)
            and item.get("type") == "blob"
            and item.get("path", "").startswith("data/")
            and item["path"].endswith("_2627.csv")
        })

    def _read_csv(self, competition: str, kind: str) -> list[dict[str, str]]:
        if not competition or "/" in competition or "\\" in competition or kind not in {"fixtures", "results"}:
            raise ValueError("Provide a competition folder and kind='fixtures' or 'results'.")
        url = f"{self.BASE_URL}/{competition}/{kind}_{self.SEASON}.csv"
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise OpenMatchdayError(f"Open Matchday {kind} request failed: {exc.__class__.__name__}.") from None
        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            raise OpenMatchdayError(f"Open Matchday {kind} request failed with HTTP {response.status_code}.")
        try:
            return list(csv.DictReader(StringIO(response.text)))
        except (csv.Error, UnicodeError):
            raise OpenMatchdayError("Open Matchday returned malformed CSV.") from None

    @classmethod
    def _kickoff(cls, day: str, time: str) -> str | None:
        try:
            local = datetime.strptime(f"{day} {time or '12:00'}", "%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            return None
        return local.replace(tzinfo=cls.DATA_TIMEZONE).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def fetch_records(
        self,
        competitions: Iterable[str],
        start_date: date,
        end_date: date,
    ) -> list[FixtureRecord]:
        """Fetch records in an inclusive date range from explicit competition folders.

        Example folder: ENG_1_premier-league. Fixture IDs are deterministic,
        source-local keys. Results require valid non-negative full-time scores.
        """
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        records: list[FixtureRecord] = []
        for competition in sorted(set(competitions)):
            for kind in ("fixtures", "results"):
                for row in self._read_csv(competition, kind):
                    try:
                        day = date.fromisoformat(str(row.get("date") or "").strip())
                    except ValueError:
                        continue
                    if not start_date <= day <= end_date:
                        continue
                    home, away = str(row.get("home") or "").strip(), str(row.get("away") or "").strip()
                    kickoff = self._kickoff(day.isoformat(), str(row.get("time") or "").strip())
                    if not home or not away or not kickoff:
                        continue
                    hg = ag = None
                    status = "NS"
                    if kind == "results":
                        try:
                            hg, ag = int(row["ft_home"]), int(row["ft_away"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        if hg < 0 or ag < 0:
                            continue
                        status = "FT"
                    source_id = f"{competition}:{day.isoformat()}:{home}:{away}"
                    records.append(FixtureRecord(
                        source=self.SOURCE,
                        source_id=source_id,
                        kickoff=kickoff,
                        home=home,
                        away=away,
                        competition=competition,
                        season=self.SEASON,
                        status=status,
                        home_goals=hg,
                        away_goals=ag,
                        raw={"provider": self.SOURCE, "kind": kind, "gameweek": row.get("gw")},
                    ))
        return records
