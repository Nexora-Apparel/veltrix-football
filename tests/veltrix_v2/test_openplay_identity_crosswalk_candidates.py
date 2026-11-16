from scripts.veltrix_v2.build_openplay_identity_crosswalk_candidates import (
    normalize_name,
    parse_comp_codes,
)


def test_normalize_name_only_normalizes_unicode_case_and_whitespace():
    assert normalize_name("  FC   Barcelona ") == "fc barcelona"
    assert normalize_name("Bayern München") == normalize_name("BAYERN MÜNCHEN")
    assert normalize_name("Man Utd") != normalize_name("Manchester United")


def test_parse_comp_codes_handles_lists_and_serialized_values():
    assert parse_comp_codes(["ENG1", "ESP1", "ENG1"]) == ["ENG1", "ESP1"]
    assert parse_comp_codes('["ENG1","FRA1"]') == ["ENG1", "FRA1"]
    assert parse_comp_codes("ENG1;FRA1|ITA1") == ["ENG1", "FRA1", "ITA1"]
    assert parse_comp_codes(None) == []
