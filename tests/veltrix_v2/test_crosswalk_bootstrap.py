from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from veltrix_v2.data.crosswalk_bootstrap import build_fivedollar_crosswalk_registry
from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture

UTC = timezone.utc
VERIFIED = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def row(fid, comp, home, away, canonical_fixture, canonical_comp, canonical_home, canonical_away, obs):
    payload = {
        "id": fid,
        "league": {"id": comp, "name": "Example League"},
        "teams": {
            "home": {"id": home, "name": f"Team {home}"},
            "away": {"id": away, "name": f"Team {away}"},
        },
    }
    return {
        "provider": "5DollarFootballAPI",
        "source_id": "5dollarfootballapi",
        "canonical_fixture_id": canonical_fixture,
        "canonical_competition_id": canonical_comp,
        "canonical_home_team_id": canonical_home,
        "canonical_away_team_id": canonical_away,
        "payload": payload,
        "payload_sha256": sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()).hexdigest(),
        "source_observation_id": obs,
    }


def rows():
    return [
        row(100, 311, 11, 22, "fx-1", "comp-1", "team-a", "team-b", 9001),
        row(101, 311, 22, 33, "fx-2", "comp-1", "team-b", "team-c", 9002),
    ]


def scheduled_fixture(*, home="11", away="33", comp="311", retrieved=VERIFIED + timedelta(minutes=1)):
    payload = {
        "id": 102,
        "league": {"id": int(comp), "name": "Example League"},
        "teams": {
            "home": {"id": int(home), "name": f"Team {home}"},
            "away": {"id": int(away), "name": f"Team {away}"},
        },
        "kickoff_utc": (retrieved + timedelta(days=2)).isoformat(),
    }
    return HistoricalFixture(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        provider_fixture_id="102", provider_competition_id=comp,
        provider_home_team_id=home, provider_away_team_id=away,
        competition_name="Example League", home_team_name=f"Team {home}",
        away_team_name=f"Team {away}",
        kickoff_at_utc=retrieved + timedelta(days=2), season_key="2026",
        status=FixtureStatus.SCHEDULED, home_score=None, away_score=None,
        payload=payload, payload_sha256=sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()).hexdigest(),
        retrieved_at_utc=retrieved, source_event_time_utc=retrieved + timedelta(days=2),
        available_at_utc=None, availability_basis="not_settled",
        point_in_time_certifiable=False, rights_approval_id="approval-1",
    )


def test_builds_unambiguous_fixture_team_and_competition_crosswalks():
    registry = build_fivedollar_crosswalk_registry(rows(), verified_at=VERIFIED)
    assert len(registry.fixture_crosswalks) == 2
    assert len(registry.team_crosswalks) == 3
    assert len(registry.competition_crosswalks) == 1
    crosswalk = registry.fixture_crosswalks["100"]
    crosswalk.validate(
        at=VERIFIED + timedelta(seconds=1),
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        provider_fixture_id="100", provider_competition_id="311",
        provider_home_team_id="11", provider_away_team_id="22",
    )
    assert len(crosswalk.evidence_sha256) == 64


def test_maps_new_scheduled_fixture_to_canonical_team_and_competition_ids():
    registry = build_fivedollar_crosswalk_registry(rows(), verified_at=VERIFIED)
    target = registry.to_prediction_target(scheduled_fixture())
    assert target.fixture_id == "5dollarfootballapi:102"
    assert target.competition_id == "comp-1"
    assert target.home_team_id == "team-a"
    assert target.away_team_id == "team-c"
    assert target.source_fixture_id == "102"


def test_rejects_ambiguous_team_mapping():
    data = rows()
    data.append(row(103, 311, 11, 44, "fx-3", "comp-1", "team-x", "team-d", 9003))
    with pytest.raises(ValueError, match="CROSSWALK_TEAM_MAPPING_AMBIGUOUS"):
        build_fivedollar_crosswalk_registry(data, verified_at=VERIFIED)


def test_rejects_ambiguous_competition_mapping():
    data = rows()
    data.append(row(103, 311, 44, 55, "fx-3", "comp-x", "team-d", "team-e", 9003))
    with pytest.raises(ValueError, match="CROSSWALK_COMPETITION_MAPPING_AMBIGUOUS"):
        build_fivedollar_crosswalk_registry(data, verified_at=VERIFIED)


def test_rejects_duplicate_provider_fixture_ids():
    data = rows()
    data.append(rows()[0])
    with pytest.raises(ValueError, match="CROSSWALK_PROVIDER_FIXTURE_DUPLICATE"):
        build_fivedollar_crosswalk_registry(data, verified_at=VERIFIED)


def test_rejects_payload_hash_substitution():
    data = rows()
    data[0]["payload_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="CROSSWALK_PAYLOAD_HASH_MISMATCH"):
        build_fivedollar_crosswalk_registry(data, verified_at=VERIFIED)


def test_rejects_unsupported_provider_and_naive_verification_clock():
    data = rows()
    data[0]["provider"] = "UnknownProvider"
    with pytest.raises(ValueError, match="CROSSWALK_PROVIDER_NOT_APPROVED"):
        build_fivedollar_crosswalk_registry(data, verified_at=VERIFIED)
    with pytest.raises(ValueError, match="CROSSWALK_VERIFICATION_TIME_MUST_BE_AWARE"):
        build_fivedollar_crosswalk_registry(rows(), verified_at=datetime(2026, 11, 14, 12, 0))


def test_target_mapping_requires_known_teams_and_verification_precedes_capture():
    registry = build_fivedollar_crosswalk_registry(rows(), verified_at=VERIFIED)
    with pytest.raises(ValueError, match="CROSSWALK_TEAM_NOT_FOUND"):
        registry.to_prediction_target(scheduled_fixture(home="99"))
    early = scheduled_fixture(retrieved=VERIFIED - timedelta(minutes=1))
    with pytest.raises(ValueError, match="CROSSWALK_TARGET_PRECEDES_VERIFICATION"):
        registry.to_prediction_target(early)
