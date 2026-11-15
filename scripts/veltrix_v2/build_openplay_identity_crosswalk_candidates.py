"""Build read-only exact-identity candidates from OpenPlay to existing 5Dollar canonicals.

No mappings are inserted here. Only unique exact team-name matches with an
overlapping, explicitly mapped competition are proposed as RESOLVABLE candidates.
All ambiguous, unmatched and non-overlapping entities remain quarantined.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
EXPECTED_DATABASE = "veltrix_football_staging"
PROVIDER = "OpenPlay / WhoScored / Opta"
SOURCE_ID = "openplay-data-v0.1.0"
APPROVAL_ID = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"

COMPETITION_ALIASES = {
    ("england", "premier league"): "England Premier League",
    ("france", "ligue 1"): "France Ligue 1",
    ("germany", "bundesliga"): "Germany Bundesliga I",
    ("italy", "serie a"): "Italy Serie A",
    ("spain", "la liga"): "Spain La Liga",
    ("brazil", "serie a"): "Brazil Serie A",
    ("brazil", "serie b"): "Brazil Serie B",
}


def normalize_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def parse_comp_codes(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return sorted({str(item).strip() for item in value if str(item).strip()})
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return sorted({str(item).strip() for item in parsed if str(item).strip()})
            except json.JSONDecodeError:
                pass
        return sorted({part.strip() for part in re.split(r"[,;|]", raw) if part.strip()})
    return []


def build_candidates(input_dir: str | Path, database_url: str) -> dict:
    parsed = urlparse(database_url)
    if (parsed.hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("OPENPLAY_CROSSWALK_DATABASE_HOST_MISMATCH")
    import duckdb
    import psycopg

    root = Path(input_dir)
    report = json.loads((root / "openplay_qualification_report.json").read_text(encoding="utf-8"))
    if report.get("status") != "PASS_NONCOMMERCIAL_SOURCE_QUALIFIED":
        raise RuntimeError("OPENPLAY_CROSSWALK_RELEASE_NOT_QUALIFIED")
    manifest_hash = report.get("capture_manifest_sha256") or report.get("manifest_sha256")
    if not manifest_hash:
        # The Neon capture manifest is authoritative; the release report may not carry it.
        manifest_hash = None

    db = duckdb.connect(database=":memory:")
    teams = db.execute("""
        SELECT team_id,team,country,comps,team_type
        FROM read_parquet(?)
        ORDER BY team_id
    """, [str(root / "teams.parquet")]).fetchall()
    competitions = db.execute("""
        SELECT comp,competition,region,competition_type,team_type
        FROM read_parquet(?)
        ORDER BY comp
    """, [str(root / "competitions.parquet")]).fetchall()
    db.close()

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),current_user")
            database, role = cur.fetchone()
            if database != EXPECTED_DATABASE or role != "neondb_owner":
                raise RuntimeError("OPENPLAY_CROSSWALK_DATABASE_TARGET_MISMATCH")
            cur.execute("""
                SELECT id,provider_team_id,name
                FROM teams WHERE provider='5DollarFootballAPI'
                ORDER BY id
            """)
            five_dollar_teams = cur.fetchall()
            cur.execute("""
                SELECT e.provider_entity_id,e.canonical_entity_key,t.name
                FROM entity_crosswalk_versions e
                JOIN teams t ON t.id::text=e.canonical_entity_key
                WHERE e.entity_type='TEAM' AND e.provider='5DollarFootballAPI'
                  AND e.source_id='5dollarfootballapi' AND e.mapping_status='RESOLVED'
                ORDER BY e.provider_entity_id
            """)
            team_crosswalk = cur.fetchall()
            cur.execute("""
                SELECT c.id,c.name,x.canonical_entity_key
                FROM competitions c
                JOIN entity_crosswalk_versions x
                  ON x.entity_type='COMPETITION'
                 AND x.provider='5DollarFootballAPI'
                 AND x.source_id='5dollarfootballapi'
                 AND x.provider_entity_id=c.provider_competition_id
                 AND x.mapping_status='RESOLVED'
                WHERE c.provider='5DollarFootballAPI'
            """)
            competition_crosswalk = cur.fetchall()
            cur.execute("""
                SELECT t.id,t.name,array_agg(DISTINCT f.competition_id)
                FROM teams t
                JOIN fixtures f ON f.home_team_id=t.id OR f.away_team_id=t.id
                WHERE t.provider='5DollarFootballAPI'
                GROUP BY t.id,t.name
            """)
            team_competitions = cur.fetchall()
            cur.execute("""
                SELECT id,provider_entity_id,payload_sha256,provider_response_id,payload
                FROM source_observations
                WHERE provider=%s AND source_id=%s AND entity_type='dataset_asset'
                  AND provider_entity_id IN ('teams.parquet','competitions.parquet')
            """, (PROVIDER,SOURCE_ID))
            source_evidence = {row[1]: row for row in cur.fetchall()}

    if set(source_evidence) != {"teams.parquet","competitions.parquet"}:
        raise RuntimeError("OPENPLAY_CROSSWALK_SOURCE_EVIDENCE_MISSING")

    canonical_competitions = {}
    for _id,name,canonical in competition_crosswalk:
        canonical_competitions[normalize_name(name)] = str(canonical)
    open_comp_to_canonical = {}
    canonical_competition_regions = {}
    competition_rows = []
    for comp, name, region, comp_type, team_type in competitions:
        key = (normalize_name(region), normalize_name(name))
        alias = COMPETITION_ALIASES.get(key)
        target = canonical_competitions.get(normalize_name(alias)) if alias else None
        status = "EXACT_REGION_NAME_ALIAS" if target else "UNMAPPED_OR_UNSUPPORTED"
        if target:
            open_comp_to_canonical[str(comp)] = target
            canonical_competition_regions[target] = normalize_name(region)
        competition_rows.append({
            "openplay_comp":str(comp),"competition":name,"region":region,
            "canonical_competition_key":target,"status":status,
            "source_evidence_observation_id":source_evidence["competitions.parquet"][0],
            "source_asset_sha256":source_evidence["competitions.parquet"][4].get("asset_sha256"),
        })

    target_name_rows = defaultdict(list)
    for provider_entity_id,canonical,name in team_crosswalk:
        target_name_rows[normalize_name(name)].append({
            "provider_entity_id":str(provider_entity_id),
            "canonical_entity_key":str(canonical),"name":name,
        })
    open_name_counts = Counter(normalize_name(row[1]) for row in teams)
    target_comp_by_name = defaultdict(set)
    for team_id,name,comp_ids in team_competitions:
        target_comp_by_name[normalize_name(name)].update(str(value) for value in (comp_ids or []))

    team_rows = []
    for team_id,name,country,comps,team_type in teams:
        key = normalize_name(name)
        codes = parse_comp_codes(comps)
        open_comp_keys = {open_comp_to_canonical[code] for code in codes if code in open_comp_to_canonical}
        candidates = target_name_rows.get(key, [])
        if not candidates:
            status = "UNMATCHED_NAME"
            selected = None
        elif len(candidates) != 1 or open_name_counts[key] != 1:
            status = "AMBIGUOUS_NAME"
            selected = None
        else:
            candidate = candidates[0]
            overlap = open_comp_keys.intersection(target_comp_by_name.get(key, set()))
            country_overlap = {
                comp_key for comp_key in overlap
                if canonical_competition_regions.get(comp_key) == normalize_name(country)
            }
            if not overlap:
                status = "NO_COMPETITION_OVERLAP"
                selected = None
            elif not country_overlap:
                status = "COUNTRY_COMPETITION_REGION_MISMATCH"
                selected = None
            else:
                status = "EXACT_UNIQUE_NAME_AND_COMPETITION_OVERLAP"
                selected = candidate
        team_rows.append({
            "openplay_team_id":str(team_id),"team":name,"country":country,
            "openplay_comp_codes":codes,
            "mapped_openplay_competition_keys":sorted(open_comp_keys),
            "country_verified_competition_keys":sorted(country_overlap) if key and candidates and len(candidates)==1 and open_name_counts[key]==1 else [],
            "status":status,
            "candidate_canonical_entity_key":selected["canonical_entity_key"] if selected else None,
            "candidate_5dollar_team_id":selected["provider_entity_id"] if selected else None,
            "evidence_source_observation_id":source_evidence["teams.parquet"][0],
            "source_asset_sha256":source_evidence["teams.parquet"][4].get("asset_sha256"),
        })

    summary = {
        "status":"READ_ONLY_CROSSWALK_CANDIDATES_BUILT",
        "commercial_use_allowed":False,
        "mapping_rows_written":0,
        "openplay_teams":len(team_rows),
        "exact_unique_name_and_competition_overlap":sum(x["status"]=="EXACT_UNIQUE_NAME_AND_COMPETITION_OVERLAP" for x in team_rows),
        "ambiguous_name":sum(x["status"]=="AMBIGUOUS_NAME" for x in team_rows),
        "no_competition_overlap":sum(x["status"]=="NO_COMPETITION_OVERLAP" for x in team_rows),
        "country_competition_region_mismatch":sum(x["status"]=="COUNTRY_COMPETITION_REGION_MISMATCH" for x in team_rows),
        "unmatched_name":sum(x["status"]=="UNMATCHED_NAME" for x in team_rows),
        "openplay_competitions":len(competition_rows),
        "mapped_competitions":sum(x["canonical_competition_key"] is not None for x in competition_rows),
        "unmapped_competitions":sum(x["canonical_competition_key"] is None for x in competition_rows),
        "policy":"No fuzzy or display-name-only mappings. Exact unique names require overlapping canonical competition scope. Unresolved rows remain quarantined.",
    }
    return {"summary":summary,"teams":team_rows,"competitions":competition_rows}


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--input-dir",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    result=build_candidates(args.input_dir,os.getenv("DATABASE_URL",""))
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result["summary"],sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
