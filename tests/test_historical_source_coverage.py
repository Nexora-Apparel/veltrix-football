import unittest

from app.canonical_season_crosswalk import (
    SCHEMA as SEASON_CROSSWALK_SCHEMA,
    sign_season_crosswalk_registry,
)
from app.canonical_team_crosswalk import (
    SCHEMA as TEAM_CROSSWALK_SCHEMA,
    sign_team_crosswalk_registry, canonical_sha256,
)
from app.point_in_time_feature_contract import build_point_in_time_feature_snapshot
from app.historical_source_coverage import (
    HistoricalSourceCoverageError,
    build_historical_source_coverage_report,
)


def snapshot(fixture_id, kickoff, features):
    return build_point_in_time_feature_snapshot(
        fixture_id=fixture_id,
        prediction_as_of=kickoff,
        features=[{
            "name": name, "value": value, "source": "results-provider",
            "source_id": f"source-{fixture_id}-{name}",
            "observed_at": "2026-09-01T10:00:00Z",
            "available_at": "2026-09-01T10:10:00Z",
            "retrieved_at": "2026-09-01T10:20:00Z",
            "payload_sha256": "a" * 64,
        } for name, value in features.items()],
    )


def fixture(fixture_id, home, away, kickoff):
    return {
        "fixture_id": fixture_id,
        "provider": "provider-a",
        "source_id": fixture_id.split(":", 1)[1],
        "competition_id": "league-1",
        "home_team_id": home,
        "away_team_id": away,
        "kickoff_at": kickoff,
        "settled_at": kickoff[:10] + "T13:00:00Z",
        "retrieved_at": kickoff[:10] + "T13:05:00Z",
        "settlement_source_id": "final-whistle-source",
        "source_season": "2025/26",
    }


SEASON_KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/veltrix-season-test-key"


class FakeSeasonKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}

    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}


SEASON_KMS = FakeSeasonKms()


def signed_season_crosswalk(provider="provider-a"):
    return sign_season_crosswalk_registry(
        kms_client=SEASON_KMS,
        key_arn=SEASON_KEY_ARN,
        trusted_key_regions={SEASON_KEY_ARN: "eu-west-1"},
        registry={
            "schema": SEASON_CROSSWALK_SCHEMA,
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "mappings": [{
                "provider": provider,
                "competition_id": "league-1",
                "source_season": "2025/26",
                "canonical_season_id": "league-1:2025-2026",
                "evidence_sha256": ["a" * 64],
                "reviewer": "data-governance-review",
                "reviewed_at": "2026-01-02T00:00:00Z",
                "valid_from": "2026-01-03T00:00:00Z",
                "valid_until": "2026-12-31T00:00:00Z",
                "revoked_at": None,
            }],
        },
    )


def signed_team_crosswalk(source_ids=("team-a", "team-b", "team-c")):
    mappings = []
    canonical_ids = {"team-a": "canonical-a", "team-b": "canonical-b", "team-c": "canonical-c"}
    for source_id in source_ids:
        canonical_id = canonical_ids[source_id]
        mappings.append({
            "provider": "provider-a",
            "competition_id": "league-1",
            "source_team_id": source_id,
            "canonical_team_id": canonical_id,
            "team_scope": "men_first_team",
            "evidence_sha256": ["b" * 64],
            "reviewer": "team-identity-review",
            "reviewed_at": "2026-01-02T00:00:00Z",
            "valid_from": "2026-01-03T00:00:00Z",
            "valid_until": "2026-12-31T00:00:00Z",
            "revoked_at": None,
        })
    return sign_team_crosswalk_registry(
        kms_client=SEASON_KMS,
        key_arn=SEASON_KEY_ARN,
        trusted_key_regions={SEASON_KEY_ARN: "eu-west-1"},
        registry={
            "schema": TEAM_CROSSWALK_SCHEMA,
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "mappings": mappings,
        },
    )


