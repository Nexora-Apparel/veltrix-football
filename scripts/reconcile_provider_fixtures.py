"Deterministic read-only reconciliation of StrikerAPI and 5DollarFootballAPI JSON exports."
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

from app.provider_team_aliases import validate_registry


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("kickoff timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("kickoff timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def payload_hash(row: dict) -> str:
    raw = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def striker_record(row: dict, league_key: str) -> dict:
    h, a = row.get("home") or {}, row.get("away") or {}
    source_id = row.get("game_id")
    return {"provider":"strikerapi","source_id":"" if source_id is None else str(source_id),
            "competition_key":league_key,"home_id":"" if h.get("team_id") is None else str(h.get("team_id")),
            "away_id":"" if a.get("team_id") is None else str(a.get("team_id")),
            "home":h.get("name") or "","away":a.get("name") or "",
            "kickoff":row.get("starts_at") or "","status":row.get("status") or "",
            "home_score":h.get("score"),"away_score":a.get("score"),
            "payload_sha256":payload_hash(row)}


def fivedollar_record(row: dict) -> dict:
    t, g, l = row.get("teams") or {}, row.get("goals") or {}, row.get("league") or {}
    h, a = t.get("home") or {}, t.get("away") or {}
    source_id = row.get("id")
    return {"provider":"fivedollar","source_id":"" if source_id is None else str(source_id),
            "competition_key":"" if l.get("id") is None else str(l.get("id")),
            "home_id":"" if h.get("id") is None else str(h.get("id")),
            "away_id":"" if a.get("id") is None else str(a.get("id")),
            "home":h.get("name") or "","away":a.get("name") or "",
            "kickoff":row.get("kickoff_utc") or "","status":row.get("status") or "",
            "home_score":g.get("home"),"away_score":g.get("away"),
            "payload_sha256":payload_hash(row)}


def valid_identity(row: dict) -> bool:
    if not all(isinstance(row.get(k), str) and row[k].strip()
               for k in ("source_id", "home", "away", "kickoff")):
        return False
    try:
        parse_utc(row["kickoff"])
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _duplicate_indexes(rows: list[dict]) -> tuple[set[int], list[str]]:
    counts = {}
    for row in rows:
        source_id = row.get("source_id")
        if isinstance(source_id, str) and source_id:
            counts[source_id] = counts.get(source_id, 0) + 1
    duplicate_ids = sorted(key for key, count in counts.items() if count > 1)
    indexes = {i for i, row in enumerate(rows) if row.get("source_id") in duplicate_ids}
    return indexes, duplicate_ids


def reconcile(striker_rows: list[dict], dollar_rows: list[dict], competition_map: dict,
              tolerance_seconds: int = 300, alias_registry: dict | None = None,
              alias_competition_key: str | None = None, season: str | None = None) -> dict:
    alias_pairs = set()
    if alias_registry is not None:
        if not alias_competition_key or not season:
            raise ValueError("alias registry requires explicit competition key and season scope")
        validate_registry(alias_registry)
        if alias_registry.get("status") == "approved":
            alias_pairs = {
                (row["competition_key"], row["season"],
                 row["striker_team_id"], row["fivedollar_team_id"])
                for row in alias_registry["candidates"]
                if row["status"] == "approved"
            }

    def approved_alias(striker_id: str, dollar_id: str) -> bool:
        return (alias_competition_key, season, str(striker_id), str(dollar_id)) in alias_pairs

    left, right = list(striker_rows), list(dollar_rows)
    invalid_left = {i for i, row in enumerate(left) if not valid_identity(row)}
    invalid_right = {j for j, row in enumerate(right) if not valid_identity(row)}
    duplicate_left, duplicate_left_ids = _duplicate_indexes(left)
    duplicate_right, duplicate_right_ids = _duplicate_indexes(right)

    edges, orientations, edge_methods = {}, {}, {}
    for i, s in enumerate(left):
        if i in invalid_left or i in duplicate_left or s.get("competition_key") not in competition_map:
            continue
        mapped = str(competition_map[s["competition_key"]])
        for j, d in enumerate(right):
            if j in invalid_right or j in duplicate_right or str(d.get("competition_key", "")) != mapped:
                continue
            delta = abs((parse_utc(s["kickoff"]) - parse_utc(d["kickoff"])).total_seconds())
            sh, sa, dh, da = map(normalize_name, (s["home"], s["away"], d["home"], d["away"]))
            home_name_match, away_name_match = sh == dh, sa == da
            home_alias_match = not home_name_match and approved_alias(s.get("home_id", ""), d.get("home_id", ""))
            away_alias_match = not away_name_match and approved_alias(s.get("away_id", ""), d.get("away_id", ""))
            if (home_name_match or home_alias_match) and (away_name_match or away_alias_match) and delta <= tolerance_seconds:
                edges[(i, j)] = int(delta)
                edge_methods[(i, j)] = {
                    "home": "approved_alias" if home_alias_match else "strict_name",
                    "away": "approved_alias" if away_alias_match else "strict_name",
                }
            else:
                reverse_home_alias = approved_alias(s.get("home_id", ""), d.get("away_id", ""))
                reverse_away_alias = approved_alias(s.get("away_id", ""), d.get("home_id", ""))
                if ((sh == da or reverse_home_alias) and (sa == dh or reverse_away_alias)
                        and delta <= tolerance_seconds):
                    orientations[(i, j)] = int(delta)

    left_degree, right_degree = {}, {}
    for i, j in edges:
        left_degree[i] = left_degree.get(i, 0) + 1
        right_degree[j] = right_degree.get(j, 0) + 1

    used_left, used_right = set(), set()
    quarantine_left = set(invalid_left) | set(duplicate_left)
    quarantine_right = set(invalid_right) | set(duplicate_right)
    decisions = []
    alias_pair_usage = defaultdict(int)
    alias_matched_fixtures = set()

    for i in sorted(invalid_left):
        decisions.append({"outcome":"INVALID_SOURCE_ROW","striker":left[i],"fivedollar":None,
                          "reason":"missing string identity or invalid timezone-aware kickoff"})
    for j in sorted(invalid_right):
        decisions.append({"outcome":"INVALID_SOURCE_ROW","striker":None,"fivedollar":right[j],
                          "reason":"missing string identity or invalid timezone-aware kickoff"})
    for i in sorted(duplicate_left):
        decisions.append({"outcome":"DUPLICATE_SOURCE_ID","striker":left[i],"fivedollar":None,
                          "reason":"StrikerAPI source ID occurs more than once in this export"})
    for j in sorted(duplicate_right):
        decisions.append({"outcome":"DUPLICATE_SOURCE_ID","striker":None,"fivedollar":right[j],
                          "reason":"5DollarFootballAPI source ID occurs more than once in this export"})

    # A reversed-orientation candidate is a conflict only when neither endpoint
    # has a valid-orientation candidate. This prevents double-counting a row.
    for (i, j), delta in sorted(orientations.items()):
        if i in left_degree or j in right_degree:
            continue
        quarantine_left.add(i)
        quarantine_right.add(j)
        decisions.append({"outcome":"IDENTITY_CONFLICT","striker":left[i],"fivedollar":right[j],
                          "kickoff_delta_seconds":delta,"reason":"home_away_orientation_reversed"})

    for (i, j), delta in sorted(edges.items()):
        s, d = left[i], right[j]
        if left_degree.get(i, 0) > 1 or right_degree.get(j, 0) > 1:
            quarantine_left.add(i)
            quarantine_right.add(j)
            decisions.append({"outcome":"AMBIGUOUS_MULTIPLE_CANDIDATES","striker":s,"fivedollar":d,
                              "kickoff_delta_seconds":delta,"reason":"candidate_graph_degree_exceeds_one"})
            continue
        used_left.add(i)
        used_right.add(j)
        striker_status = "finished" if s.get("status") == "final" else s.get("status")
        dollar_status = "finished" if d.get("status") == "finished" else d.get("status")
        if striker_status != dollar_status:
            outcome, reason = "STATUS_CONFLICT", "provider_status_disagreement"
        elif striker_status == "finished" and (
            s.get("home_score") != d.get("home_score") or s.get("away_score") != d.get("away_score")
        ):
            outcome, reason = "RESULT_CONFLICT", "final_score_disagreement"
        else:
            outcome, reason = "MATCHED_UNIQUE", "competition_teams_orientation_and_kickoff_match"
        if outcome in ("STATUS_CONFLICT", "RESULT_CONFLICT"):
            quarantine_left.add(i)
            quarantine_right.add(j)
        decision = {"outcome":outcome,"striker":s,"fivedollar":d,
                    "kickoff_delta_seconds":delta,"reason":reason,
                    "identity_evidence":edge_methods.get((i, j), {"home":"strict_name","away":"strict_name"})}
        decisions.append(decision)
        if outcome == "MATCHED_UNIQUE":
            methods = edge_methods.get((i, j), {})
            used_alias = False
            for side in ("home", "away"):
                if methods.get(side) == "approved_alias":
                    used_alias = True
                    pair = (s.get(f"{side}_id", ""), d.get(f"{side}_id", ""))
                    alias_pair_usage[pair] += 1
            if used_alias:
                alias_matched_fixtures.add((s["source_id"], d["source_id"]))

    for i, s in enumerate(left):
        if i not in used_left and i not in quarantine_left:
            decisions.append({"outcome":"UNMATCHED_STRIKER_ONLY","striker":s,"fivedollar":None,
                              "reason":"no unique candidate"})
    for j, d in enumerate(right):
        if j not in used_right and j not in quarantine_right:
            decisions.append({"outcome":"UNMATCHED_5DOLLAR_ONLY","striker":None,"fivedollar":d,
                              "reason":"no unique candidate"})

    matched_left = len(used_left - quarantine_left)
    matched_right = len(used_right - quarantine_right)
    unmatched_left = sum(x["outcome"] == "UNMATCHED_STRIKER_ONLY" for x in decisions)
    unmatched_right = sum(x["outcome"] == "UNMATCHED_5DOLLAR_ONLY" for x in decisions)
    accounting = {
        "striker":{"total":len(left),"matched":matched_left,"unmatched":unmatched_left,
                   "quarantined":len(quarantine_left),
                   "balanced":len(left) == matched_left + unmatched_left + len(quarantine_left)},
        "fivedollar":{"total":len(right),"matched":matched_right,"unmatched":unmatched_right,
                      "quarantined":len(quarantine_right),
                      "balanced":len(right) == matched_right + unmatched_right + len(quarantine_right)}
    }
    acceptance_pass = (
        accounting["striker"]["balanced"] and accounting["fivedollar"]["balanced"]
        and matched_left > 0 and matched_right > 0
        and accounting["striker"]["quarantined"] == 0
        and accounting["fivedollar"]["quarantined"] == 0
        and not duplicate_left_ids and not duplicate_right_ids
    )
    return {"schema_version":1,"mode":"read_only_no_merge","acceptance_pass":acceptance_pass,
            "tolerance_seconds":tolerance_seconds,"competition_map_striker_to_fivedollar":competition_map,
            "alias_scope":{"competition_key":alias_competition_key,"season":season,
                           "registry_status":alias_registry.get("status") if alias_registry else "not_loaded"},
            "alias_usage":{"alias_matched_fixture_count":len(alias_matched_fixtures),
                           "team_pair_uses":[{"striker_team_id":key[0],"fivedollar_team_id":key[1],"uses":value}
                                             for key,value in sorted(alias_pair_usage.items())]},
            "source_counts":{"striker":len(left),"fivedollar":len(right)},
            "duplicate_source_ids":{"striker":duplicate_left_ids,"fivedollar":duplicate_right_ids},
            "accounting":accounting,"decisions":decisions}


def load_envelope(path: str, provider: str):
    env = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(env, dict) or not isinstance(env.get("data"), (dict, list)):
        raise ValueError(f"{provider} input must be an envelope")
    if provider == "strikerapi":
        key = env.get("league_key")
        rows = env["data"].get("games") if isinstance(env["data"], dict) else None
        if not isinstance(key, str) or not key or not isinstance(rows, list):
            raise ValueError("Striker envelope requires league_key and data.games")
        return [striker_record(x, key) for x in rows], env
    rows = env["data"]
    if not isinstance(rows, list):
        raise ValueError("5Dollar envelope data must be an array")
    return [fivedollar_record(x) for x in rows], env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--striker", required=True)
    parser.add_argument("--fivedollar", required=True)
    parser.add_argument("--competition-map", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--alias-registry")
    parser.add_argument("--alias-competition-key")
    parser.add_argument("--season")
    args = parser.parse_args()
    striker, striker_meta = load_envelope(args.striker, "strikerapi")
    dollar, dollar_meta = load_envelope(args.fivedollar, "fivedollar")
    mapping = json.loads(Path(args.competition_map).read_text(encoding="utf-8"))
    if not isinstance(mapping, dict) or not mapping or any(
        not isinstance(k, str) or not k or v in (None, "") for k, v in mapping.items()
    ):
        raise ValueError("competition map must be a non-empty object with non-empty mappings")
    alias_registry = None
    if args.alias_registry:
        alias_registry = json.loads(Path(args.alias_registry).read_text(encoding="utf-8"))
    report = reconcile(
        striker, dollar, mapping, alias_registry=alias_registry,
        alias_competition_key=args.alias_competition_key, season=args.season,
    )
    report["provenance"] = {
        "striker_retrieved_at":striker_meta.get("retrieved_at"),
        "striker_query":striker_meta.get("query"),
        "fivedollar_retrieved_at":dollar_meta.get("retrieved_at"),
        "fivedollar_query":dollar_meta.get("query")
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RECONCILIATION_REPORT: {args.output}")
    print(f"STRIKER_BALANCED: {report['accounting']['striker']['balanced']}")
    print(f"FIVEDOLLAR_BALANCED: {report['accounting']['fivedollar']['balanced']}")
    print("DATABASE_WRITES: 0; CANONICAL_MERGES: 0")
    return 0 if report["acceptance_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
