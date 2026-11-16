from veltrix_v2.providers.odds_api_v4.quota_headers import parse_quota_headers


def test_parses_documented_headers_case_insensitively():
    result = parse_quota_headers([
        ("X-Requests-Used", " 120 "),
        ("x-requests-remaining", "880"),
        ("X-Requests-Last", "2"),
        ("content-type", "application/json"),
    ])
    assert result.complete
    assert (result.requests_used, result.requests_remaining, result.requests_last) == (
        120, 880, 2
    )
    assert result.raw_headers == (
        ("x-requests-used", " 120 "),
        ("x-requests-remaining", "880"),
        ("x-requests-last", "2"),
    )


def test_missing_header_remains_unknown_not_zero():
    result = parse_quota_headers([
        ("x-requests-used", "1"),
        ("x-requests-last", "1"),
    ])
    assert result.requests_remaining is None
    assert not result.complete
    assert "X_REQUESTS_REMAINING_MISSING" in result.reason_codes


def test_duplicate_case_variant_is_rejected_as_ambiguous():
    result = parse_quota_headers([
        ("x-requests-used", "1"),
        ("X-Requests-Used", "2"),
        ("x-requests-remaining", "99"),
        ("x-requests-last", "1"),
    ])
    assert result.requests_used is None
    assert "X_REQUESTS_USED_DUPLICATE" in result.reason_codes


def test_malformed_boolean_signed_float_and_non_ascii_digits_fail_closed():
    for value in ("-1", "+1", "1.0", "true", "１２"):
        result = parse_quota_headers([
            ("x-requests-used", value),
            ("x-requests-remaining", "9"),
            ("x-requests-last", "1"),
        ])
        assert result.requests_used is None
        assert "X_REQUESTS_USED_MALFORMED" in result.reason_codes


def test_untrusted_unknown_headers_are_not_included_in_evidence():
    base = [
        ("x-requests-used", "10"),
        ("x-requests-remaining", "90"),
        ("x-requests-last", "1"),
    ]
    with_unknown = base + [("x-api-key", "do-not-retain")]
    assert parse_quota_headers(base).evidence_sha256 == parse_quota_headers(
        with_unknown
    ).evidence_sha256
    assert "x-api-key" not in repr(parse_quota_headers(with_unknown).raw_headers)


def test_evidence_hash_binds_exact_retained_raw_values():
    a = parse_quota_headers([
        ("x-requests-used", "10"), ("x-requests-remaining", "90"),
        ("x-requests-last", "1"),
    ])
    b = parse_quota_headers([
        ("x-requests-used", " 10 "), ("x-requests-remaining", "90"),
        ("x-requests-last", "1"),
    ])
    assert a.evidence_sha256 != b.evidence_sha256


def test_invalid_pair_is_diagnostic_and_never_crashes():
    result = parse_quota_headers([
        ("x-requests-used", "1"),
        ("x-requests-remaining", "9"),
        ("x-requests-last", "1"),
        ("bad-pair",),
    ])
    assert not result.complete
    assert "QUOTA_HEADER_PAIR_INVALID" in result.reason_codes
