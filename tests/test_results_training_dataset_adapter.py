import unittest
from datetime import date, timedelta

from app.source_payload_provenance import canonical_payload_sha256
from app.results_training_dataset_adapter import (
    assemble_results_history_dataset,
    build_results_history_snapshot,
)
from app.canonical_season_crosswalk import (
    SCHEMA as SEASON_SCHEMA, sign_season_crosswalk_registry,
)
from app.canonical_team_crosswalk import (
    SCHEMA as TEAM_SCHEMA, canonical_sha256 as team_canonical_sha256,
    sign_team_crosswalk_registry,
)

SEASON_KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/season-adapter-test"
TEAM_KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/team-adapter-test"

class FakeKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}
    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}

KMS = FakeKms()



def team_registry():
    mappings = [{
        "provider": "fivedollar",
        "competition_id": "4160026622",
        "source_team_id": team_id,
        "canonical_team_id": team_id,
        "team_scope": "men_first_team",
        "evidence_sha256": ["c" * 64],
        "reviewer": "team-review",
        "reviewed_at": "2026-01-02T00:00:00Z",
        "valid_from": valid_from,
        "valid_until": valid_until,
        "revoked_at": revoked_at,
    } for team_id in ("A", "B", "C", "D")]
    unsigned = {
        "schema": TEAM_SCHEMA,
        "issued_at": "2026-01-01T00:00:00Z",
        "expires_at": "2027-01-01T00:00:00Z",
        "mappings": mappings,
    }
    return sign_team_crosswalk_registry(
        kms_client=KMS, key_arn=TEAM_KEY_ARN,
        trusted_key_regions={TEAM_KEY_ARN: "eu-west-1"},
        registry=unsigned,
    )

TEAM_REGISTRY = team_registry()
TEAM_REGISTRY_DIGEST = team_canonical_sha256({
    key: value for key, value in TEAM_REGISTRY.items() if key != "signature"
})

def trusted_clients():
    return {SEASON_KEY_ARN: KMS, TEAM_KEY_ARN: KMS}

def attach_evidence(row):
    row.setdefault("home_team_source_id", row["home_team_id"])
    row.setdefault("away_team_source_id", row["away_team_id"])
    row["team_identity_evidence"] = {
        "home_source_team_id": row["home_team_source_id"],
        "away_source_team_id": row["away_team_source_id"],
        "home_canonical_team_id": row["home_team_id"],
        "away_canonical_team_id": row["away_team_id"],
        "team_scope": "men_first_team",
        "home_mapping_evidence_sha256": ["c" * 64],
        "away_mapping_evidence_sha256": ["c" * 64],
        "home_mapping_reviewer": "team-review",
        "away_mapping_reviewer": "team-review",
        "home_mapping_reviewed_at": "2026-01-02T00:00:00Z",
        "away_mapping_reviewed_at": "2026-01-02T00:00:00Z",
        "registry_sha256": TEAM_REGISTRY_DIGEST,
        "signing_key_arn": TEAM_KEY_ARN,
        "verified_at": row["retrieved_at"],
    }
    normalized = {
        "fixture_id": row["fixture_id"],
        "competition_id": row["competition_id"],
        "source_season": row["source_season"],
        "kickoff_at": row["kickoff_at"],
        "settled_at": row["settled_at"],
        "home_team_id": row["home_team_source_id"],
        "away_team_id": row["away_team_source_id"],
        "home_score": row["home_score"],
        "away_score": row["away_score"],
        "normalized_status": row["normalized_status"],
    }
    payload = {"provider_fixture": dict(normalized), "source_version": 1}
    row["payload_sha256"] = canonical_payload_sha256(payload)
    row["source_payload"] = {
        "provider": row["provider"], "endpoint": row["endpoint"],
        "source_id": row["source_id"], "run_id": row["run_id"],
        "retrieved_at": row["retrieved_at"], "payload": payload,
        "payload_sha256": row["payload_sha256"],
        "normalized_record": normalized,
        "normalized_record_sha256": canonical_payload_sha256(normalized),
    }
    return row