def report_input():
    a = fixture("provider:1", "team-a", "team-b", "2026-09-01T12:00:00Z")
    b = fixture("provider:2", "team-b", "team-c", "2026-09-02T12:00:00Z")
    registry = signed_team_crosswalk()
    registry_digest = canonical_sha256({
        key: value for key, value in registry.items() if key != "signature"
    })
    for record in (a, b):
        home_source, away_source = record["home_team_id"], record["away_team_id"]
        canonical = {"team-a": "canonical-a", "team-b": "canonical-b", "team-c": "canonical-c"}
        record["home_team_source_id"] = home_source
        record["away_team_source_id"] = away_source
        record["home_team_id"] = canonical[home_source]
        record["away_team_id"] = canonical[away_source]
        record["team_identity_evidence"] = {
            "home_source_team_id": home_source,
            "away_source_team_id": away_source,
            "home_canonical_team_id": canonical[home_source],
            "away_canonical_team_id": canonical[away_source],
            "team_scope": "men_first_team",
            "registry_sha256": registry_digest,
            "signing_key_arn": SEASON_KEY_ARN,
            "verified_at": "2026-06-01T00:00:00Z",
        }
    sa = snapshot(a["fixture_id"], "2026-09-01T11:00:00Z", {"home_team_elo": 1500})
    sb = snapshot(b["fixture_id"], "2026-09-02T11:00:00Z", {"home_team_elo": 1490})
    return {
        "historical_availability_proven": False,
        "acquisition_eligibility": {
            "input_record_count": 3, "rejected_count": 1,
            "accepted_records": [a, b],
            "rejected_records": [{"fixture_id": "provider:3", "reason": "no_settlement"}],
        },
        "feature_reconstruction": {
            "snapshots": [sa, sb], "snapshot_count": 2,
        },
        "dataset": {
            "rows": [
                {"fixture_id": a["fixture_id"], "competition_key": "league-1",
                 "feature_snapshot_sha256": sa["snapshot_sha256"],
                 "predictors": {"home_team_elo": 1500}},
                {"fixture_id": b["fixture_id"], "competition_key": "league-1",
                 "feature_snapshot_sha256": sb["snapshot_sha256"],
                 "predictors": {"home_team_elo": 1490}},
            ],
        },
    }


