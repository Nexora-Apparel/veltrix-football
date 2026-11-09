"""Deterministic, read-only reconciliation of StrikerAPI and 5DollarFootballAPI JSON exports.

Input files are explicit provider envelopes. This tool never calls an API or database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("kickoff timestamp must include a timezone")
    return parsed.astimezone(__import__("datetime").timezone.utc)


def payload_hash(row: dict) -> str:
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def striker_record(row: dict, league_key: str) -> dict:
    home, away = row.get("home") or {}, row.get("away") or {}
    return {
        "provider": "strikerapi",
        "source_id": str(row.get("game_id", "")),
        "competition_key": league_key,
        "home_id": str(home.get("team_id", "")),
        "away_id": str(away.get("team_id", "")),
        "home": str(home.get("name", "")),
        "away": str(away.get("name", "")),
        "kickoff": str(row.get("starts_at", "")),
        "status": str(row.get("status", "")),
        "home_score": home.get("score"),
        "away_score": away.get("score"),
        "payload_sha256": payload_hash(row),
        "raw": row,
    }


def fivedollar_record(row: dict) -> dict:
    teams, goals = row.get("teams") or {}, row.get("goals") or {}
    home, away = teams.get("home") or {}, teams.get("away") or {}
    league = row.get("league") or {}
    return {
        "provider": "fivedollar",
        "source_id": str(row.get("id", "")),
        "competition_key": str(league.get("id", "")),
        "home_id": str(home.get("id", "")),
        "away_id": str(away.get("id", "")),
        "home": str(home.get("name", "")),
        "away": str(away.get("name", "")),
        "kickoff": str(row.get("kickoff_utc", "")),
        "status": str(row.get("status", "")),
        "home_score": goals.get("home"),
        "away_score": goals.get("away"),
        "payload_sha256": payload_hash(row),
        "raw": row,
    }


def valid_identity(record: dict) -> bool:
    if not all(record.get(k) for k in ("source_id", "home", "away", "kickoff")):
        return False
    try:
        parse_utc(record["kickoff"])
    except (TypeError, ValueError):
        return False
    return True


def reconcile(striker_rows: list[dict], dollar_rows: list[dict], competition_map: dict,
              tolerance_seconds: int = 300) -> dict:
    """Return source-level accounting and candidate decisions; never merge records."""
    left, right = [], []
    for row in striker_rows:
        if not valid_identity(row):
            left.append({**row, "_invalid": True})
        else:
            left.append(row)
    for row in dollar_rows:
        if not valid_identity(row):
            right.append({**row, "_invalid": True})
        else:
            right.append(row)

    left_ids = [r["source_id"] for r in left if not r.get("_invalid")]
    right_ids = [r["source_id"] for r in right if not r.get("_invalid")]
    duplicate_left = sorted({x for x in left_ids if left_ids.count(x) > 1})
    duplicate_right = sorted({x for x in right_ids if right_ids.count(x) > 1})

    edges: dict[tuple[int, int], tuple[str, int]] = {}
    for i, s in enumerate(left):
        if s.get("_invalid") or s["competition_key"] not in competition_map:
            continue
        expected_dollar_comp = str(competition_map[s["competition_key"]])
        for j, d in enumerate(right):
            if d.get("_invalid") or d["competition_key"] != expected_dollar_comp:
                continue
            delta = abs((parse_utc(s["kickoff"]) - parse_utc(d["kickoff"])).total_seconds())
            same = (normalize_name(s["home"]) == normalize_name(d["home"]) and
                    normalize_name(s["away"]) == normalize_name(d["away"]))
            reversed_teams = (normalize_name(s["home"]) == normalize_name(d["away"]) and
                              normalize_name(s["away"]) == normalize_name(d["home"]))
            if same and delta <= tolerance_seconds:
                edges[(i, j)] = ("candidate", int(delta))
            elif reversed_teams and delta <= tolerance_seconds:
                edges[(i, j)] = ("orientation_conflict", int(delta))

    left_degree, right_degree = {}, {}
    for i, j in edges:
        left_degree[i] = left_degree.get(i, 0) + 1
        right_degree[j] = right_degree.get(j, 0) + 1

    used_left, used_right, decisions = set(), set(), []
    quarantined_left, quarantined_right = set(), set()
    for (i, j), (kind, delta) in sorted(edges.items()):
        s, d = left[i], right[j]
        if kind == "orientation_conflict":
            quarantined_left.add(i); quarantined_right.add(j)
            decisions.append({"outcome": "IDENTITY_CONFLICT", "striker": s, "fivedollar": d,
                              "kickoff_delta_seconds": delta, "reason": "home_away_orientation_reversed"})
            continue
        if left_degree.get(i, 0) > 1 or right_degree.get(j, 0) > 1:
            quarantined_left.add(i); quarantined_right.add(j)
            decisions.append({"outcome": "AMBIGUOUS_MULTIPLE_CANDIDATES", "striker": s, "fivedollar": d,
                              "kickoff_delta_seconds": delta, "reason": "candidate_graph_degree_exceeds_one"})
            continue
        used_left.add(i); used_right.add(j)
        if s["status"] != ("finished" if d["status"] == "finished" else d["status"]):
            outcome, reason = "STATUS_CONFLICT", "provider_status_disagreement"
        elif s["status"] == "final" and d["status"] == "finished" and (
            s.get("home_score") != d.get("home_score") or s.get("away_score") != d.get("away_score")
        ):
            outcome, reason = "RESULT_CONFLICT", "final_score_disagreement"
        else:
            outcome, reason = "MATCHED_UNIQUE", "competition_teams_orientation_and_kickoff_match"
        if outcome in ("STATUS_CONFLICT", "RESULT_CONFLICT"):
            quarantined_left.add(i); quarantined_right.add(j)
        decisions.append({"outcome": outcome, "striker": s, "fivedollar": d,
                          "kickoff_delta_seconds": delta, "reason": reason})

    for i, s in enumerate(left):
        if i not in used_left and i not in quarantined_left:
            decisions.append({"outcome": "UNMATCHED_STRIKER_ONLY", "striker": s,
                              "fivedollar": None, "reason": "no_unique_candidate"})
    for j, d in enumerate(right):
        if j not in used_right and j not in quarantined_right:
            decisions.append({"outcome": "UNMATCHED_5DOLLAR_ONLY", "striker": None,
                              "fivedollar": d, "reason": "no_unique_candidate"})

    matched_left = sum(x["outcome"] == "MATCHED_UNIQUE" for x in decisions)
    matched_right = matched_left
    unmatched_left = sum(x["outcome"] == "UNMATCHED_STRIKER_ONLY" for x in decisions)
    unmatched_right = sum(x["outcome"] == "UNMATCHED_5DOLLAR_ONLY" for x in decisions)
    quarantine_outcomes = {"AMBIGUOUS_MULTIPLE_CANDIDATES", "IDENTITY_CONFLICT", "STATUS_CONFLICT", "RESULT_CONFLICT"}
    q_left = sum(x["outcome"] in quarantine_outcomes and x.get("striker") is not None for x in decisions)
    q_right = sum(x["outcome"] in quarantine_outcomes and x.get("fivedollar") is not None for x in decisions)
    return {
        "schema_version": 1,
        "mode": "read_only_no_merge",
        "tolerance_seconds": tolerance_seconds,
        "competition_map_striker_to_fivedollar": competition_map,
        "source_counts": {"striker": len(left), "fivedollar": len(right)},
        "duplicate_source_ids": {"striker": duplicate_left, "fivedollar": duplicate_right},
        "accounting": {
            "striker": {"total": len(left), "matched": matched_left, "unmatched": unmatched_left,
                        "quarantined": q_left, "balanced": len(left) == matched_left + unmatched_left + q_left},
            "fivedollar": {"total": len(right), "matched": matched_right, "unmatched": unmatched_right,
                           "quarantined": q_right, "balanced": len(right) == matched_right + unmatched_right + q_right},
        },
        "decisions": decisions,
    }


def load_envelope(path: str, provider: str) -> tuple[list[dict], dict]:
    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), (dict, list)):
        raise ValueError(f"{provider} input must be an envelope with a data object or array")
    if provider == "strikerapi":
        league_key = envelope.get("league_key")
        games = envelope["data"].get("games") if isinstance(envelope["data"], dict) else None
        if not isinstance(league_key, str) or not isinstance(games, list):
            raise ValueError("StrikerAPI envelope requires league_key and data.games")
        return [striker_record(x, league_key) for x in games], envelope
    rows = envelope["data"]
    if not isinstance(rows, list):
        raise ValueError("5Dollar envelope data must be an array")
    return [fivedollar_record(x) for x in rows], envelope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--striker", required=True, help="StrikerAPI JSON envelope")
    parser.add_argument("--fivedollar", required=True, help="5DollarFootballAPI JSON envelope")
    parser.add_argument("--competition-map", required=True, help="JSON object mapping Striker league key to verified 5Dollar league ID")
    parser.add_argument("--output", required=True, help="Output report JSON path")
    args = parser.parse_args()
    striker, s_meta = load_envelope(args.striker, "strikerapi")
    dollar, d_meta = load_envelope(args.fivedollar, "fivedollar")
    mapping = json.loads(Path(args.competition_map).read_text(encoding="utf-8"))
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("competition map must be a non-empty JSON object")
    report = reconcile(striker, dollar, mapping)
    report["provenance"] = {
        "striker_retrieved_at": s_meta.get("retrieved_at"),
        "striker_query": s_meta.get("query"),
        "fivedollar_retrieved_at": d_meta.get("retrieved_at"),
        "fivedollar_query": d_meta.get("query"),
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RECONCILIATION_REPORT: {args.output}")
    print(f"STRIKER_BALANCED: {report['accounting']['striker']['balanced']}")
    print(f"FIVEDOLLAR_BALANCED: {report['accounting']['fivedollar']['balanced']}")
    print("DATABASE_WRITES: 0; CANONICAL_MERGES: 0")
    return 0 if all(v["balanced"] for v in report["accounting"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