def season_registry(*, include_prior=False, issued_at="2026-01-02T00:00:00Z",
                    valid_from="2026-01-03T00:00:00Z",
                    valid_until="2026-12-31T00:00:00Z", revoked_at=None):
    mappings = [{
        "provider": "fivedollar",
        "competition_id": "4160026622",
        "source_season": "2025/26",
        "canonical_season_id": "league:2025-2026",
        "evidence_sha256": ["d" * 64],
        "reviewer": "season-review",
        "reviewed_at": "2026-01-02T00:00:00Z",
        "valid_from": "2026-01-03T00:00:00Z",
        "valid_until": "2026-12-31T00:00:00Z",
        "revoked_at": None,
    }]
    if include_prior:
        mappings.append({
            "provider": "fivedollar",
            "competition_id": "4160026622",
            "source_season": "2024/25",
            "canonical_season_id": "league:2024-2025",
            "evidence_sha256": ["e" * 64],
            "reviewer": "season-review",
            "reviewed_at": "2026-01-02T00:00:00Z",
            "valid_from": "2026-01-03T00:00:00Z",
            "valid_until": "2026-12-31T00:00:00Z",
            "revoked_at": None,
        })
    unsigned = {
        "schema": SEASON_SCHEMA,
        "issued_at": issued_at,
        "expires_at": "2027-01-01T00:00:00Z",
        "mappings": mappings,
    }
    return sign_season_crosswalk_registry(
        kms_client=KMS, key_arn=SEASON_KEY_ARN,
        trusted_key_regions={SEASON_KEY_ARN: "eu-west-1"},
        registry=unsigned,
    )

def history_rows():
    pairings = [
        [("A", "B"), ("C", "D")],
        [("B", "C"), ("D", "A")],
        [("A", "C"), ("B", "D")],
        [("A", "D"), ("B", "C")],
        [("A", "B"), ("C", "D")],
        [("A", "C"), ("B", "D")],
    ]
    rows = []
    start = date(2026, 8, 1)
    for day_index, pair in enumerate(pairings):
        day = start + timedelta(days=day_index * 3)
        for match_index, (home, away) in enumerate(pair):
            hour = 12 + match_index * 3
            fixture_id = f"history-{day_index}-{match_index}"
            rows.append(attach_evidence({
                "fixture_id": fixture_id,
                "provider": "fivedollar",
                "source_id": fixture_id,
                "competition_id": "4160026622",
                "source_season": "2025/26",
                "kickoff_at": f"{day.isoformat()}T{hour:02d}:00:00Z",
                "settled_at": f"{day.isoformat()}T{hour + 2:02d}:00:00Z",
                "home_team_id": home,
                "away_team_id": away,
                "home_score": (day_index + match_index) % 4,
                "away_score": (day_index * 2 + match_index + 1) % 3,
                "endpoint": "/fixtures",
                "retrieved_at": f"{day.isoformat()}T{hour + 3:02d}:00:00Z",
                "payload_sha256": "",
                "run_id": "history-acquisition-run-1",
                "normalized_status": "finished",
            }))
    return rows


TARGET = {
    "fixture_id": "target-2026-09-01",
    "provider": "fivedollar",
    "source_season": "2025/26",
    "competition_id": "4160026622",
    "kickoff_at": "2026-09-01T18:00:00Z",
    "home_team_id": "A",
    "away_team_id": "B",
}

def history_with_target():
    history = history_rows()
    history.append(attach_evidence({
        "fixture_id": TARGET["fixture_id"],
        "provider": "fivedollar",
        "source_id": TARGET["fixture_id"],
        "competition_id": TARGET["competition_id"],
        "source_season": TARGET["source_season"],
        "kickoff_at": TARGET["kickoff_at"],
        "settled_at": "2026-09-01T20:00:00Z",
        "home_team_id": TARGET["home_team_id"],
        "away_team_id": TARGET["away_team_id"],
        "home_score": 2,
        "away_score": 1,
        "endpoint": "/fixtures",
        "retrieved_at": "2026-09-01T21:00:00Z",
        "payload_sha256": "",
        "run_id": "target-acquisition-run",
        "normalized_status": "finished",
    }))
    return history

LABEL = {
    "fixture_id": TARGET["fixture_id"],
    "competition_key": "4160026622",
    "kickoff_at": TARGET["kickoff_at"],
    "settled_at": "2026-09-01T20:00:00Z",
    "home_score": 2,
    "away_score": 1,
    "label_source": "fivedollar",
    "label_source_id": "result-target-2026-09-01",
    "label_retrieved_at": "2026-09-01T21:00:00Z",
    "payload_sha256": "f" * 64,
}
POLICY = {
    "train_end_date": "2026-09-30",
    "validation_start_date": "2026-10-08",
    "validation_end_date": "2026-10-20",
    "test_start_date": "2026-10-28",
    "test_end_date": "2026-11-30",
    "embargo_days": 7,
}


