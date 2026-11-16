import json

import pytest

from scripts.veltrix_v2.apply_openplay_exact_identity_crosswalk import apply_crosswalk


def test_crosswalk_write_requires_explicit_environment_switch(monkeypatch, tmp_path):
    candidate = tmp_path / "candidates.json"
    candidate.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("VELTRIX_ENABLE_OPENPLAY_CROSSWALK_WRITE", raising=False)
    with pytest.raises(RuntimeError, match="OPENPLAY_CROSSWALK_WRITE_NOT_EXPLICITLY_ENABLED"):
        apply_crosswalk("", candidate)


def test_crosswalk_apply_rejects_unqualified_candidate_file(monkeypatch, tmp_path):
    candidate = tmp_path / "candidates.json"
    candidate.write_text(json.dumps({"summary":{"status":"NOT_QUALIFIED"}}), encoding="utf-8")
    monkeypatch.setenv("VELTRIX_ENABLE_OPENPLAY_CROSSWALK_WRITE", "YES")
    with pytest.raises(RuntimeError, match="OPENPLAY_CROSSWALK_DATABASE_HOST_MISMATCH"):
        apply_crosswalk("postgresql://invalid.invalid/db", candidate)


def test_crosswalk_apply_rejects_changed_candidate_counts_before_database_write(monkeypatch, tmp_path):
    candidate = tmp_path / "candidates.json"
    candidate.write_text(json.dumps({"summary":{"status":"READ_ONLY_CROSSWALK_CANDIDATES_BUILT"},
                                     "teams":[],"competitions":[]}), encoding="utf-8")
    monkeypatch.setenv("VELTRIX_ENABLE_OPENPLAY_CROSSWALK_WRITE", "YES")
    with pytest.raises(RuntimeError, match="OPENPLAY_CROSSWALK_CANDIDATE_COUNTS_CHANGED"):
        apply_crosswalk("postgresql://ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech/db", candidate)
