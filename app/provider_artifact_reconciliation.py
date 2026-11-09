"""Offline reconciliation of verified acquisition artifacts; never imports data."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.provider_acquisition_artifact import validate_acquisition_report_file
from app.provider_team_aliases import load_registry, validate_registry


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("kickoff_missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("kickoff_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _record_valid(row: dict, provider: str) -> bool:
    required = ("source_id", "competition_key", "season", "home_team_source_id",
                "away_team_source_id", "home_team_name", "away_team_name",
                "kickoff_at", "normalized_status", "payload_sha256", "run_id")
    if not isinstance(row, dict) or row.get("provider") != provider:
        return False
    if any(not isinstance(row.get(key), str) or not row[key].strip() for key in required):
        return False
    try:
        _utc(row["kickoff_at"])
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _duplicates(rows: list[dict]) -> set[int]:
    counts: dict[str, int] = {}
    for row in rows:
        source_id = row.get("source_id")
        if isinstance(source_id, str) and source_id:
            counts[source_id] = counts.get(source_id, 0) + 1
    return {i for i, row in enumerate(rows) if counts.get(row.get("source_id"), 0) > 1}


def reconcile_artifact_records(
    striker_rows: list[dict],
    fivedollar_rows: list[dict],
    competition_map: dict[str, str],
    *,
    alias_registry: dict | None = None,
    alias_competition_key: str | None = None,
    season: str | None = None,
) -> dict:
    """Match only unique, same-orientation observations using exact IDs or names."""
    if not isinstance(competition_map, dict) or not competition_map:
        raise ValueError("competition_map_required")
    if alias_registry is not None:
        if not alias_competition_key or not season:
            raise ValueError("alias_scope_required")
        validate_registry(alias_registry)

    approved = set()
    if alias_registry and alias_registry.get("status") == "approved":
        approved = {
            (r["competition_key"], r["season"], r["striker_team_id"], r["fivedollar_team_id"])
            for r in alias_registry["candidates"] if r["status"] == "approved"
        }

    def alias_ok(sid: str, did: str, comp: str, sseason: str | None, dseason: str | None) -> bool:
        return (sseason is not None and dseason is not None and sseason == dseason
                and (comp, sseason, sid, did) in approved
                and comp == alias_competition_key and sseason == season)

    left, right = list(striker_rows), list(fivedollar_rows)
    invalid_l = {i for i, r in enumerate(left) if not _record_valid(r, "strikerapi")}
    invalid_r = {j for j, r in enumerate(right) if not _record_valid(r, "fivedollar")}
    dup_l, dup_r = _duplicates(left), _duplicates(right)
    invalid_l |= dup_l
    invalid_r |= dup_r
    edges: dict[tuple[int, int], dict] = {}
    reverse: list[tuple[int, int]] = []

    for i, s in enumerate(left):
        if i in invalid_l:
            continue
        mapped_comp = competition_map.get(s["competition_key"])
        if mapped_comp is None:
            continue
        for j, d in enumerate(right):
            if j in invalid_r or d["competition_key"] != str(mapped_comp):
                continue
            if s.get("season") != d.get("season"):
                continue
            if _utc(s["kickoff_at"]) != _utc(d["kickoff_at"]):
                continue
            same_home = _name(s["home_team_name"]) == _name(d["home_team_name"])
            same_away = _name(s["away_team_name"]) == _name(d["away_team_name"])
            home_alias = not same_home and alias_ok(
                s["home_team_source_id"], d["home_team_source_id"],
                alias_competition_key, s.get("season"), d.get("season"))
            away_alias = not same_away and alias_ok(
                s["away_team_source_id"], d["away_team_source_id"],
                s["competition_key"], s.get("season"), d.get("season"))
            if (same_home or home_alias) and (same_away or away_alias):
                edges[(i, j)] = {
                    "home": "approved_alias" if home_alias else "strict_name",
                    "away": "approved_alias" if away_alias else "strict_name",
                }
                continue
            reverse_home = (_name(s["home_team_name"]) == _name(d["away_team_name"])
                            or alias_ok(s["home_team_source_id"], d["away_team_source_id"],
                                        s["competition_key"], s.get("season"), d.get("season")))
            reverse_away = (_name(s["away_team_name"]) == _name(d["home_team_name"])
                            or alias_ok(s["away_team_source_id"], d["home_team_source_id"],
                                        s["competition_key"], s.get("season"), d.get("season")))
            if reverse_home and reverse_away:
                reverse.append((i, j))

    degree_l: dict[int, int] = defaultdict(int)
    degree_r: dict[int, int] = defaultdict(int)
    for i, j in edges:
        degree_l[i] += 1
        degree_r[j] += 1

    quarantine_l, quarantine_r = set(invalid_l), set(invalid_r)
    used_l, used_r = set(), set()
    decisions = []
    for i in sorted(invalid_l):
        decisions.append({"outcome": "INVALID_OR_DUPLICATE_STRIKER", "striker_index": i})
    for j in sorted(invalid_r):
        decisions.append({"outcome": "INVALID_OR_DUPLICATE_5DOLLAR", "fivedollar_index": j})

    for i, j in sorted(reverse):
        if degree_l[i] or degree_r[j]:
            continue
        quarantine_l.add(i)
        quarantine_r.add(j)
        decisions.append({"outcome": "IDENTITY_CONFLICT", "striker_index": i,
                          "fivedollar_index": j, "reason": "home_away_orientation_reversed"})

    for (i, j), evidence in sorted(edges.items()):
        if degree_l[i] != 1 or degree_r[j] != 1:
            quarantine_l.add(i)
            quarantine_r.add(j)
            decisions.append({"outcome": "AMBIGUOUS", "striker_index": i,
                              "fivedollar_index": j, "reason": "candidate_degree_exceeds_one"})
            continue
        used_l.add(i)
        used_r.add(j)
        s, d = left[i], right[j]
        if s["normalized_status"] != d["normalized_status"]:
            outcome, reason = "STATUS_CONFLICT", "normalized_status_disagreement"
        elif s["normalized_status"] == "finished" and (
            s.get("home_score") != d.get("home_score") or s.get("away_score") != d.get("away_score")
        ):
            outcome, reason = "RESULT_CONFLICT", "finished_score_disagreement"
        else:
            outcome, reason = "MATCHED_UNIQUE", "competition_season_orientation_and_exact_utc_kickoff"
        if outcome != "MATCHED_UNIQUE":
            quarantine_l.add(i)
            quarantine_r.add(j)
        decisions.append({
            "outcome": outcome, "striker_index": i, "fivedollar_index": j,
            "striker_source_id": s["source_id"], "fivedollar_source_id": d["source_id"],
            "kickoff_at": s["kickoff_at"], "identity_evidence": evidence, "reason": reason,
        })

    for i, row in enumerate(left):
        if i not in used_l and i not in quarantine_l:
            decisions.append({"outcome": "UNMATCHED_STRIKER_ONLY", "striker_index": i,
                              "source_id": row.get("source_id")})
    for j, row in enumerate(right):
        if j not in used_r and j not in quarantine_r:
            decisions.append({"outcome": "UNMATCHED_5DOLLAR_ONLY", "fivedollar_index": j,
                              "source_id": row.get("source_id")})

    matched_l = sum(d["outcome"] == "MATCHED_UNIQUE" for d in decisions)
    matched_r = matched_l
    unmatched_l = sum(d["outcome"] == "UNMATCHED_STRIKER_ONLY" for d in decisions)
    unmatched_r = sum(d["outcome"] == "UNMATCHED_5DOLLAR_ONLY" for d in decisions)
    counts = {
        "striker": {"total": len(left), "matched": matched_l, "unmatched": unmatched_l,
                    "quarantined": len(quarantine_l)},
        "fivedollar": {"total": len(right), "matched": matched_r, "unmatched": unmatched_r,
                       "quarantined": len(quarantine_r)},
    }
    for side, count in counts.items():
        count["balanced"] = count["total"] == count["matched"] + count["unmatched"] + count["quarantined"]

    return {
        "schema_version": 1, "report_type": "veltrix_provider_fixture_reconciliation",
        "mode": "offline_read_only_no_import", "acceptance_pass":
            all(v["balanced"] and v["quarantined"] == 0 for v in counts.values())
            and matched_l > 0 and matched_r > 0,
        "competition_map_striker_to_fivedollar": dict(sorted(competition_map.items())),
        "alias_scope": {"registry_status": alias_registry.get("status") if alias_registry else "not_loaded",
                        "competition_key": alias_competition_key, "season": season},
        "counts": counts, "decisions": decisions,
        "side_effects": {"network_requests": 0, "database_writes": 0, "imports": 0,
                         "checkpoints": 0, "canonical_merges": 0, "prediction_publications": 0},
    }


def reconcile_artifact_files(striker_path: str, fivedollar_path: str, competition_map_path: str,
                             *, alias_registry_path: str | None = None,
                             alias_competition_key: str | None = None,
                             season: str | None = None) -> dict:
    for path in (striker_path, fivedollar_path):
        validate_acquisition_report_file(path)
    striker = json.loads(Path(striker_path).read_text(encoding="utf-8"))
    dollar = json.loads(Path(fivedollar_path).read_text(encoding="utf-8"))
    if "strikerapi" not in striker.get("provider_scope", []) or "fivedollar" not in dollar.get("provider_scope", []):
        raise ValueError("artifact_provider_scope_mismatch")
    registry = load_registry(alias_registry_path) if alias_registry_path else None
    mapping = json.loads(Path(competition_map_path).read_text(encoding="utf-8"))
    report = reconcile_artifact_records(
        striker["records"], dollar["records"], mapping, alias_registry=registry,
        alias_competition_key=alias_competition_key, season=season,
    )
    report["provenance"] = {
        "striker_artifact_sha256": striker["report_sha256"],
        "fivedollar_artifact_sha256": dollar["report_sha256"],
        "striker_run_id": striker.get("run_id"), "fivedollar_run_id": dollar.get("run_id"),
        "striker_retrieved_at": striker.get("retrieved_at"),
        "fivedollar_retrieved_at": dollar.get("retrieved_at"),
    }
    report["report_sha256"] = _sha(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--striker-artifact", required=True)
    parser.add_argument("--fivedollar-artifact", required=True)
    parser.add_argument("--competition-map", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--alias-registry")
    parser.add_argument("--alias-competition-key")
    parser.add_argument("--season")
    args = parser.parse_args()
    report = reconcile_artifact_files(
        args.striker_artifact, args.fivedollar_artifact, args.competition_map,
        alias_registry_path=args.alias_registry,
        alias_competition_key=args.alias_competition_key, season=args.season,
    )
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RECONCILIATION_REPORT: {args.output}")
    print(f"ACCEPTANCE_PASS: {report['acceptance_pass']}")
    print("NETWORK_REQUESTS: 0; DATABASE_WRITES: 0; IMPORTS: 0; CANONICAL_MERGES: 0")
    return 0 if report["acceptance_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
