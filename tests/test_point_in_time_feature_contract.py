import hashlib
import json
import unittest

from app.feature_source_qualification import (
    SCHEMA as FEATURE_SOURCE_SCHEMA, sign_feature_source_qualification_registry,
    verify_feature_source_qualification_registry,
)
from app.point_in_time_feature_contract import (
    PointInTimeFeatureError,
    build_point_in_time_feature_snapshot,
    validate_point_in_time_feature_snapshot,
)


CUTOFF = "2026-11-10T05:00:00Z"
BASE = {
    "name": "home_team_elo",
    "value": 1512.5,
    "source": "veltrix_elo",
    "source_id": "team-123-rating-2026-11-10",
    "observed_at": "2026-11-09T05:00:00Z",
    "available_at": "2026-11-09T05:00:00Z",
    "retrieved_at": "2026-11-09T05:01:00Z",
    "payload_sha256": "a" * 64,
}


class FakeKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}

    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}


FEATURE_KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/pit-feature-test"


def verified_feature_registry():
    kms = FakeKms()
    registry = sign_feature_source_qualification_registry(
        kms_client=kms, key_arn=FEATURE_KEY_ARN,
        trusted_key_regions={FEATURE_KEY_ARN: "eu-west-1"},
        registry={
            "schema": FEATURE_SOURCE_SCHEMA,
            "issued_at": "2026-10-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "sources": [{
                "source": "provider-x",
                "qualified_features": ["home_rolling_xg_for"],
                "supported_competitions": ["league-a"],
                "observed_at_semantics": "measurement_timestamp",
                "available_at_semantics": "first_publication_timestamp",
                "qualification_evidence_sha256": ["a" * 64],
                "reviewer": "data-governance",
                "qualified_at": "2026-10-01T00:00:00Z",
                "valid_from": "2026-10-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
                "revoked_at": None,
            }],
        },
    )
    return verify_feature_source_qualification_registry(
        registry=registry, trusted_kms_clients={FEATURE_KEY_ARN: kms},
        as_of="2026-11-10T00:00:00Z",
    )


def valid_team_identity_evidence(**overrides):
    value = {
        "home_source_team_id": "source-home",
        "away_source_team_id": "source-away",
        "home_canonical_team_id": "canonical-home",
        "away_canonical_team_id": "canonical-away",
        "team_scope": "men_first_team",
        "home_mapping_evidence_sha256": ["b" * 64],
        "away_mapping_evidence_sha256": ["c" * 64],
        "home_mapping_reviewer": "identity-reviewer",
        "away_mapping_reviewer": "identity-reviewer",
        "home_mapping_reviewed_at": "2026-10-01T00:00:00Z",
        "away_mapping_reviewed_at": "2026-10-01T00:00:00Z",
        "registry_sha256": "d" * 64,
        "signing_key_arn": "arn:aws:kms:eu-west-1:123456789012:key/team-test",
        "verified_at": CUTOFF,
        "source_verified_at": "2026-11-09T00:00:00Z",
    }
    value.update(overrides)
    return value


