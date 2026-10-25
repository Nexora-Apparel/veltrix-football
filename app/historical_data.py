"""Historical fixture cleaning and leakage-safe rolling team features."""
from __future__ import annotations
import csv
from collections import defaultdict, deque
from datetime import date
from pathlib import Path
from typing import Any, Iterable

FINISHED_STATUSES = {"FT", "AET", "PEN"}

def completed_fixture_rows(fixtures: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in fixtures:
        fixture = item.get("fixture") or {}
        status = (fixture.get("status") or {}).get("short")
        teams, goals, league = item.get("teams") or {}, item.get("goals") or {}, item.get("league") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        hg, ag = goals.get("home"), goals.get("away")
        if status not in FINISHED_STATUSES or not isinstance(home.get("id"), int) or not isinstance(away.get("id"), int):
            continue
        if not isinstance(hg, int) or not isinstance(ag, int) or not fixture.get("date"):
            continue
        rows.append({"fixture_id": fixture.get("id"), "kickoff_utc": fixture["date"],
          "league_id": league.get("id"), "league_name": league.get("name"), "season": league.get("season"),
          "home_team_id": home["id"], "home_team": home.get("name", ""),
          "away_team_id": away["id"], "away_team": away.get("name", ""),
          "home_goals": hg, "away_goals": ag, "status": status})
    return sorted(rows, key=lambda r: (r["kickoff_utc"], r["fixture_id"] or 0))

def add_leakage_safe_rolling_features(matches: Iterable[dict[str, Any]], window: int = 5) -> list[dict[str, Any]]:
    """Features for each match use only that team's earlier completed matches."""
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ValueError("window must be a positive integer")
    ordered = sorted(matches, key=lambda r: (r["kickoff_utc"], r.get("fixture_id") or 0))
    history: dict[tuple[int, int], deque[tuple[int, int]]] = defaultdict(lambda: deque(maxlen=window))
    output = []
    for match in ordered:
        lid, hid, aid = int(match["league_id"] or 0), int(match["home_team_id"]), int(match["away_team_id"])
        hh, ah = history[(lid, hid)], history[(lid, aid)]
        row = dict(match)
        row["rolling_window"] = window
        for prefix, hist in (("home", hh), ("away", ah)):
            row[f"{prefix}_prior_matches"] = len(hist)
            row[f"{prefix}_avg_goals_for"] = _mean([gf for gf, _ in hist])
            row[f"{prefix}_avg_goals_against"] = _mean([ga for _, ga in hist])
            row[f"{prefix}_points_per_match"] = _ppm(hist)
        output.append(row)
        hg, ag = int(match["home_goals"]), int(match["away_goals"])
        history[(lid, hid)].append((hg, ag))
        history[(lid, aid)].append((ag, hg))
    return output

def _mean(values: list[int]) -> float | None:
    return sum(values) / len(values) if values else None

def _ppm(history: deque[tuple[int, int]]) -> float | None:
    if not history: return None
    return sum(3 if gf > ga else 1 if gf == ga else 0 for gf, ga in history) / len(history)

def write_csv(rows: Iterable[dict[str, Any]], output_path: str | Path) -> int:
    rows = list(rows)
    if not rows: raise ValueError("No completed matches to write; no CSV was created.")
    path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return len(rows)

def validate_date_range(start: str, end: str) -> tuple[str, str]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if b < a: raise ValueError("--to must be on or after --from")
    if (b-a).days > 6: raise ValueError("Request at most 7 calendar days at a time to respect Highlightly's free API quota")
    return a.isoformat(), b.isoformat()
