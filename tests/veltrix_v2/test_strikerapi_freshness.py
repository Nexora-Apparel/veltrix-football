from datetime import datetime, timezone
from hashlib import sha256

import pytest

from veltrix_v2.data.strikerapi_freshness import parse_striker_dataset_freshness


UTC = timezone.utc
HTML = b"""<!doctype html><html><body><table>
<tr><th>Dataset</th><th>Through</th><th>Written</th><th>Endpoints</th></tr>
<tr><td>Fixtures, results and box scores Fixtures, scores and lineups</td>
<td>2026-11-08</td><td>2026-11-13 10:01 UTC</td><td>list_games</td></tr>
<tr><td>Match events</td><td>2026-11-08</td><td>2026-11-13 10:01 UTC</td><td>get_events</td></tr>
</table></body></html>"""


def test_parses_exact_dataset_written_time_and_archives_raw_hash():
    retrieved = datetime(2026, 11, 14, 5, 0, tzinfo=UTC)
    evidence = parse_striker_dataset_freshness(HTML, retrieved_at=retrieved)
    assert evidence.dataset_name == "Fixtures, results and box scores"
    assert evidence.through_date == "2026-11-08"
    assert evidence.written_at == datetime(2026, 11, 13, 10, 1, tzinfo=UTC)
    assert evidence.retrieved_at == retrieved
    assert evidence.changelog_sha256 == sha256(HTML).hexdigest()
    assert evidence.timestamp_basis == "provider_dataset_refresh"


def test_missing_dataset_row_fails_closed():
    with pytest.raises(ValueError, match="STRIKER_DATASET_FRESHNESS_ROW_MISSING"):
        parse_striker_dataset_freshness(
            b"<table><tr><td>Odds</td><td>-</td><td>2026-11-13 10:01 UTC</td></tr></table>",
            retrieved_at=datetime(2026, 11, 14, 5, 0, tzinfo=UTC),
        )


def test_future_written_time_fails_closed():
    with pytest.raises(ValueError, match="STRIKER_DATASET_WRITTEN_AFTER_RETRIEVAL"):
        parse_striker_dataset_freshness(
            HTML, retrieved_at=datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
        )


def test_naive_retrieval_time_fails_closed():
    with pytest.raises(ValueError, match="STRIKER_CHANGELOG_RETRIEVAL_TIME_UNTRUSTED"):
        parse_striker_dataset_freshness(
            HTML, retrieved_at=datetime(2026, 11, 14, 5, 0)
        )
