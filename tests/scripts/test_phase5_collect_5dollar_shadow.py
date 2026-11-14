from scripts import phase5_collect_5dollar_shadow as capture


def test_admitted_prediction_tuple_is_normalized_before_staging(monkeypatch):
    admitted = (object(), object())
    observed = {}

    def fake_persist(dsn, predictions):
        observed["dsn"] = dsn
        observed["predictions"] = predictions
        return {"events_appended": len(predictions)}

    monkeypatch.setattr(
        capture, "_persist_paper_predictions_to_staging", fake_persist
    )

    result = capture._persist_admitted_predictions_to_staging(
        "postgresql://staging", admitted
    )

    assert observed["dsn"] == "postgresql://staging"
    assert isinstance(observed["predictions"], list)
    assert observed["predictions"] == list(admitted)
    assert result == {"events_appended": 2}
