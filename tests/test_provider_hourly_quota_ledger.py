import json
import tempfile
import unittest
from pathlib import Path

from app.provider_hourly_quota_ledger import (
    HourlyQuotaError,
    reserve_hourly_quota,
    settle_hourly_quota,
)


def ledger_file(path):
    path.write_text(json.dumps({
        "schema_version": 1,
        "provider": "fivedollar",
        "window_seconds": 3600,
        "maximum_requests": 60,
        "reservations": [],
    }), encoding="utf-8")


class HourlyQuotaLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ledger.json"
        ledger_file(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_reservations_enforce_rolling_hour_limit(self):
        reserve_hourly_quota(
            ledger_path=self.path, run_id="run-1", reserved_requests=20,
            now="2026-11-10T05:00:00Z",
        )
        reserve_hourly_quota(
            ledger_path=self.path, run_id="run-2", reserved_requests=20,
            now="2026-11-10T05:10:00Z",
        )
        reserve_hourly_quota(
            ledger_path=self.path, run_id="run-3", reserved_requests=20,
            now="2026-11-10T05:20:00Z",
        )
        with self.assertRaisesRegex(HourlyQuotaError, "hourly_quota_exceeded"):
            reserve_hourly_quota(
                ledger_path=self.path, run_id="run-4", reserved_requests=5,
                now="2026-11-10T05:30:00Z",
            )

    def test_settlement_releases_unused_reserved_capacity(self):
        reserve_hourly_quota(
            ledger_path=self.path, run_id="run-1", reserved_requests=20,
            now="2026-11-10T05:00:00Z",
        )
        result = settle_hourly_quota(
            ledger_path=self.path, run_id="run-1", actual_requests=5,
            settled_at="2026-11-10T05:05:00Z",
        )
        self.assertEqual(result["unused_reservation_released"], 15)
        reserve_hourly_quota(
            ledger_path=self.path, run_id="run-2", reserved_requests=20,
            now="2026-11-10T05:06:00Z",
        )

    def test_pending_reservation_is_conservatively_charged_at_full_ceiling(self):
        reserve_hourly_quota(
            ledger_path=self.path, run_id="run-1", reserved_requests=20,
            now="2026-11-10T05:00:00Z",
        )
        with self.assertRaisesRegex(HourlyQuotaError, "hourly_quota_exceeded"):
            reserve_hourly_quota(
                ledger_path=self.path, run_id="run-2", reserved_requests=20,
                now="2026-11-10T05:01:00Z",
            )

    def test_reservation_expires_after_rolling_hour(self):
        reserve_hourly_quota(
            ledger_path=self.path, run_id="run-1", reserved_requests=60,
            now="2026-11-10T05:00:00Z",
        )
        result = reserve_hourly_quota(
            ledger_path=self.path, run_id="run-2", reserved_requests=5,
            now="2026-11-10T06:00:01Z",
        )
        self.assertTrue(result["reserved"])

    def test_duplicate_run_ids_and_over_reservation_settlement_rejected(self):
        reserve_hourly_quota(
            ledger_path=self.path, run_id="run-1", reserved_requests=10,
            now="2026-11-10T05:00:00Z",
        )
        with self.assertRaisesRegex(HourlyQuotaError, "already_reserved"):
            reserve_hourly_quota(
                ledger_path=self.path, run_id="run-1", reserved_requests=5,
                now="2026-11-10T05:01:00Z",
            )
        with self.assertRaisesRegex(HourlyQuotaError, "exceed_reserved"):
            settle_hourly_quota(
                ledger_path=self.path, run_id="run-1", actual_requests=15,
                settled_at="2026-11-10T05:02:00Z",
            )

    def test_corrupt_ledger_fails_closed(self):
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(HourlyQuotaError, "unreadable"):
            reserve_hourly_quota(
                ledger_path=self.path, run_id="run-1", reserved_requests=5,
                now="2026-11-10T05:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