class ResultsTrainingDatasetAdapterTests(unittest.TestCase):
    def test_builds_pit_snapshot_with_reconstruction_source_provenance(self):
        snapshot = build_results_history_snapshot(
            historical_matches=history_with_target(), target_fixture=TARGET,
            season_crosswalk_registry=season_registry(),
            trusted_kms_clients=trusted_clients(),
            team_crosswalk_registry=TEAM_REGISTRY,
        )
        self.assertEqual(snapshot["fixture_id"], TARGET["fixture_id"])
        self.assertEqual(snapshot["feature_count"], 11)
        self.assertTrue(all(
            feature["source"] == "veltrix_results_feature_reconstruction"
            for feature in snapshot["features"]
        ))
        self.assertTrue(all(
            feature["retrieved_at"] <= snapshot["prediction_as_of"]
            for feature in snapshot["features"]
        ))

    def test_other_canonical_season_history_cannot_change_target_features(self):
        history = history_with_target()
        history.append(attach_evidence({
            "fixture_id": "prior-season-match",
            "provider": "fivedollar",
            "source_id": "prior-season-match",
            "competition_id": TARGET["competition_id"],
            "source_season": "2024/25",
            "kickoff_at": "2026-08-20T09:00:00Z",
            "settled_at": "2026-08-20T11:00:00Z",
            "home_team_id": "A",
            "away_team_id": "B",
            "home_score": 9,
            "away_score": 0,
            "endpoint": "/fixtures",
            "retrieved_at": "2026-08-20T11:30:00Z",
            "payload_sha256": "",
            "run_id": "prior-season-run",
            "normalized_status": "finished",
        }))
        registry = season_registry(include_prior=True)
        baseline = build_results_history_snapshot(
            historical_matches=history_with_target(), target_fixture=TARGET,
            season_crosswalk_registry=registry,
            trusted_kms_clients=trusted_clients(),
            team_crosswalk_registry=TEAM_REGISTRY,
        )
        mixed = build_results_history_snapshot(
            historical_matches=history, target_fixture=TARGET,
            season_crosswalk_registry=registry,
            trusted_kms_clients=trusted_clients(),
            team_crosswalk_registry=TEAM_REGISTRY,
        )
        self.assertEqual(
            {item["name"]: item["value"] for item in baseline["features"]},
            {item["name"]: item["value"] for item in mixed["features"]},
        )
        self.assertEqual(
            mixed["season_identity_evidence"]["canonical_season_id"],
            "league:2025-2026",
        )

    def test_missing_team_crosswalk_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "team_crosswalk_registry_required"):
            build_results_history_snapshot(
                historical_matches=history_with_target(),
                target_fixture=TARGET,
                season_crosswalk_registry=season_registry(),
                trusted_kms_clients=trusted_clients(),
            )

    def test_tampered_target_team_pair_evidence_is_rejected(self):
        history = history_with_target()
        target_row = next(row for row in history if row["fixture_id"] == TARGET["fixture_id"])
        target_row["team_identity_evidence"]["home_canonical_team_id"] = "tampered-team"
        with self.assertRaisesRegex(ValueError, "target_team_identity_not_valid_at_feature_cutoff"):
            build_results_history_snapshot(
                historical_matches=history,
                target_fixture=TARGET,
                season_crosswalk_registry=season_registry(),
                trusted_kms_clients=trusted_clients(),
                team_crosswalk_registry=TEAM_REGISTRY,
            )

    def test_target_without_admitted_team_pair_row_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "target_team_identity_not_valid_at_feature_cutoff"):
            build_results_history_snapshot(
                historical_matches=history_rows(),
                target_fixture=TARGET,
                season_crosswalk_registry=season_registry(),
                trusted_kms_clients=trusted_clients(),
                team_crosswalk_registry=TEAM_REGISTRY,
            )

    def test_missing_target_season_mapping_withholds_target(self):
        target = {**TARGET, "source_season": "unmapped-season"}
        with self.assertRaisesRegex(
            ValueError, "target_canonical_season_mapping_not_valid_at_feature_cutoff"
        ):
            build_results_history_snapshot(
                historical_matches=history_with_target(), target_fixture=target,
                season_crosswalk_registry=season_registry(),
                trusted_kms_clients=trusted_clients(),
            team_crosswalk_registry=TEAM_REGISTRY,
            )

    def test_expired_season_mapping_is_not_eligible_at_feature_cutoff(self):
        with self.assertRaisesRegex(
            ValueError, "target_canonical_season_mapping_not_valid_at_feature_cutoff"
        ):
            build_results_history_snapshot(
                historical_matches=history_with_target(), target_fixture=TARGET,
                season_crosswalk_registry=season_registry(
                    valid_until="2026-09-01T11:59:59Z"
                ),
                trusted_kms_clients=trusted_clients(),
                team_crosswalk_registry=TEAM_REGISTRY,
            )

    def test_revoked_season_mapping_is_not_eligible_at_feature_cutoff(self):
        with self.assertRaisesRegex(
            ValueError, "target_canonical_season_mapping_not_valid_at_feature_cutoff"
        ):
            build_results_history_snapshot(
                historical_matches=history_with_target(), target_fixture=TARGET,
                season_crosswalk_registry=season_registry(
                    revoked_at="2026-09-01T11:59:59Z"
                ),
                trusted_kms_clients=trusted_clients(),
                team_crosswalk_registry=TEAM_REGISTRY,
            )

    def test_season_mapping_requires_exact_provider_and_competition_identity(self):
        registry = season_registry()
        for changed in (
            {**TARGET, "provider": "another-provider"},
            {**TARGET, "competition_id": "another-competition"},
        ):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(
                    ValueError, "target_canonical_season_mapping_not_valid_at_feature_cutoff"
                ):
                    build_results_history_snapshot(
                        historical_matches=history_with_target(), target_fixture=changed,
                        season_crosswalk_registry=registry,
                        trusted_kms_clients=trusted_clients(),
                        team_crosswalk_registry=TEAM_REGISTRY,
                    )

    def test_provider_source_season_label_remains_in_original_payload_evidence(self):
        target_row = next(
            row for row in history_with_target() if row["fixture_id"] == TARGET["fixture_id"]
        )
        self.assertEqual(target_row["source_season"], "2025/26")
        self.assertEqual(
            target_row["source_payload"]["normalized_record"]["source_season"], "2025/26"
        )

    def test_registry_issued_after_feature_cutoff_cannot_retroactively_map_season(self):
        with self.assertRaisesRegex(ValueError, "season_crosswalk_registry_rejected_at_feature_cutoff"):
            build_results_history_snapshot(
                historical_matches=history_with_target(), target_fixture=TARGET,
                season_crosswalk_registry=season_registry(issued_at="2026-09-01T13:00:00Z"),
                trusted_kms_clients=trusted_clients(),
            team_crosswalk_registry=TEAM_REGISTRY,
            )

    def test_target_row_is_excluded_from_its_own_historical_feature_input(self):
        history = history_rows()
        target_row = attach_evidence({
            "fixture_id": TARGET["fixture_id"],
            "provider": "fivedollar",
            "source_id": TARGET["fixture_id"],
            "competition_id": TARGET["competition_id"],
            "source_season": TARGET["source_season"],
            "kickoff_at": TARGET["kickoff_at"],
            "settled_at": "2026-09-01T20:00:00Z",
            "home_team_id": TARGET["home_team_id"],
            "away_team_id": TARGET["away_team_id"],
            "home_score": 2,
            "away_score": 1,
            "endpoint": "/fixtures",
            "retrieved_at": "2026-09-01T21:00:00Z",
            "payload_sha256": "",
            "run_id": "history-acquisition-run-2",
            "normalized_status": "finished",
        })
        history.append(target_row)
        snapshot = build_results_history_snapshot(
            historical_matches=history, target_fixture=TARGET,
            season_crosswalk_registry=season_registry(),
            trusted_kms_clients=trusted_clients(),
            team_crosswalk_registry=TEAM_REGISTRY,
        )
        self.assertEqual(snapshot["fixture_id"], TARGET["fixture_id"])
        self.assertEqual(snapshot["feature_count"], 11)

    def test_assembles_snapshot_and_settled_label_into_chronological_dataset(self):
        result = assemble_results_history_dataset(
            historical_matches=history_with_target(),
            target_fixtures=[TARGET],
            settled_labels=[LABEL],
            split_policy=POLICY,
            season_crosswalk_registry=season_registry(),
            trusted_kms_clients=trusted_clients(),
            team_crosswalk_registry=TEAM_REGISTRY,
        )
        self.assertEqual(result["feature_reconstruction"]["snapshot_count"], 1)
        self.assertEqual(result["dataset"]["quality"]["included_fixture_count"], 1)
        self.assertEqual(result["dataset"]["rows"][0]["split"], "train")
        self.assertFalse(result["dataset"]["training_readiness"]["ready_for_model_training"])
        self.assertEqual(result["feature_reconstruction"]["database_writes"], 0)

    def test_withholds_history_retrieved_after_target_feature_cutoff(self):
        history = history_with_target()
        for row in history:
            if row["fixture_id"] != TARGET["fixture_id"] and "A" in (row["home_team_id"], row["away_team_id"]):
                row["retrieved_at"] = "2026-09-01T13:00:00Z"
                attach_evidence(row)
        result = assemble_results_history_dataset(
            historical_matches=history,
            target_fixtures=[TARGET],
            settled_labels=[LABEL],
            split_policy=POLICY,
            season_crosswalk_registry=season_registry(),
            trusted_kms_clients=trusted_clients(),
            team_crosswalk_registry=TEAM_REGISTRY,
        )
        self.assertEqual(result["feature_reconstruction"]["snapshot_count"], 0)
        self.assertEqual(result["feature_reconstruction"]["withheld_count"], 1)
        self.assertEqual(result["dataset"]["quality"]["included_fixture_count"], 0)


if __name__ == "__main__":
    unittest.main()
