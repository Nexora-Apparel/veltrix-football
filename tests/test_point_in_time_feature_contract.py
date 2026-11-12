import hashlib
import json
import unittest

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

    def test_snapshot_tampering_is_rejected(self):
        snapshot = build_point_in_time_feature_snapshot(
            fixture_id="fixture-1", prediction_as_of=CUTOFF, features=[BASE],
        )
        snapshot["features"][0]["value"] = 0
        with self.assertRaisesRegex(PointInTimeFeatureError, "hash_mismatch"):
            validate_point_in_time_feature_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
