from app.research_verification import verify_structured_match_evidence


def _fixture(**overrides):
    fixture = {
        "provider_fixture_id": "fixture-9001",
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "competition": "National League",
        "squad_category": "Senior",
        "kickoff_utc": "2026-11-10T12:00:00Z",
    }
    fixture.update(overrides)
    return fixture


def _record(domain, **overrides):
    record = {
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "competition": "National League",
        "squad_category": "Senior",
        "match_date": "2026-10-01",
        "home_goals": 2,
        "away_goals": 1,
        "source_url": f"https://www.{domain}/match/123",
        "published_at": "2026-10-02T10:00:00Z",
        "retrieved_at_utc": "2026-11-05T10:00:00Z",
        "source_record_id": f"{domain}-123",
    }
    record.update(overrides)
    return record


def test_two_independent_trusted_sources_verify_and_preserve_provenance():
    result = verify_structured_match_evidence(
        _fixture(),
        [_record("uefa.com"), _record("fifa.com")],
        trusted_domains=["uefa.com", "fifa.com"],
    )

    assert result["status"] == "VERIFIED"
    assert result["model_eligible"] is True
    assert result["fixture_provider_id"] == "fixture-9001"
    assert result["verified_record_count"] == 1
    verified = result["verified_records"][0]
    assert (verified["home_goals"], verified["away_goals"]) == (2, 1)
    assert verified["verification_status"] == "VERIFIED_TWO_INDEPENDENT_SOURCES"
    assert len(verified["provenance"]) == 2


def test_subdomains_of_one_trusted_domain_are_not_independent_sources():
    result = verify_structured_match_evidence(
        _fixture(),
        [
            _record("uefa.com", source_url="https://www.uefa.com/match/123"),
            _record("uefa.com", source_url="https://scores.uefa.com/match/123"),
        ],
        trusted_domains=["uefa.com"],
    )

    assert result["status"] == "INSUFFICIENT_INDEPENDENT_SOURCES"
    assert result["model_eligible"] is False
    assert result["verified_records"] == []


def test_conflicting_scores_are_quarantined():
    result = verify_structured_match_evidence(
        _fixture(),
        [
            _record("uefa.com"),
            _record("fifa.com", home_goals=1, away_goals=1),
        ],
        trusted_domains=["uefa.com", "fifa.com"],
    )

    assert result["status"] == "QUARANTINED_CONFLICT"
    assert result["quarantined_conflict_records"] == 2
    assert result["model_eligible"] is False


def test_squad_category_mismatch_is_rejected_not_cross_matched():
    result = verify_structured_match_evidence(
        _fixture(squad_category="U19"),
        [_record("uefa.com"), _record("fifa.com")],
        trusted_domains=["uefa.com", "fifa.com"],
    )

    assert result["status"] == "NO_MATCHING_EVIDENCE"
    assert result["rejected_records"] == 2
    assert result["model_eligible"] is False


def test_post_kickoff_or_future_match_evidence_is_rejected():
    result = verify_structured_match_evidence(
        _fixture(kickoff_utc="2026-10-10T12:00:00Z"),
        [
            _record("uefa.com", match_date="2026-10-11", published_at="2026-10-12T10:00:00Z"),
            _record("fifa.com", match_date="2026-10-01", published_at="2026-10-12T10:00:00Z"),
        ],
        trusted_domains=["uefa.com", "fifa.com"],
    )

    assert result["model_eligible"] is False
    assert result["verified_records"] == []
    assert result["rejected_records"] == 2


def test_missing_trusted_domain_allowlist_disables_verification():
    result = verify_structured_match_evidence(_fixture(), [_record("uefa.com")], trusted_domains=[])

    assert result["status"] == "DISABLED_NO_TRUSTED_DOMAINS"
    assert result["model_eligible"] is False
