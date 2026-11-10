import copy
import hashlib
import json
import pytest

from app.poisson_dixon_coles_model import (
    MODEL_FAMILY, PoissonModelError, fit_poisson_dixon_coles,
    predict_poisson_dixon_coles,
)


def _rows(n=120):
    rows = []
    teams = ["A", "B", "C", "D"]
    for i in range(n):
        day = i % 28 + 1
        month = 1 if i < 60 else 2
        comp = "EPL" if i < 60 else "Ligue1"
        home, away = teams[(i // 2) % 4], teams[(i // 2 + 1) % 4]
        if home == away:
            away = teams[(teams.index(home) + 1) % 4]
        rows.append({
            "competition_key": comp, "fixture_id": f"fx-{i}",
            "kickoff_at": f"2025-{month:02d}-{day:02d}T15:00:00Z",
            "settled_at": f"2025-{month:02d}-{day:02d}T17:00:00Z",
            "home_team_id": home, "away_team_id": away,
            "home_score": (i * 3 + 1) % 4, "away_score": (i * 7 + 2) % 3,
            "source_record_sha256": hashlib.sha256(f"source-{i}".encode()).hexdigest(),
        })
    return rows


def _fit(rows=None):
    rows = rows or _rows()
    ids = [r["fixture_id"] for r in rows]
    return fit_poisson_dixon_coles(
        history=rows, training_cutoff="2025-03-01T00:00:00Z",
        trained_at="2025-03-01T00:01:00Z",
        dataset_sha256="a" * 64, train_fixture_ids=ids,
        validation_fixture_ids=["validation-only"],
        test_fixture_ids=["test-only"], iterations=400,
    )


def test_fit_seals_independent_artifact_and_prediction_is_shadow_only():
    model = _fit()
    assert model["model_family"] == MODEL_FAMILY
    assert model["publication_allowed"] is False
    assert model["value_betting_enabled"] is False
    pred = predict_poisson_dixon_coles(
        artifact=model,
        fixture={"fixture_id": "future", "competition_key": "EPL",
                 "home_team_id": "A", "away_team_id": "B",
                 "kickoff_at": "2025-03-05T15:00:00Z",
                 "feature_as_of": "2025-03-04T00:00:00Z"},
    )
    assert sum(pred["markets"]["1x2"].values()) == pytest.approx(1.0)
    assert pred["publication_allowed"] is False


def test_artifact_tampering_is_detected():
    model = _fit()
    altered = copy.deepcopy(model)
    altered["rho"] = 0.12
    with pytest.raises(PoissonModelError, match="artifact_digest"):
        predict_poisson_dixon_coles(
            artifact=altered,
            fixture={"fixture_id": "f", "competition_key": "EPL",
                     "home_team_id": "A", "away_team_id": "B",
                     "kickoff_at": "2025-03-05T15:00:00Z",
                     "feature_as_of": "2025-03-04T00:00:00Z"},
        )


def test_training_rejects_validation_or_test_rows_in_train_payload():
    rows = _rows()
    ids = [r["fixture_id"] for r in rows]
    with pytest.raises(PoissonModelError, match="training_manifest_mismatch"):
        fit_poisson_dixon_coles(
            history=rows + [{**rows[0], "fixture_id": "test-only"}],
            training_cutoff="2025-03-01T00:00:00Z",
            trained_at="2025-03-01T00:01:00Z",
            dataset_sha256="a" * 64, train_fixture_ids=ids,
            validation_fixture_ids=["validation-only"],
            test_fixture_ids=["test-only"], iterations=400,
        )


def test_training_rejects_label_settled_after_cutoff():
    rows = _rows()
    rows[0]["settled_at"] = "2025-03-02T00:00:00Z"
    with pytest.raises(PoissonModelError, match="label_temporal_order"):
        _fit(rows)


def test_prediction_rejects_future_feature_or_unseen_team():
    model = _fit()
    base = {"fixture_id": "future", "competition_key": "EPL",
            "home_team_id": "A", "away_team_id": "B",
            "kickoff_at": "2025-03-05T15:00:00Z",
            "feature_as_of": "2025-03-05T16:00:00Z"}
    with pytest.raises(PoissonModelError, match="temporal_order"):
        predict_poisson_dixon_coles(artifact=model, fixture=base)
    base["feature_as_of"] = "2025-03-04T00:00:00Z"
    base["home_team_id"] = "new-team"
    with pytest.raises(PoissonModelError, match="team_unseen"):
        predict_poisson_dixon_coles(artifact=model, fixture=base)


def test_fit_is_deterministic():
    first, second = _fit(), _fit()
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["rho"] == second["rho"]


def test_minimum_training_and_manifest_are_enforced():
    rows = _rows(99)
    ids = [r["fixture_id"] for r in rows]
    with pytest.raises(PoissonModelError, match="minimum_100"):
        fit_poisson_dixon_coles(
            history=rows, training_cutoff="2025-03-01T00:00:00Z",
            trained_at="2025-03-01T00:01:00Z", dataset_sha256="a" * 64,
            train_fixture_ids=ids, validation_fixture_ids=[],
            test_fixture_ids=[], iterations=400,
        )
