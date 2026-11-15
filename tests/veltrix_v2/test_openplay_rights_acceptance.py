from __future__ import annotations

import hashlib
import json

from scripts.veltrix_v2 import qualify_openplay_release as openplay


def test_openplay_authorization_record_is_present_and_hash_bound():
    evidence = openplay.authorization_evidence()
    raw = openplay.AUTHORIZATION_RECORD.read_bytes()
    assert evidence["sha256"] == hashlib.sha256(raw).hexdigest()
    assert evidence["uri"] == openplay.AUTHORIZATION_URI
    assert evidence["status"] == "USER_CONFIRMED_NONCOMMERCIAL_AUTHORIZATION"
    assert evidence["rights_basis"] == "WRITTEN_PERMISSION"


def test_openplay_authorization_allows_research_and_training_but_not_monetisation():
    evidence = openplay.authorization_evidence()
    permitted = set(evidence["permitted_uses"])
    assert {"collection", "storage", "historical_import", "internal_analysis",
            "model_training", "model_validation", "derived_research"} <= permitted
    assert evidence["commercial_use_allowed"] is False
    assert evidence["raw_redistribution_allowed"] is False


def test_openplay_qualifier_does_not_reclassify_archive_as_historical_pit():
    source = openplay.AUTHORIZATION_RECORD.read_text(encoding="utf-8")
    assert "non-commercial" in source.casefold()
    script = openplay.__file__
    text = open(script, encoding="utf-8").read()
    assert '"production_approved": False' in text
    assert '"rights_review_required": False' in text
    assert '"training_approved": not bool(schema_failures)' in text
    assert '"commercial_use_allowed": False' in text
