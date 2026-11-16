from datetime import datetime, timezone

import pytest

from veltrix_v2.identity.teams import (
    CanonicalTeam,
    TeamCrosswalkEntry,
    TeamSourceRecord,
    normalize_team_name,
    resolve_team_identity,
    validate_crosswalk_registry,
)

UTC = timezone.utc
VERIFIED_AT = datetime(2026, 11, 14, 0, 0, tzinfo=UTC)
HASH = "a" * 64


def teams():
    return [
        CanonicalTeam("veltrix:team:remo-stars", "Remo Stars FC", "NGA_NPFL", "NG",
                      aliases=("Remo Stars Football Club",)),
        CanonicalTeam("veltrix:team:rivers-united", "Rivers United FC", "NGA_NPFL", "NG"),
    ]


def entry(source="fivedollar", source_id="club-100", canonical="veltrix:team:remo-stars"):
    return TeamCrosswalkEntry(
        source=source, source_team_id=source_id, canonical_team_id=canonical,
        competition_id="NGA_NPFL", country_code="NG",
        evidence_uri="https://official.example/club/remo-stars",
        evidence_sha256=HASH, verified_at=VERIFIED_AT,
    )


def record(source="fivedollar", source_id="club-100", name="Remo Stars", comp="NGA_NPFL", country="NG"):
    return TeamSourceRecord(source, source_id, name, comp, country)


def test_verified_provider_id_crosswalk_is_the_only_resolved_path():
    result = resolve_team_identity(record(), canonical_teams=teams(), crosswalk_entries=[entry()])
    assert result.status == "RESOLVED"
    assert result.canonical_team_id == "veltrix:team:remo-stars"
    assert result.reason_code == "VERIFIED_PROVIDER_ID_CROSSWALK"


def test_exact_name_match_is_candidate_only_until_evidence_is_supplied():
    result = resolve_team_identity(
        record(source_id="other-id", name="Remo Stars Football Club"),
        canonical_teams=teams(),
    )
    assert result.status == "REVIEW_REQUIRED"
    assert result.canonical_team_id is None
    assert result.candidate_canonical_team_ids == ("veltrix:team:remo-stars",)


def test_name_collision_is_ambiguous_and_never_auto_merged():
    canonical = teams() + [
        CanonicalTeam("veltrix:team:remo-academy", "Remo Stars FC", "NGA_NPFL", "NG")
    ]
    result = resolve_team_identity(
        record(source_id="unknown", name="Remo Stars FC"),
        canonical_teams=canonical,
    )
    assert result.status == "AMBIGUOUS"
    assert result.canonical_team_id is None
    assert len(result.candidate_canonical_team_ids) == 2


def test_competition_and_country_are_part_of_candidate_scope():
    result = resolve_team_identity(
        record(source_id="unknown", name="Remo Stars FC", comp="OTHER", country="NG"),
        canonical_teams=teams(),
    )
    assert result.status == "UNRESOLVED"


def test_verified_crosswalk_scope_mismatch_fails_closed():
    result = resolve_team_identity(
        record(comp="OTHER"),
        canonical_teams=teams(), crosswalk_entries=[entry()],
    )
    assert result.status == "SCOPE_MISMATCH"
    assert result.canonical_team_id is None


@pytest.mark.parametrize(
    ("changed", "reason"),
    [
        ({"evidence_uri": "http://official.example/club"}, "CROSSWALK_EVIDENCE_URI_INVALID"),
        ({"evidence_sha256": "not-a-hash"}, "CROSSWALK_EVIDENCE_HASH_INVALID"),
        ({"verified_at": datetime(2026, 11, 14)}, "CROSSWALK_VERIFIED_AT_MUST_BE_AWARE"),
        ({"canonical_team_id": "unknown"}, "CROSSWALK_CANONICAL_TEAM_UNKNOWN"),
        ({"country_code": "US"}, "CROSSWALK_CANONICAL_SCOPE_MISMATCH"),
    ],
)
def test_invalid_crosswalk_evidence_is_rejected(changed, reason):
    values = dict(
        source="fivedollar", source_team_id="club-100",
        canonical_team_id="veltrix:team:remo-stars",
        competition_id="NGA_NPFL", country_code="NG",
        evidence_uri="https://official.example/club/remo-stars",
        evidence_sha256=HASH, verified_at=VERIFIED_AT,
    )
    values.update(changed)
    invalid = TeamCrosswalkEntry(**values)
    with pytest.raises(ValueError, match=reason):
        validate_crosswalk_registry(teams(), [invalid])


def test_duplicate_provider_ids_are_rejected():
    with pytest.raises(ValueError, match="CROSSWALK_SOURCE_ID_DUPLICATE"):
        validate_crosswalk_registry(teams(), [entry(), entry(canonical="veltrix:team:rivers-united")])


def test_name_normalization_does_not_drop_club_tokens():
    assert normalize_team_name("Étoile du Sahel, FC") == "etoile du sahel fc"
    assert normalize_team_name("Rivers United FC") != normalize_team_name("Rivers United")
