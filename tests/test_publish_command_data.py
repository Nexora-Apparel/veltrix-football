from datetime import datetime, timezone

from scripts.publish_command_data import _archive_report_path, _valid_recent_cache


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
    report.write_text(json.dumps({
        "as_of_date": "2026-11-02",
        "predictions": [],
    }), encoding="utf-8")
    ledger.write_text(json.dumps({
        "model_status": "PAPER_TRACKING_ONLY",
        "cumulative_metrics_by_model": {},
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
