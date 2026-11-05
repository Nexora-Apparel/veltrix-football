"""Conservative, provenance-preserving cross-provider fixture identity.

Provider IDs remain source-local. A canonical fixture is formed only when
competition, squad category, home/away identity and kickoff all agree.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

KICKOFF_TOLERANCE_SECONDS = 300
KICKOFF_AMBIGUITY_WINDOW_SECONDS = 3600

# Curated aliases are deliberately exact and context-gated by competition,
# squad category, orientation and kickoff. Add entries only after source review.
# No name-only aliases are currently certified by a provider team-ID
# crosswalk. Add an alias only after source IDs and club identity are verified.
TEAM_ALIASES: dict[str, str] = {}
# Observed provider abbreviations without a verified team-ID crosswalk.
# They may trigger quarantine but are deliberately NOT merge aliases.
UNVERIFIED_TEAM_ALIAS_CANDIDATES = {
    "atleticopr": "atleticoparanaense",
    "vascodg": "vascodagama",
    "gremiopa": "gremio",
}
COMPETITION_ALIASES = {
    "braa": "brazilianseriea",
    "brazilseriea": "brazilianseriea",
    "brazilianseriea": "brazilianseriea",
    "brasileirao": "brazilianseriea",
    "premierleague": "premierleague",
    "englishpremierleague": "premierleague",
    "englandpremierleague": "premierleague",
    "epl": "premierleague",
    "laliga": "laliga",
    "spanishprimera": "laliga",
    "spainlaliga": "laliga",
    "bundesliga": "bundesliga",
    "germanbundesliga": "bundesliga",
    "seriea": "seriea",
    "italyseriea": "seriea",
    "italianseriea": "seriea",
    "ligue1": "ligue1",
    "franceligue1": "ligue1",
    "frenchligue1": "ligue1",
    "eredivisie": "eredivisie",
    "dutcheredivisie": "eredivisie",
    "primeiraliga": "primeiraliga",
    "portugalprimeiraliga": "primeiraliga",
    "argentineprimera": "argentineprimera",
    "argentinaprimera": "argentineprimera",
    "ligaprofesional": "argentineprimera",
}


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(re.findall(r"[a-z0-9]+", text))


def team_identity(value: Any) -> tuple[str, tuple[str, ...]]:
    """Return canonical club name and non-removable squad category."""
    raw = str(value or "").strip().casefold()
    category: list[str] = []
    patterns = (
        ("women", r"(?:\s*\((?:w|women)\)|\s+(?:women|womens|ladies|feminine|femenino|feminino))$"),
        ("u19", r"(?:\s*\(u19\)|\s+u19)$"),
        ("u21", r"(?:\s*\(u21\)|\s+u21)$"),
        ("u23", r"(?:\s*\(u23\)|\s+u23)$"),
        ("reserve", r"(?:\s*\((?:r|reserves?)\)|\s+(?:reserves?|b|b\s*team|ii|iii|iv))$"),
    )
    base = raw
    changed = True
    while changed:
        changed = False
        for label, pattern in patterns:
            if re.search(pattern, base):
                category.append(label)
                base = re.sub(pattern, "", base).strip()
                changed = True
                break
    tokens = re.findall(r"[a-z0-9]+", _plain(base))
    edge_markers = {"fc", "afc", "cf", "sc", "ac", "as", "ec", "sbv", "acf", "cd", "ud", "bc"}
    while tokens and tokens[0] in edge_markers:
        tokens.pop(0)
    while tokens and tokens[-1] in edge_markers:
        tokens.pop()
    key = "".join(tokens)
    key = TEAM_ALIASES.get(key, key)
    return key, tuple(sorted(category))


def competition_identity(row: dict[str, Any]) -> tuple[str, str, str] | None:
    league = row.get("league") if isinstance(row.get("league"), dict) else {}
    name = _plain(league.get("name"))
    country = _plain(league.get("country"))
    if not name:
        return None
    category = "senior"
    if re.search(r"(women|womens|ladies|feminin|femenino|feminino)", name):
        category = "women"
    elif re.search(r"(u19|u20|u21|u23|youth|academy|junior)", name):
        category = "youth"
    elif re.search(r"(reserve|reserves|secondteam|bteam|ii|iii)", name):
        category = "reserve"
    return category, country, COMPETITION_ALIASES.get(name, name)


def _kickoff(row: dict[str, Any], timezone_name: str) -> datetime | None:
    fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
    raw = fixture.get("date")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo(timezone_name))
    except (TypeError, ValueError, OverflowError):
        return None


def _identity(row: dict[str, Any], timezone_name: str) -> dict[str, Any]:
    teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    home_key, home_category = team_identity(home.get("name"))
    away_key, away_category = team_identity(away.get("name"))
    competition = competition_identity(row)
    competition_category = competition[0] if competition else "unknown"
    competition_name = competition[2] if competition else ""
    age_match = re.search(r"u(19|20|21|23)", competition_name)
    if competition_category == "youth":
        inherited_category = ("youth", "u" + age_match.group(1)) if age_match else ("youth",)
    elif competition_category in {"women", "reserve"}:
        inherited_category = (competition_category,)
    else:
        inherited_category = ()
    def effective_category(category: tuple[str, ...]) -> tuple[str, ...]:
        if not category:
            return inherited_category
        if len(category) == 1 and category[0] in {"u19", "u20", "u21", "u23"}:
            return ("youth", category[0])
        return category
    home_category = effective_category(home_category)
    away_category = effective_category(away_category)
    kickoff = _kickoff(row, timezone_name)
    return {
        "home_key": home_key, "away_key": away_key,
        "home_category": home_category, "away_category": away_category,
        "competition": competition, "kickoff": kickoff,
        "source": str(row.get("_veltrix_source") or row.get("provider") or "UNKNOWN"),
        "fixture_id": (row.get("fixture") or {}).get("id"),
        "competition_id": (row.get("league") or {}).get("id"),
    }


def _provenance(row: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
    league = row.get("league") if isinstance(row.get("league"), dict) else {}
    teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    return {
        "provider": identity["source"],
        "fixture_id": fixture.get("id"),
        "competition_id": league.get("id"),
        "competition_name": league.get("name"),
        "competition_country": league.get("country"),
        "home_team_id": home.get("id"),
        "away_team_id": away.get("id"),
        "home_team_name": home.get("name"),
        "away_team_name": away.get("name"),
        "kickoff": fixture.get("date"),
    }




def fixtures_match(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    timezone_name: str = "Africa/Lagos",
    kickoff_tolerance_seconds: int = KICKOFF_TOLERANCE_SECONDS,
) -> bool:
    """Strict cross-feed event match; requires teams, squad and competition."""
    a = _identity(left, timezone_name)
    b = _identity(right, timezone_name)
    if not a["kickoff"] or not b["kickoff"]:
        return False
    if abs((a["kickoff"] - b["kickoff"]).total_seconds()) > kickoff_tolerance_seconds:
        return False
    return bool(
        a["home_key"] and a["away_key"]
        and a["home_key"] == b["home_key"]
        and a["away_key"] == b["away_key"]
        and a["home_category"] == b["home_category"]
        and a["away_category"] == b["away_category"]
        and a["competition"] is not None
        and a["competition"] == b["competition"]
    )


def unique_prediction_match(
    event_row: dict[str, Any],
    predictions: list[dict[str, Any]],
    *,
    timezone_name: str = "Africa/Lagos",
) -> dict[str, Any] | None:
    """Return exactly one strict match; ambiguous or missing joins return None."""
    matches = []
    for prediction in predictions:
        if not isinstance(prediction, dict):
            continue
        prediction_row = {
            "fixture": {"date": prediction.get("kickoff_local") or prediction.get("kickoff")},
            "teams": {
                "home": {"name": prediction.get("home_team")},
                "away": {"name": prediction.get("away_team")},
            },
            "league": {
                "name": prediction.get("league"),
                "country": prediction.get("league_country"),
            },
            "_veltrix_source": prediction.get("fixture_source") or "PREDICTION",
        }
        if fixtures_match(event_row, prediction_row, timezone_name=timezone_name):
            matches.append(prediction)
    return matches[0] if len(matches) == 1 else None


def reconcile_fixture_rows(
    rows: list[dict[str, Any]],
    *,
    timezone_name: str = "Africa/Lagos",
    kickoff_tolerance_seconds: int = KICKOFF_TOLERANCE_SECONDS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge only verified duplicates; preserve and quarantine all other rows."""
    valid = [row for row in rows if isinstance(row, dict)]
    identities = [_identity(row, timezone_name) for row in valid]
    parent = list(range(len(valid)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = root(left), root(right)
        if a != b:
            parent[b] = a

    ambiguous_pairs: list[tuple[int, int, str]] = []
    for i in range(len(valid)):
        a = identities[i]
        for j in range(i + 1, len(valid)):
            b = identities[j]
            if (
                a["fixture_id"] is not None
                and a["source"] != "UNKNOWN"
                and a["source"] == b["source"]
                and str(a["fixture_id"]) == str(b["fixture_id"])
            ):
                same_core = (
                    bool(a["home_key"] and a["away_key"])
                    and a["home_key"] == b["home_key"] and a["away_key"] == b["away_key"]
                    and a["home_category"] == b["home_category"] and a["away_category"] == b["away_category"]
                    and a["competition"] == b["competition"]
                    and (
                        not a["kickoff"] or not b["kickoff"]
                        or abs((a["kickoff"] - b["kickoff"]).total_seconds()) <= kickoff_tolerance_seconds
                    )
                )
                if same_core:
                    union(i, j)
                else:
                    ambiguous_pairs.append((i, j, "same_provider_fixture_id_conflicting_identity"))
                continue

            if not a["kickoff"] or not b["kickoff"]:
                continue
            seconds = abs((a["kickoff"] - b["kickoff"]).total_seconds())
            same_categories = (
                a["home_category"] == b["home_category"]
                and a["away_category"] == b["away_category"]
            )
            same_teams = (
                bool(a["home_key"] and a["away_key"])
                and a["home_key"] == b["home_key"] and a["away_key"] == b["away_key"]
                and same_categories
            )
            if seconds > KICKOFF_AMBIGUITY_WINDOW_SECONDS or not same_categories:
                continue
            possible_unverified_alias = bool(a["home_key"] and a["away_key"] and b["home_key"] and b["away_key"]) and (
                UNVERIFIED_TEAM_ALIAS_CANDIDATES.get(a["home_key"], a["home_key"])
                == UNVERIFIED_TEAM_ALIAS_CANDIDATES.get(b["home_key"], b["home_key"])
                and UNVERIFIED_TEAM_ALIAS_CANDIDATES.get(a["away_key"], a["away_key"])
                == UNVERIFIED_TEAM_ALIAS_CANDIDATES.get(b["away_key"], b["away_key"])
            )
            if not same_teams and not possible_unverified_alias:
                continue
            if a["competition"] is not None and a["competition"] == b["competition"]:
                if same_teams and seconds <= kickoff_tolerance_seconds:
                    # Source-local competition IDs are recorded but never compared
                    # across providers. The normalized, category-aware competition
                    # identity is the cross-provider join key.
                    union(i, j)
                elif same_teams:
                    ambiguous_pairs.append((i, j, "kickoff_proximity_conflict"))
                else:
                    ambiguous_pairs.append((i, j, "team_alias_not_verified"))
            elif a["competition"] is None or b["competition"] is None:
                ambiguous_pairs.append((i, j, "competition_identity_missing"))
            elif a["competition"][0] == b["competition"][0]:
                # Same squad tier and near-identical team identity, but competition
                # country/name does not agree. Quarantine instead of guessing.
                ambiguous_pairs.append((i, j, "competition_identity_conflict"))
            # A different squad category is a distinct event.

    ambiguous_indices: dict[int, set[str]] = defaultdict(set)
    for index, identity in enumerate(identities):
        if not identity["kickoff"]:
            ambiguous_indices[index].add("missing_or_invalid_kickoff")
        if not identity["home_key"] or not identity["away_key"]:
            ambiguous_indices[index].add("missing_team_identity")
        if identity["competition"] is None:
            ambiguous_indices[index].add("missing_competition_identity")
    for i, j, reason in ambiguous_pairs:
        ambiguous_indices[i].add(reason)
        ambiguous_indices[j].add(reason)
        # One visible quarantine row retains every ambiguous source record.
        union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(valid)):
        groups[root(index)].append(index)

    output: list[dict[str, Any]] = []
    merged_groups = 0
    quarantined_rows = 0
    for members in groups.values():
        # Prefer the primary provider's representation without discarding
        # the full source records and IDs carried in provenance.
        ordered = sorted(
            members,
            key=lambda idx: (
                0 if identities[idx]["source"].casefold() == "5dollarfootballapi" else 1,
                identities[idx]["source"].casefold(),
                idx,
            ),
        )
        chosen_index = ordered[0]
        chosen = dict(valid[chosen_index])
        provenance = [_provenance(valid[idx], identities[idx]) for idx in ordered]
        source_ids = [
            {"provider": item["provider"], "fixture_id": item["fixture_id"]}
            for item in provenance
        ]
        chosen["_veltrix_provenance"] = provenance
        chosen["_veltrix_source_fixture_ids"] = source_ids
        reasons = sorted({reason for idx in members for reason in ambiguous_indices.get(idx, set())})
        chosen["_veltrix_canonical_fixture"] = len(members) > 1 and not reasons
        if len(members) > 1 and not reasons:
            merged_groups += 1
        if reasons:
            chosen["_veltrix_reconciliation_status"] = "AMBIGUOUS"
            chosen["_veltrix_quarantine_reasons"] = reasons
            chosen["_veltrix_ambiguous_source_records"] = [
                _provenance(valid[idx], identities[idx]) for idx in members
            ]
            quarantined_rows += len(members)
        else:
            chosen["_veltrix_reconciliation_status"] = "MATCHED" if len(members) > 1 else "UNIQUE"
        output.append(chosen)

    output.sort(key=lambda row: str(((row.get("fixture") or {}).get("date") or "")))
    return output, {
        "input_rows": len(valid),
        "canonical_rows": len(output),
        "confirmed_duplicate_groups": merged_groups,
        "quarantined_rows": quarantined_rows,
        "ambiguous_pairs": len(ambiguous_pairs),
        "kickoff_tolerance_seconds": kickoff_tolerance_seconds,
        "policy": "provider-local IDs; competition and squad-category aware; home/away orientation preserved; five-minute kickoff tolerance; ambiguous records quarantined",
    }
