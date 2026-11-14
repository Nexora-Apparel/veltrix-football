from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.data.competition_coverage import (
    CoverageFixture, DomainEvidence, audit_competition_coverage,
)
from veltrix_v2.data.provider_registry import DataDomain

UTC = timezone.utc
AS_OF = datetime(2026, 11, 14, 12, tzinfo=UTC)
KICKOFF = AS_OF + timedelta(days=1)
HASH = "a" * 64


def fixture(fid="fx-1", comp="league-a", kickoff=KICKOFF):
    return CoverageFixture(fid, comp, kickoff)


def evidence(fid="fx-1", comp="league-a", domain=DataDomain.LINEUPS, **changes):
    values = dict(
        fixture_id=fid, competition_id=comp, domain=domain,
        provider="ProviderA", source_id="source-1",
        available_at=AS_OF - timedelta(hours=2),
        recorded_at=AS_OF - timedelta(hours=1),
        payload_sha256=HASH, rights_approved=True,
        rights_approval_id="approval-1", rights_evidence_sha256="b" * 64,
        rights_evaluated_at=AS_OF - timedelta(minutes=90),
        point_in_time_certifiable=True,
    )
    values.update(changes)
    return DomainEvidence(**values)


def test_coverage_counts_distinct_fixtures_and_retains_provider_provenance():
    report = audit_competition_coverage(
        [fixture(), fixture("fx-2")],
        [evidence(), evidence(provider="ProviderB", source_id="source-2")],
        domains=[DataDomain.LINEUPS], as_of=AS_OF,
    )
    item = report.for_domain("league-a", DataDomain.LINEUPS)
    assert item.target_fixture_count == 2
    assert item.eligible_fixture_count == 1
    assert item.coverage_ratio == 0.5
    assert item.missing_fixture_ids == ("fx-2",)
    assert item.contributing_providers == ("ProviderA", "ProviderB")


def test_cross_competition_or_unknown_fixture_evidence_is_rejected():
    report = audit_competition_coverage(
        [fixture()], [evidence(comp="league-b"), evidence(fid="unknown")],
        domains=[DataDomain.LINEUPS], as_of=AS_OF,
    )
    item = report.for_domain("league-a", DataDomain.LINEUPS)
    assert item.eligible_fixture_count == 0
    assert item.rejected_evidence_count == 1  # cross-competition evidence is scoped separately


@pytest.mark.parametrize("changes", [
    {"rights_approved": False},
    {"rights_approved": 1},
    {"rights_approval_id": ""},
    {"rights_evidence_sha256": "invalid"},
    {"rights_evaluated_at": AS_OF + timedelta(minutes=1)},
    {"rights_evaluated_at": AS_OF + timedelta(hours=1)},
    {"point_in_time_certifiable": False},
    {"point_in_time_certifiable": 1},
    {"payload_sha256": "bad"},
    {"available_at": AS_OF + timedelta(hours=1)},
    {"recorded_at": AS_OF + timedelta(hours=1)},
    {"recorded_at": AS_OF - timedelta(days=1)},
    {"available_at": KICKOFF},
])
def test_unapproved_uncertified_malformed_or_late_evidence_is_rejected(changes):
    report = audit_competition_coverage(
        [fixture()], [evidence(**changes)],
        domains=[DataDomain.LINEUPS], as_of=AS_OF,
    )
    item = report.for_domain("league-a", DataDomain.LINEUPS)
    assert item.eligible_fixture_count == 0
    assert item.rejected_evidence_count == 1


def test_results_are_allowed_to_become_available_after_kickoff():
    finished_kickoff = AS_OF - timedelta(days=2)
    result_evidence = evidence(
        domain=DataDomain.RESULTS,
        available_at=finished_kickoff + timedelta(hours=2),
        recorded_at=finished_kickoff + timedelta(hours=3),
        rights_evaluated_at=finished_kickoff + timedelta(hours=2, minutes=30),
    )
    report = audit_competition_coverage(
        [fixture(kickoff=finished_kickoff)], [result_evidence],
        domains=[DataDomain.RESULTS], as_of=AS_OF,
    )
    item = report.for_domain("league-a", DataDomain.RESULTS)
    assert item.eligible_fixture_count == 1
    assert item.coverage_ratio == 1.0


def test_duplicate_fixture_ids_fail_closed():
    with pytest.raises(ValueError, match="COVERAGE_FIXTURE_ID_DUPLICATE"):
        audit_competition_coverage(
            [fixture(), fixture()], [], domains=[DataDomain.LINEUPS], as_of=AS_OF,
        )


def test_naive_as_of_and_fixture_timestamps_fail_closed():
    with pytest.raises(ValueError, match="COVERAGE_AS_OF_MUST_BE_TIMEZONE_AWARE"):
        audit_competition_coverage([], [], as_of=datetime(2026, 11, 14))
    with pytest.raises(ValueError, match="COVERAGE_FIXTURE_INVALID"):
        audit_competition_coverage(
            [fixture(kickoff=datetime(2026, 11, 15))], [],
            domains=[DataDomain.LINEUPS], as_of=AS_OF,
        )


def test_zero_fixture_competitions_are_not_synthesized():
    report = audit_competition_coverage(
        [], [], domains=[DataDomain.LINEUPS], as_of=AS_OF,
    )
    assert report.domains == ()
