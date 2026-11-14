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


def test_legacy_main_refuses_all_non_archive_snapshots(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from scripts import publish_command_data as publisher

    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "as_of_date": "2026-11-14",
        "predictions": [],
    }), encoding="utf-8")
    calls = []
    monkeypatch.setattr(publisher, "publish", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(sys, "argv", ["publish_command_data.py", "--report", str(report)])
    assert publisher.main() == 2
    assert calls == []
    assert "LEGACY_COMMAND_DATA_PUBLISHER_DISABLED" in capsys.readouterr().err



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
    publisher.publish("public-data/archive/2026-11-14/daily_predictions_20261114T050000Z.json", target, "owner/repo", "token")
    assert ref_reads == 2
    assert patch_attempts == 2
    second_tree = next(body for url, method, body in calls
                       if url.endswith("/git/trees") and body["base_tree"] == "base-tree-2")
    assert second_tree["tree"][0]["sha"] == "blob-2"



def test_legacy_command_data_publisher_blocks_prediction_and_dashboard_paths(tmp_path, monkeypatch):
    import pytest
    from scripts.publish_command_data import publish

    local = tmp_path / "report.json"
    local.write_text('{"predictions":[]}', encoding="utf-8")
    monkeypatch.setattr(
        "scripts.publish_command_data.urlopen",
        lambda *args, **kwargs: pytest.fail("blocked legacy path must not contact GitHub"),
    )
    for path in (
        "public-data/daily_predictions.json",
        "public-data/dashboard_snapshot.json",
    ):
        with pytest.raises(PermissionError, match="LEGACY_PREDICTION_PUBLICATION_DISABLED"):
            publish(path, local, "Nexora-Apparel/veltrix-football", "not-a-real-token")


def test_legacy_command_data_publisher_rejects_path_traversal_before_network(tmp_path, monkeypatch):
    import pytest
    from scripts.publish_command_data import publish

    local = tmp_path / "report.json"
    local.write_text('{"predictions":[]}', encoding="utf-8")
    monkeypatch.setattr(
        "scripts.publish_command_data.urlopen",
        lambda *args, **kwargs: pytest.fail("invalid path must not contact GitHub"),
    )
    with pytest.raises(ValueError, match="COMMAND_DATA_PATH_INVALID"):
        publish("public-data/../public-data/daily_predictions.json", local,
                "Nexora-Apparel/veltrix-football", "not-a-real-token")



def test_archive_only_publication_preserves_historical_report_without_live_pointers(tmp_path, monkeypatch):
    import json
    from scripts import publish_command_data as publisher

    report_path = tmp_path / "daily_predictions.json"
    original = {
        "as_of_date": "2026-10-31",
        "same_day_only": True,
        "predictions": [{"fixture_id": "historical-1"}],
    }
    original_bytes = json.dumps(original).encode()
    report_path.write_bytes(original_bytes)
    calls = []
    monkeypatch.setattr(
        publisher,
        "publish",
        lambda path, local_file, repo, token: calls.append((path, local_file.read_bytes())),
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "Nexora-Apparel/veltrix-football")
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    monkeypatch.setattr(
        "sys.argv",
        ["publish_command_data.py", "--report", str(report_path), "--archive-only"],
    )

    assert publisher.main() == 0
    assert len(calls) == 1
    assert calls[0][0].startswith("public-data/archive/2026-10-31/")
    assert calls[0][1] == original_bytes
    assert report_path.read_bytes() == original_bytes


def test_legacy_main_refuses_live_report_and_dashboard_publication(tmp_path, monkeypatch, capsys):
    import json
    from scripts import publish_command_data as publisher

    report_path = tmp_path / "daily_predictions.json"
    report_path.write_text(json.dumps({
        "as_of_date": "2026-11-14",
        "predictions": [],
    }), encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        publisher,
        "publish",
        lambda *args, **kwargs: calls.append(args),
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "Nexora-Apparel/veltrix-football")
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    monkeypatch.setattr(
        "sys.argv",
        ["publish_command_data.py", "--report", str(report_path)],
    )
    assert publisher.main() == 2
    assert calls == []
    assert "LEGACY_COMMAND_DATA_PUBLISHER_DISABLED" in capsys.readouterr().err


def test_archive_path_remains_publishable_for_historical_preservation(tmp_path, monkeypatch):
    import json
    from scripts.publish_command_data import publish

    local = tmp_path / "historical.json"
    local.write_text('{"as_of_date":"2026-10-31","predictions":[]}', encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        "scripts.publish_command_data._github_json",
        lambda url, token, method="GET", body=None: calls.append((url, method, body)) or {},
    )
    publish(
        "public-data/archive/2026-10-31/daily_predictions_20261031T000000Z.json",
        local,
        "Nexora-Apparel/veltrix-football",
        "not-a-real-token",
    )
    assert len(calls) == 2



def test_archive_content_path_is_stable_and_content_addressed():
    from scripts.publish_command_data import _archive_content_path

    report = {"as_of_date": "2026-10-31"}
    first = _archive_content_path(report, b"immutable-report")
    same = _archive_content_path(report, b"immutable-report")
    changed = _archive_content_path(report, b"corrected-report")
    assert first == same
    assert first != changed
    assert first.startswith("public-data/archive/2026-10-31/daily_predictions_")


def test_command_data_publish_skips_existing_identical_bytes(tmp_path, monkeypatch, capsys):
    import base64
    import json
    from scripts.publish_command_data import publish

    local = tmp_path / "snapshot.json"
    raw = b'{"as_of_date":"2026-10-31","predictions":[]}'
    local.write_bytes(raw)
    calls = []

    def fake_github_json(url, token, method="GET", body=None):
        calls.append((url, method, body))
        return {
            "sha": "existing-blob-sha",
            "encoding": "base64",
            "content": base64.b64encode(raw).decode("ascii"),
        }

    monkeypatch.setattr("scripts.publish_command_data._github_json", fake_github_json)
    publish(
        "public-data/archive/2026-10-31/daily_predictions_abc.json",
        local,
        "Nexora-Apparel/veltrix-football",
        "not-a-real-token",
    )
    assert len(calls) == 1
    assert calls[0][1] == "GET"
    assert "exact bytes match" in capsys.readouterr().out
