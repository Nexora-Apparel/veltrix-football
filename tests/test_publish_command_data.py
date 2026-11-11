from datetime import datetime, timezone

from scripts.publish_command_data import _archive_report_path, _valid_recent_cache
from app.independent_report_contract import MODEL_PORTFOLIO_ID, REPORT_SCHEMA


def authorized_report(report):
    return {
        **report,
        "report_schema": REPORT_SCHEMA,
        "model_portfolio_id": MODEL_PORTFOLIO_ID,
        "legacy_model_dependency": False,
        "publication_allowed": True,
        "release_certificate": {
            "status": "CERTIFIED", "publication_authorized": True,
            "signature_verified": True, "certificate_sha256": "a" * 64,
            "model_portfolio_id": MODEL_PORTFOLIO_ID,
        },
    }


def test_recent_cache_publisher_accepts_current_v2_schema():
    assert _valid_recent_cache({
        "version": 2,
        "matches": [{"date": "2026-10-27"}],
        "state": {"next_backfill_end_date": "2026-10-20"},
    })


def test_recent_cache_publisher_accepts_legacy_v1_schema():
    assert _valid_recent_cache({
        "version": 1,
        "matches": [],
        "state": {},
    })


def test_recent_cache_publisher_rejects_invalid_schema():
    assert not _valid_recent_cache({"version": 3, "matches": [], "state": {}})
    assert not _valid_recent_cache({"version": 2, "matches": []})
    assert not _valid_recent_cache({"version": 2, "matches": [], "state": None})



def test_daily_report_archive_path_is_date_scoped_and_immutable():
    report = {"as_of_date": "2026-10-31"}
    published = datetime(2026, 10, 31, 15, 30, 12, 123456, tzinfo=timezone.utc)
    assert _archive_report_path(report, published) == (
        "public-data/archive/2026-10-31/daily_predictions_20261031T153012123456Z.json"
    )


def test_daily_report_archive_path_rejects_invalid_report_date():
    import pytest

    with pytest.raises(ValueError):
        _archive_report_path({"as_of_date": "not-a-date"}, datetime.now(timezone.utc))