class HistoricalSourceCoverageTests(unittest.TestCase):
    def test_reports_competition_team_feature_and_season_gaps(self):
        result = build_historical_source_coverage_report(
            report_input(),
            minimum_fixtures_per_competition=2,
            minimum_distinct_teams_per_competition=3,
            minimum_feature_coverage_rate=0.9,
        )
        league = result["competition_coverage"]["league-1"]
        self.assertEqual(league["settlement_eligible_fixtures"], 2)
        self.assertIsNone(league["distinct_teams"])
        self.assertEqual(league["distinct_source_team_ids"], 3)
        self.assertFalse(league["team_identity"]["canonical_team_crosswalk_verified"])
        self.assertEqual(league["dataset_rows"], 2)
        self.assertEqual(league["season_coverage"]["status"], "source_reported_crosswalk_unverified")
        self.assertFalse(league["season_coverage"]["canonical_season_crosswalk_verified"])
        self.assertEqual(result["feature_coverage"]["by_feature"]["home_team_elo"]["coverage_rate"], 1.0)
        self.assertFalse(result["historical_availability"]["proven"])
        self.assertFalse(result["qualification"]["source_coverage_qualified"])
        self.assertIn("season_crosswalk_unverified", result["qualification"]["threshold_failures"])
        self.assertEqual(
            result["feature_coverage"]["by_data_domain"]["injury_availability"]["status"],
            "not_in_feature_catalogue",
        )
        self.assertEqual(
            result["feature_coverage"]["by_data_domain"]["pressing_intensity_ppda"]["status"],
            "not_in_feature_catalogue",
        )
        self.assertFalse(result["qualification"]["training_authorized"])
        self.assertEqual(len(result["report_sha256"]), 64)

    def test_reports_provider_specific_acceptance_and_rejection_rates(self):
        value = report_input()
        value["acquisition_eligibility"]["rejected_records"][0].update({
            "provider": "provider-a",
            "source_id": "3",
        })
        result = build_historical_source_coverage_report(
            value,
            minimum_fixtures_per_competition=2,
            minimum_distinct_teams_per_competition=3,
            minimum_feature_coverage_rate=0.9,
        )
        quality = result["settlement_source_coverage"]["provider_quality"]["provider-a"]
        self.assertEqual(quality["input_records"], 3)
        self.assertEqual(quality["accepted_records"], 2)
        self.assertEqual(quality["rejected_records"], 1)
        self.assertAlmostEqual(quality["acceptance_rate"], 2 / 3)
        self.assertEqual(quality["rejection_reasons"], {"no_settlement": 1})

    def test_reports_provider_settlement_retrieval_chronology(self):
        result = build_historical_source_coverage_report(
            report_input(),
            minimum_fixtures_per_competition=2,
            minimum_distinct_teams_per_competition=3,
            minimum_feature_coverage_rate=0.9,
        )
        quality = result["settlement_source_coverage"]["provider_quality"]["provider-a"]
        self.assertEqual(
            quality["settlement_timestamp_provenance"]["settlement_timestamp_present"], 2
        )
        self.assertEqual(
            quality["settlement_timestamp_provenance"]["retrieval_timestamp_present"], 2
        )
        self.assertEqual(
            quality["settlement_timestamp_provenance"]["retrieval_after_settlement"], 2
        )

    def test_rejects_provider_retrieval_timestamp_before_settlement(self):
        value = report_input()
        value["acquisition_eligibility"]["accepted_records"][0]["retrieved_at"] = (
            "2026-09-01T12:59:59Z"
        )
        with self.assertRaisesRegex(
            HistoricalSourceCoverageError, "provider_retrieval_precedes_settlement"
        ):
            build_historical_source_coverage_report(value)

    def test_signed_crosswalk_verifies_canonical_season_identity(self):
        result = build_historical_source_coverage_report(
            report_input(),
            minimum_fixtures_per_competition=2,
            minimum_distinct_teams_per_competition=3,
            minimum_feature_coverage_rate=0.9,
            season_crosswalk_registry=signed_season_crosswalk(),
            trusted_kms_clients={SEASON_KEY_ARN: SEASON_KMS},
            season_crosswalk_as_of="2026-06-01T00:00:00Z",
        )
        season = result["competition_coverage"]["league-1"]["season_coverage"]
        self.assertEqual(season["status"], "verified")
        self.assertTrue(season["canonical_season_crosswalk_verified"])
        self.assertEqual(season["canonical_season_counts"], {"league-1:2025-2026": 2})
        self.assertEqual(season["mapped_records"], 2)
        self.assertEqual(season["unmapped_records"], 0)
        self.assertNotIn("season_crosswalk_unverified", result["qualification"]["threshold_failures"])

    def test_signed_crosswalk_does_not_allow_provider_scope_substitution(self):
        result = build_historical_source_coverage_report(
            report_input(),
            minimum_fixtures_per_competition=2,
            minimum_distinct_teams_per_competition=3,
            minimum_feature_coverage_rate=0.9,
            season_crosswalk_registry=signed_season_crosswalk(provider="different-provider"),
            trusted_kms_clients={SEASON_KEY_ARN: SEASON_KMS},
            season_crosswalk_as_of="2026-06-01T00:00:00Z",
        )
        season = result["competition_coverage"]["league-1"]["season_coverage"]
        self.assertEqual(season["status"], "source_reported_crosswalk_unverified")
        self.assertFalse(season["canonical_season_crosswalk_verified"])
        self.assertIn("season_crosswalk_unverified", result["qualification"]["threshold_failures"])

    def test_signed_crosswalk_requires_out_of_band_trust(self):
        with self.assertRaisesRegex(HistoricalSourceCoverageError, "trusted_keys_required"):
            build_historical_source_coverage_report(
                report_input(),
                season_crosswalk_registry=signed_season_crosswalk(),
                trusted_kms_clients={},
                season_crosswalk_as_of="2026-06-01T00:00:00Z",
            )

    def test_signed_team_crosswalk_qualifies_canonical_team_coverage(self):
        result = build_historical_source_coverage_report(
            report_input(),
            minimum_fixtures_per_competition=2,
            minimum_distinct_teams_per_competition=3,
            minimum_feature_coverage_rate=0.9,
            team_crosswalk_registry=signed_team_crosswalk(),
            trusted_kms_clients={SEASON_KEY_ARN: SEASON_KMS},
            team_crosswalk_as_of="2026-06-01T00:00:00Z",
        )
        league = result["competition_coverage"]["league-1"]
        self.assertEqual(league["distinct_teams"], 3)
        self.assertEqual(league["team_identity"]["status"], "verified")
        self.assertTrue(league["thresholds"]["teams_met"])
        self.assertTrue(result["team_coverage"]["league-1"]["canonical_team_crosswalk_verified"])
        self.assertEqual(
            result["team_coverage"]["league-1"]["canonical_team_fixture_appearances"],
            {"canonical-a": 1, "canonical-b": 2, "canonical-c": 1},
        )

    def test_unmapped_team_identity_blocks_team_coverage_threshold(self):
        result = build_historical_source_coverage_report(
            report_input(),
            minimum_fixtures_per_competition=2,
            minimum_distinct_teams_per_competition=3,
            minimum_feature_coverage_rate=0.9,
            team_crosswalk_registry=signed_team_crosswalk(source_ids=("team-a", "team-b")),
            trusted_kms_clients={SEASON_KEY_ARN: SEASON_KMS},
            team_crosswalk_as_of="2026-06-01T00:00:00Z",
        )
        league = result["competition_coverage"]["league-1"]
        self.assertEqual(league["team_identity"]["status"], "partially_verified")
        self.assertEqual(league["team_identity"]["unmapped_team_appearances"], 1)
        self.assertFalse(league["thresholds"]["teams_met"])
        self.assertIn(
            "league-1:team_identity_crosswalk_unverified",
            result["qualification"]["threshold_failures"],
        )

    def test_signed_team_crosswalk_requires_out_of_band_trust(self):
        with self.assertRaisesRegex(HistoricalSourceCoverageError, "team_crosswalk_trusted_keys_required"):
            build_historical_source_coverage_report(
                report_input(),
                team_crosswalk_registry=signed_team_crosswalk(),
                trusted_kms_clients={},
                team_crosswalk_as_of="2026-06-01T00:00:00Z",
            )

    def test_rejects_dataset_row_with_wrong_snapshot_digest(self):
        value = report_input()
        value["dataset"]["rows"][0]["feature_snapshot_sha256"] = "b" * 64
        with self.assertRaisesRegex(HistoricalSourceCoverageError, "dataset_row_source_join_invalid"):
            build_historical_source_coverage_report(value)

    def test_rejects_accepted_fixture_with_missing_team_identity(self):
        value = report_input()
        del value["acquisition_eligibility"]["accepted_records"][0]["home_team_id"]
        with self.assertRaisesRegex(HistoricalSourceCoverageError, "accepted_record_scope_invalid"):
            build_historical_source_coverage_report(value)

    def test_rejects_admission_count_mismatch(self):
        value = report_input()
        value["acquisition_eligibility"]["input_record_count"] = 99
        with self.assertRaisesRegex(HistoricalSourceCoverageError, "settlement_admission_count_mismatch"):
            build_historical_source_coverage_report(value)


if __name__ == "__main__":
    unittest.main()
