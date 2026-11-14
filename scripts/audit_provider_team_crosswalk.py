#!/usr/bin/env python3
"""Audit provider team-ID crosswalks using strict fixture matches as anchors.

This is a diagnostic only. It never changes the production alias registry or matcher.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def kickoff_key(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("kickoff must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def team_pair(row: dict, side: str) -> tuple[str, str]:
    return str(row.get(f"{side}_id") or ""), str(row.get(side) or "")


def add_mapping(mapping: dict[str, str], reverse: dict[str, str],
                striker_id: str, dollar_id: str) -> bool:
    if not striker_id or not dollar_id:
        return False
    if striker_id in mapping and mapping[striker_id] != dollar_id:
        raise ValueError(f"conflicting 5Dollar ID for Striker team {striker_id}")
    if dollar_id in reverse and reverse[dollar_id] != striker_id:
        raise ValueError(f"conflicting Striker ID for 5Dollar team {dollar_id}")
    is_new = striker_id not in mapping
    mapping[striker_id] = dollar_id
    reverse[dollar_id] = striker_id
    return is_new


def audit_crosswalk(report: dict, minimum_support: int = 3) -> dict:
    if report.get("schema_version") != 1 or report.get("mode") != "read_only_no_merge":
        raise ValueError("unsupported reconciliation report")
    if minimum_support < 2:
        raise ValueError("minimum_support must be at least two independent fixtures")

    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    strict_seed_ids: set[str] = set()
    names: dict[tuple[str, str], tuple[str, str]] = {}
    support: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for decision in report.get("decisions", []):
        if decision.get("outcome") != "MATCHED_UNIQUE":
            continue
        s, d = decision["striker"], decision["fivedollar"]
        for side in ("home", "away"):
            sid, sname = team_pair(s, side)
            did, dname = team_pair(d, side)
            add_mapping(mapping, reverse, sid, did)
            strict_seed_ids.add(sid)
            names[(sid, did)] = (sname, dname)
            support[(sid, did)][f"strict:{s['source_id']}:{d['source_id']}"] = {
                "striker_fixture_id": s["source_id"],
                "fivedollar_fixture_id": d["source_id"],
                "evidence": "strict_name_fixture_match",
                "kickoff": s["kickoff"],
            }

    left = [x["striker"] for x in report.get("decisions", [])
            if x.get("outcome") == "UNMATCHED_STRIKER_ONLY"]
    right = [x["fivedollar"] for x in report.get("decisions", [])
             if x.get("outcome") == "UNMATCHED_5DOLLAR_ONLY"]
    used_left: set[str] = set()
    used_right: set[str] = set()
    conflict_records: list[dict] = []
    rounds = 0

    while True:
        rounds += 1
        candidates: dict[tuple[str, str], dict] = {}
        left_degree: dict[str, int] = defaultdict(int)
        right_degree: dict[str, int] = defaultdict(int)
        for s in left:
            if s["source_id"] in used_left:
                continue
            for d in right:
                if d["source_id"] in used_right:
                    continue
                if kickoff_key(s["kickoff"]) != kickoff_key(d["kickoff"]):
                    continue
                anchors = []
                proposals = []
                for side, other in (("home", "away"), ("away", "home")):
                    sid, sname = team_pair(s, side)
                    did, dname = team_pair(d, side)
                    if sid in mapping and mapping[sid] == did:
                        anchors.append((side, sid, did))
                    elif sid in mapping and mapping[sid] != did:
                        continue
                    elif did in reverse and reverse[did] != sid:
                        continue
                    else:
                        proposals.append((side, sid, did, sname, dname))
                if not anchors:
                    continue
                if len(anchors) == 2:
                    # Both sides are already mapped. It is only a confirming
                    # fixture if both provider IDs agree on both sides.
                    if all(mapping.get(team_pair(s, side)[0]) == team_pair(d, side)[0]
                           for side in ("home", "away")):
                        candidates[(s["source_id"], d["source_id"])] = {
                            "striker": s, "fivedollar": d, "proposals": [],
                            "anchors": anchors,
                        }
                elif len(proposals) == 1:
                    candidates[(s["source_id"], d["source_id"])] = {
                        "striker": s, "fivedollar": d, "proposals": proposals,
                        "anchors": anchors,
                    }
                # Two anchors with a disagreement, or two unanchored teams,
                # are not used to infer a mapping.
        for (sid, did) in candidates:
            left_degree[sid] += 1
            right_degree[did] += 1

        newly_mapped = 0
        for (sid, did), candidate in candidates.items():
            if left_degree[sid] != 1 or right_degree[did] != 1:
                continue
            s, d = candidate["striker"], candidate["fivedollar"]
            key = f"crosswalk:{sid}:{did}"
            for side, anchor_sid, anchor_did in candidate["anchors"]:
                support[(anchor_sid, anchor_did)][key] = {
                    "striker_fixture_id": sid,
                    "fivedollar_fixture_id": did,
                    "evidence": f"same_kickoff_and_{side}_anchor",
                    "kickoff": s["kickoff"],
                }
            for side, new_sid, new_did, sname, dname in candidate["proposals"]:
                try:
                    is_new = add_mapping(mapping, reverse, new_sid, new_did)
                except ValueError as exc:
                    conflict_records.append({
                        "striker_fixture_id": sid,
                        "fivedollar_fixture_id": did,
                        "striker_team_id": new_sid,
                        "fivedollar_team_id": new_did,
                        "reason": str(exc),
                    })
                    continue
                names[(new_sid, new_did)] = (sname, dname)
                support[(new_sid, new_did)][key] = {
                    "striker_fixture_id": sid,
                    "fivedollar_fixture_id": did,
                    "evidence": f"same_kickoff_and_{candidate['anchors'][0][0]}_anchor",
                    "kickoff": s["kickoff"],
                }
                newly_mapped += int(is_new)
            used_left.add(sid)
            used_right.add(did)
        if newly_mapped == 0:
            break
        if rounds > len(left) + len(right):
            raise RuntimeError("crosswalk propagation did not converge")

    aliases = []
    for sid, did in sorted(mapping.items(), key=lambda x: int(x[0])):
        sname, dname = names.get((sid, did), ("", ""))
        evidence = list(support[(sid, did)].values())
        fixture_evidence = [x for x in evidence if x["evidence"] != "strict_name_fixture_match"]
        aliases.append({
            "striker_team_id": sid,
            "striker_name": sname,
            "fivedollar_team_id": did,
            "fivedollar_name": dname,
            "strict_seed": sid in strict_seed_ids,
            "strict_seed_fixture_count": sum(
                x["evidence"] == "strict_name_fixture_match" for x in evidence
            ),
            "anchored_crosswalk_fixture_count": len(fixture_evidence),
            "crosswalk_fixture_ids": sorted({
                (x["striker_fixture_id"], x["fivedollar_fixture_id"])
                for x in fixture_evidence
            }),
            "status": ("STRICT_NAME_MATCH_SEED" if sid in strict_seed_ids else
                "REPEATED_ANCHORED_CROSSWALK_SUPPORTED"
                if len({(x["striker_fixture_id"], x["fivedollar_fixture_id"])
                        for x in fixture_evidence}) >= minimum_support
                else "INSUFFICIENT_ANCHORED_SUPPORT"),
        })

    unmatched_after = {
        "striker": len(left) - len(used_left),
        "fivedollar": len(right) - len(used_right),
    }
    approved = all(x["status"] in ("STRICT_NAME_MATCH_SEED", "REPEATED_ANCHORED_CROSSWALK_SUPPORTED")
                   for x in aliases) and not conflict_records
    return {
        "schema_version": 1,
        "mode": "read_only_anchored_team_crosswalk_audit",
        "minimum_independent_fixture_support": minimum_support,
        "seed_method": "strict unique fixture matches with exact normalized team names",
        "inference_method": "same timezone-normalized kickoff plus one already-mapped team in the same home/away position; no scores, statuses or fuzzy names",
        "propagation_rounds": rounds,
        "strict_seed_team_count": len({
            team_id
            for decision in report.get("decisions", [])
            if decision.get("outcome") == "MATCHED_UNIQUE"
            for team_id in (decision["striker"]["home_id"], decision["striker"]["away_id"])
        }),
        "crosswalk_team_count": len(aliases),
        "anchored_fixture_pairs_used": len(used_left),
        "unmatched_fixture_rows_remaining": unmatched_after,
        "conflict_count": len(conflict_records),
        "conflicts": conflict_records,
        "crosswalks": aliases,
        "all_crosswalks_repeatedly_supported": approved,
        "database_writes": 0,
        "imports": 0,
        "canonical_merges": 0,
        "production_registry_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--minimum-support", type=int, default=3)
    args = parser.parse_args()
    report = json.loads(Path(args.reconciliation).read_text(encoding="utf-8"))
    result = audit_crosswalk(report, args.minimum_support)
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
    print(f"ANCHORED_CROSSWALK_TEAMS: {result['crosswalk_team_count']}")
    print(f"ANCHORED_FIXTURE_PAIRS: {result['anchored_fixture_pairs_used']}")
    print(f"UNMATCHED_FIXTURES_REMAINING: {result['unmatched_fixture_rows_remaining']}")
    print(f"CROSSWALK_CONFLICTS: {result['conflict_count']}")
    print(f"ALL_CROSSWALKS_REPEATEDLY_SUPPORTED: {result['all_crosswalks_repeatedly_supported']}")
    print("DATABASE_WRITES: 0; IMPORTS: 0; CANONICAL_MERGES: 0")
    return 0 if result["all_crosswalks_repeatedly_supported"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