def test_publisher_refuses_legacy_daily_prediction_artifacts(tmp_path):
    import json
    import pytest
    from scripts.publish_command_data import publish

    target = tmp_path / "daily_predictions.json"
    target.write_text(json.dumps({
        "as_of_date": "2026-11-11",
        "predictions": [{"home_team": "Legacy FC", "probabilities": {}}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="LEGACY_OR_UNCERTIFIED_REPORT_PUBLICATION_BLOCKED"):
        publish("public-data/daily_predictions.json", target, "owner/repo", "token")


def test_large_json_snapshot_uses_git_data_api_without_four_mb_rejection(tmp_path, monkeypatch):
    import json
    from scripts import publish_command_data as publisher

    payload = {"observations": ["x" * 1000 for _ in range(1000)]}
    target = tmp_path / "large.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    calls = []

    def fake_github_json(url, token, method="GET", body=None):
        calls.append((url, method, body))
        if url.endswith("/git/ref/heads/command-data"):
            return {"object": {"sha": "head-sha"}}
        if url.endswith("/git/commits/head-sha"):
            return {"tree": {"sha": "tree-base"}}
        if url.endswith("/git/blobs"):
            return {"sha": "blob-sha"}
        if url.endswith("/git/trees"):
            return {"sha": "tree-new"}
        if url.endswith("/git/commits"):
            return {"sha": "commit-new"}
        if url.endswith("/git/refs/heads/command-data"):
            return {"ref": "refs/heads/command-data"}
        raise AssertionError(url)

    monkeypatch.setattr(publisher, "_github_json", fake_github_json)
    publisher.publish("public-data/value_evidence_ledger.json", target, "owner/repo", "token")
    assert len(target.read_bytes()) > 900_000
    assert any(url.endswith("/git/blobs") and method == "POST" for url, method, _ in calls)
    assert any(url.endswith("/git/refs/heads/command-data") and method == "PATCH" for url, method, _ in calls)


def test_large_blob_publication_preserves_existing_branch_tree(tmp_path, monkeypatch):
    from scripts import publish_command_data as publisher

    target = tmp_path / "snapshot.json"
    target.write_text('{"data":"' + ("a" * 950_000) + '"}', encoding="utf-8")
    requests = []

    def fake_github_json(url, token, method="GET", body=None):
        requests.append((url, method, body))
        if url.endswith("/git/ref/heads/command-data"):
            return {"object": {"sha": "parent"}}
        if url.endswith("/git/commits/parent"):
            return {"tree": {"sha": "base-tree"}}
        if url.endswith("/git/blobs"):
            return {"sha": "new-blob"}
        if url.endswith("/git/trees"):
            assert body["base_tree"] == "base-tree"
            return {"sha": "new-tree"}
        if url.endswith("/git/commits"):
            assert body["parents"] == ["parent"]
            return {"sha": "new-commit"}
        if url.endswith("/git/refs/heads/command-data"):
            assert body == {"sha": "new-commit", "force": False}
            return {}
        raise AssertionError(url)

    monkeypatch.setattr(publisher, "_github_json", fake_github_json)
    publisher.publish("public-data/recent_results_cache.json", target, "owner/repo", "token")
    assert len(requests) == 6


def test_one_snapshot_failure_does_not_block_later_publications(tmp_path, monkeypatch):
    import json
    import sys
    from scripts import publish_command_data as publisher

    report = tmp_path / "report.json"
    ledger = tmp_path / "paper.json"
    evidence = tmp_path / "evidence.json"
    cache = tmp_path / "cache.json"
    report.write_text(json.dumps(authorized_report({
        "as_of_date": "2026-11-02",
        "predictions": [],
    })), encoding="utf-8")
    ledger.write_text(json.dumps({
        "ledger_schema": "VELTRIX_INDEPENDENT_PAPER_LEDGER_V1",
        "model_portfolio_id": MODEL_PORTFOLIO_ID,
        "legacy_model_dependency": False,
        "model_status": "PAPER_TRACKING_ONLY",
        "cumulative_metrics_by_model": {},
        "scored_matches": [],
    }), encoding="utf-8")
    evidence.write_text(json.dumps({
        "version": "VELTRIX_VALUE_EVIDENCE_V1",
        "release_status": "LOCKED_SHADOW_MODE",
        "observations": [],
    }), encoding="utf-8")
    cache.write_text(json.dumps({
        "version": 2,
        "matches": [],
        "state": {},
    }), encoding="utf-8")

    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(sys, "argv", [
        "publish_command_data.py",
        "--report", str(report),
        "--ledger", str(ledger),
        "--value-evidence", str(evidence),
        "--recent-cache", str(cache),
    ])

    attempted = []

    def fake_publish(path, local_file, repo, token):
        attempted.append(path)
        if path == "public-data/value_evidence_ledger.json":
            raise OSError("simulated large-snapshot publication failure")

    monkeypatch.setattr(publisher, "publish", fake_publish)

    assert publisher.main() == 1
    assert "public-data/daily_predictions.json" in attempted
    assert "public-data/paper_tracking_ledger.json" in attempted
    assert "public-data/value_evidence_ledger.json" in attempted
    assert "public-data/recent_results_cache.json" in attempted


def test_publication_marker_confirms_live_report_but_preserves_reuse_warning():
    from datetime import datetime, timezone
    from scripts.publish_command_data import _mark_report_publication

    published_at = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    live = {
        "publication_status": "LIVE_REPORT_GENERATED_PENDING_PUBLICATION",
        "publication_notice": "Generated from this run's live fixture response.",
    }
    _mark_report_publication(live, published_at)
    assert live["publication_status"] == "PUBLISHED"
    assert live["command_data_publication"] == "PUBLISHED"
    assert "publication to command-data is confirmed" in live["publication_notice"]

    reused = {
        "publication_status": "REUSED_SNAPSHOT_NOT_REFRESHED",
        "publication_notice": "A previously generated report was reused.",
    }
    _mark_report_publication(reused, published_at)
    assert reused["publication_status"] == "REUSED_SNAPSHOT_NOT_REFRESHED"
    assert reused["command_data_publication"] == "PUBLISHED"
    assert reused["publication_notice"] == "A previously generated report was reused."



def test_large_blob_publication_retries_when_command_data_branch_moves(tmp_path, monkeypatch):
    import io
    from urllib.error import HTTPError
    from scripts import publish_command_data as publisher

    target = tmp_path / "large.json"
    target.write_text('{"data":"' + ("x" * 950_000) + '"}', encoding="utf-8")
    calls = []
    ref_reads = 0
    patch_attempts = 0

    def fake_github_json(url, token, method="GET", body=None):
        nonlocal ref_reads, patch_attempts
        calls.append((url, method, body))
        if url.endswith("/git/ref/heads/command-data"):
            ref_reads += 1
            return {"object": {"sha": f"head-{ref_reads}"}}
        if url.endswith("/git/commits/head-1"):
            return {"tree": {"sha": "base-tree-1"}}
        if url.endswith("/git/commits/head-2"):
            return {"tree": {"sha": "base-tree-2"}}
        if url.endswith("/git/blobs"):
            return {"sha": f"blob-{ref_reads}"}
        if url.endswith("/git/trees"):
            return {"sha": f"tree-{ref_reads}"}
        if url.endswith("/git/commits"):
            return {"sha": f"commit-{ref_reads}"}
        if url.endswith("/git/refs/heads/command-data"):
            patch_attempts += 1
            if patch_attempts == 1:
                raise HTTPError(url, 409, "Conflict", {}, io.BytesIO(b"branch advanced"))
            return {"ref": "refs/heads/command-data"}
        raise AssertionError(url)

    monkeypatch.setattr(publisher, "_github_json", fake_github_json)
    publisher.publish("public-data/daily_predictions.json", target, "owner/repo", "token")
    assert ref_reads == 2
    assert patch_attempts == 2
    second_tree = next(body for url, method, body in calls
                       if url.endswith("/git/trees") and body["base_tree"] == "base-tree-2")
    assert second_tree["tree"][0]["sha"] == "blob-2"
