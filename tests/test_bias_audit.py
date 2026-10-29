from app.bias_audit import audit_favourites_and_underdogs


def test_audit_separates_market_favourite_and_underdog_wins():
    rows = [
        {"actual": "H", "model": {"H": 0.55, "D": 0.25, "A": 0.20},
         "market": {"H": 0.60, "D": 0.25, "A": 0.15}},
        {"actual": "A", "model": {"H": 0.30, "D": 0.25, "A": 0.45},
         "market": {"H": 0.55, "D": 0.25, "A": 0.20}},
        {"actual": "D", "model": {"H": 0.35, "D": 0.35, "A": 0.30},
         "market": {"H": 0.40, "D": 0.30, "A": 0.30}},
    ]
    result = audit_favourites_and_underdogs(rows)
    assert result["overall"]["matches"] == 3
    assert result["favourite_wins"]["matches"] == 1
    assert result["underdog_wins"]["matches"] == 1
    assert result["matches_with_market_classification"] == 3
    assert result["status"] == "diagnostic_only"


def test_audit_excludes_invalid_probabilities_without_crashing():
    rows = [
        {"actual": "H", "model": {"H": 2, "D": 0, "A": -1},
         "market": {"H": 0.5, "D": 0.3, "A": 0.2}},
        {"actual": "X", "model": {"H": 0.5, "D": 0.3, "A": 0.2},
         "market": {"H": 0.5, "D": 0.3, "A": 0.2}},
    ]
    result = audit_favourites_and_underdogs(rows)
    assert result["overall"]["matches"] == 0
    assert result["excluded_invalid_rows"] == 2
