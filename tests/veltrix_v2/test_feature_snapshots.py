from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.features import FeatureSnapshot, FeatureValue

T = datetime(2026, 11, 11, 6, tzinfo=timezone.utc)


def feature(**overrides):
    args = dict(name="home_attack_rate", value=1.4, source_observation_ids=("obs-1",),
                computed_at_utc=T, cutoff_utc=T, sample_size=12, quality_state="valid")
    args.update(overrides)
    return FeatureValue(**args)


def test_valid_snapshot_has_shared_cutoff():
    snap = FeatureSnapshot("strikerapi", "fx-1", T, "features-0.1", (feature(),))
    assert snap.features[0].value == 1.4


def test_missing_value_requires_reason_and_missing_state():
    with pytest.raises(ValueError, match="reason code"):
        feature(value=None)
    with pytest.raises(ValueError, match="quality_state=missing"):
        feature(value=None, missing_reason="no history", quality_state="valid")
    assert feature(value=None, missing_reason="no history", quality_state="missing").value is None


def test_snapshot_rejects_duplicate_feature_names():
    with pytest.raises(ValueError, match="unique"):
        FeatureSnapshot("strikerapi", "fx-1", T, "features-0.1", (feature(), feature()))


def test_feature_computation_must_not_occur_after_cutoff():
    with pytest.raises(ValueError, match="after its cutoff"):
        feature(computed_at_utc=T + timedelta(seconds=1))


def test_snapshot_accepts_feature_computed_before_cutoff():
    early = feature(computed_at_utc=T - timedelta(seconds=30))
    snap = FeatureSnapshot("strikerapi", "fx-1", T, "features-0.1", (early,))
    assert snap.features[0].computed_at_utc == T - timedelta(seconds=30)


def test_rejects_nonfinite_features():
    with pytest.raises(ValueError, match="finite"):
        feature(value=float("nan"))