class PointInTimeFeatureContractTests(unittest.TestCase):
    def test_valid_snapshot_is_deterministic_and_target_is_separate(self):
        first = build_point_in_time_feature_snapshot(
            fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[BASE],
        )
        second = build_point_in_time_feature_snapshot(
            fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[BASE],
        )
        self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])
        self.assertTrue(validate_point_in_time_feature_snapshot(first)["valid"])
        self.assertFalse(first["model_training_certified"])

    def test_team_identity_evidence_is_bound_into_snapshot_digest(self):
        snapshot = build_point_in_time_feature_snapshot(
            fixture_id="fixture-team", prediction_as_of=CUTOFF, features=[BASE],
            team_identity_evidence=valid_team_identity_evidence(),
        )
        self.assertTrue(validate_point_in_time_feature_snapshot(snapshot)["valid"])
        self.assertEqual(snapshot["team_identity_evidence"]["team_scope"], "men_first_team")
        tampered = dict(snapshot)
        tampered["team_identity_evidence"] = dict(snapshot["team_identity_evidence"])
        tampered["team_identity_evidence"]["team_scope"] = "women_first_team"
        with self.assertRaises(PointInTimeFeatureError):
            validate_point_in_time_feature_snapshot(tampered)

    def test_team_identity_registry_not_verified_at_feature_cutoff_is_rejected(self):
        with self.assertRaisesRegex(PointInTimeFeatureError, "team_identity_verified_after_cutoff"):
            build_point_in_time_feature_snapshot(
                fixture_id="fixture-team", prediction_as_of=CUTOFF, features=[BASE],
                team_identity_evidence=valid_team_identity_evidence(
                    verified_at="2026-11-10T05:00:01Z"
                ),
            )

    def test_future_observation_availability_and_retrieval_are_rejected(self):
        for field, value in (
            ("observed_at", "2026-11-10T05:01:00Z"),
            ("available_at", "2026-11-10T05:01:00Z"),
            ("retrieved_at", "2026-11-10T05:01:00Z"),
        ):
            feature = dict(BASE)
            feature[field] = value
            with self.subTest(field=field), self.assertRaises(PointInTimeFeatureError):
                build_point_in_time_feature_snapshot(
                    fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[feature],
                )

    def test_post_match_targets_and_unknown_features_are_rejected(self):
        for name in ("home_score", "result", "post_match_xg", "unapproved_feature"):
            feature = dict(BASE, name=name)
            with self.subTest(name=name), self.assertRaises(PointInTimeFeatureError):
                build_point_in_time_feature_snapshot(
                    fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[feature],
                )

    def test_stale_odds_and_duplicate_features_are_rejected(self):
        odds = dict(BASE, name="odds_home_decimal", observed_at="2026-11-10T04:00:00Z",
                    available_at="2026-11-10T04:00:00Z", retrieved_at="2026-11-10T04:01:00Z")
        with self.assertRaisesRegex(PointInTimeFeatureError, "stale_feature"):
            build_point_in_time_feature_snapshot(
                fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[odds],
            )
        with self.assertRaisesRegex(PointInTimeFeatureError, "duplicate_feature"):
            build_point_in_time_feature_snapshot(
                fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[BASE, BASE],
            )

    def test_naive_timestamps_and_nonfinite_values_are_rejected(self):
        naive = dict(BASE, observed_at="2026-11-09T05:00:00")
        with self.assertRaisesRegex(PointInTimeFeatureError, "timezone_missing"):
            build_point_in_time_feature_snapshot(
                fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[naive],
            )
        invalid = dict(BASE, value=float("nan"))
        with self.assertRaisesRegex(PointInTimeFeatureError, "value_invalid"):
            build_point_in_time_feature_snapshot(
                fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[invalid],
            )


    def test_rehashed_artifact_with_future_or_reversed_provenance_is_rejected(self):
        for changes in (
            {"retrieved_at": "2026-11-10T05:01:00Z"},
            {"available_at": "2026-11-09T04:59:00Z"},
        ):
            snapshot = build_point_in_time_feature_snapshot(
                fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[BASE],
            )
            snapshot["features"][0].update(changes)
            snapshot.pop("snapshot_sha256")
            snapshot["snapshot_sha256"] = hashlib.sha256(
                json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
            ).hexdigest()
            with self.subTest(changes=changes), self.assertRaises(PointInTimeFeatureError):
                validate_point_in_time_feature_snapshot(snapshot)

    def test_rehashed_artifact_cannot_smuggle_extra_feature_fields(self):
        snapshot = build_point_in_time_feature_snapshot(
            fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[BASE],
        )
        snapshot["features"][0]["home_score"] = 3
        snapshot.pop("snapshot_sha256")
        snapshot["snapshot_sha256"] = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False).encode("utf-8")
        ).hexdigest()
        with self.assertRaisesRegex(PointInTimeFeatureError, "shape_invalid"):
            validate_point_in_time_feature_snapshot(snapshot)

    def test_signed_feature_source_qualification_is_embedded_in_snapshot(self):
        feature = dict(
            BASE, name="home_rolling_xg_for", source="provider-x",
        )
        snapshot = build_point_in_time_feature_snapshot(
            fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[feature],
            verified_source_registry=verified_feature_registry(),
            competition_id="league-a",
        )
        self.assertTrue(validate_point_in_time_feature_snapshot(snapshot)["valid"])
        evidence = snapshot["features"][0]["source_qualification"]
        self.assertEqual(evidence["signing_key_arn"], FEATURE_KEY_ARN)
        self.assertEqual(evidence["observed_at_semantics"], "measurement_timestamp")

    def test_unqualified_feature_source_and_competition_are_rejected(self):
        feature = dict(BASE, name="home_rolling_xg_for", source="provider-x")
        with self.assertRaisesRegex(PointInTimeFeatureError, "feature_source_competition_unsupported"):
            build_point_in_time_feature_snapshot(
                fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[feature],
                verified_source_registry=verified_feature_registry(),
                competition_id="league-b",
            )
        feature["source"] = "unqualified-provider"
        with self.assertRaisesRegex(PointInTimeFeatureError, "feature_source_not_qualified"):
            build_point_in_time_feature_snapshot(
                fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[feature],
                verified_source_registry=verified_feature_registry(),
                competition_id="league-a",
            )

    def test_source_qualification_evidence_tampering_is_rejected(self):
        feature = dict(BASE, name="home_rolling_xg_for", source="provider-x")
        snapshot = build_point_in_time_feature_snapshot(
            fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[feature],
            verified_source_registry=verified_feature_registry(),
            competition_id="league-a",
        )
        snapshot["features"][0]["source_qualification"]["registry_sha256"] = "0" * 64
        with self.assertRaisesRegex(PointInTimeFeatureError, "hash_mismatch"):
            validate_point_in_time_feature_snapshot(snapshot)

    def test_snapshot_tampering_is_rejected(self):
        snapshot = build_point_in_time_feature_snapshot(
            fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[BASE],
        )
        snapshot["features"][0]["value"] = 0
        with self.assertRaisesRegex(PointInTimeFeatureError, "hash_mismatch"):
            validate_point_in_time_feature_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
