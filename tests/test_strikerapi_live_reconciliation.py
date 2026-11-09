import unittest
from urllib.parse import urlparse, parse_qs

from scripts.run_readonly_epl_reconciliation import (
    FIVEDOLLAR_EPL_ID,
    ExportError,
    collect_fivedollar_pages,
    validate_fivedollar_row,
)


def fixture(fixture_id=1):
    return {
        "id": fixture_id,
        "league": {"id": FIVEDOLLAR_EPL_ID, "name": "Premier League"},
        "teams": {
            "home": {"id": 10, "name": "Arsenal"},
            "away": {"id": 20, "name": "Chelsea"},
        },
        "kickoff_utc": "2026-08-15T16:30:00+00:00",
        "status": "finished",
        "goals": {"home": 2, "away": 0},
    }


class LiveEplReconciliationExportTests(unittest.TestCase):
    def test_validates_finished_epl_fixture(self):
        self.assertTrue(validate_fivedollar_row(fixture()))

    def test_rejects_wrong_competition_and_unsettled_scores(self):
        wrong_league = fixture()
        wrong_league["league"]["id"] = 999
        self.assertFalse(validate_fivedollar_row(wrong_league))
        unsettled = fixture()
        unsettled["goals"]["home"] = None
        self.assertFalse(validate_fivedollar_row(unsettled))

    def test_collects_all_pages_with_fixed_window(self):
        seen = []

        def fake_request(url, _key):
            query = parse_qs(urlparse(url).query)
            seen.append(query)
            page = int(query["page"][0])
            rows = [fixture(page)]
            return 200, {}, {
                "success": 1,
                "data": rows,
                "pagination": {"page": page, "has_more": page == 1},
            }

        rows, pages, _headers = collect_fivedollar_pages(
            "test-key", 1784131200, 1792000000, fake_request
        )
        self.assertEqual([row["id"] for row in rows], [1, 2])
        self.assertEqual(pages, 2)
        self.assertEqual([x["page"][0] for x in seen], ["1", "2"])
        self.assertTrue(all(x["start_time"][0] == "1784131200" for x in seen))
        self.assertTrue(all(x["end_time"][0] == "1792000000" for x in seen))

    def test_stops_if_page_cap_is_exceeded(self):
        def fake_request(_url, _key):
            return 200, {}, {
                "success": 1,
                "data": [fixture()],
                "pagination": {"has_more": True},
            }

        with self.assertRaisesRegex(ExportError, "page cap"):
            collect_fivedollar_pages("test-key", 1, 2, fake_request)


if __name__ == "__main__":
    unittest.main()
