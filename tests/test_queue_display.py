import unittest
from datetime import datetime, timedelta, timezone

from server.dashboard import estimate_queue_send_times, sort_queue_by_send_time
from mail.schedule import paced_interval_sec

TOKYO = timezone(timedelta(hours=9))


class SortQueueBySendTimeTests(unittest.TestCase):
    def test_sending_then_soonest_then_paused(self):
        items = [
            {
                "queue_id": 1,
                "status": "queued",
                "estimated_send_at": "2026-08-14T15:00:00+00:00",
                "queued_at": "2026-08-14T10:00:00+00:00",
            },
            {
                "queue_id": 2,
                "status": "sending",
                "estimated_send_at": "2026-08-14T12:00:00+00:00",
                "queued_at": "2026-08-14T09:00:00+00:00",
            },
            {
                "queue_id": 3,
                "status": "queued",
                "estimated_send_at": "2026-08-14T13:00:00+00:00",
                "queued_at": "2026-08-14T11:00:00+00:00",
            },
            {
                "queue_id": 4,
                "status": "queued",
                "estimated_send_at": None,
                "estimated_send_label": "Paused",
                "queued_at": "2026-08-14T08:00:00+00:00",
            },
        ]
        ordered = sort_queue_by_send_time(items)
        self.assertEqual([row["queue_id"] for row in ordered], [2, 3, 1, 4])


class PaceEstimateTests(unittest.TestCase):
    def test_fifo_first_send_is_now(self):
        when = datetime(2026, 8, 15, 10, 0, tzinfo=TOKYO)
        items = [
            {
                "queue_id": 1,
                "status": "queued",
                "country": "usa",
                "queued_at": "2026-08-15T09:00:00+09:00",
            },
            {
                "queue_id": 2,
                "status": "queued",
                "country": "germany",
                "queued_at": "2026-08-15T09:01:00+09:00",
            },
        ]
        rows = estimate_queue_send_times(
            items,
            sent_today=0,
            daily_limit=20,
            drip_paused=False,
            now=when,
        )
        self.assertEqual(
            rows[0]["estimated_send_at"],
            when.astimezone(timezone.utc).isoformat(),
        )
        self.assertIsNone(rows[0]["estimated_send_label"])
        gap = paced_interval_sec(19, 14 * 3600, min_sec=30)
        second = datetime.fromisoformat(rows[1]["estimated_send_at"])
        first = datetime.fromisoformat(rows[0]["estimated_send_at"])
        self.assertAlmostEqual((second - first).total_seconds(), gap, places=3)

    def test_overflow_waits_for_next_tokyo_day(self):
        when = datetime(2026, 8, 15, 23, 0, tzinfo=TOKYO)
        items = [
            {
                "queue_id": i,
                "status": "queued",
                "country": "india",
                "queued_at": f"2026-08-15T22:0{i}:00+09:00",
            }
            for i in range(1, 4)
        ]
        rows = estimate_queue_send_times(
            items,
            sent_today=1,
            daily_limit=2,
            drip_paused=False,
            now=when,
        )
        midnight = datetime(2026, 8, 16, 0, 0, tzinfo=TOKYO).astimezone(timezone.utc)
        self.assertEqual(
            rows[0]["estimated_send_at"],
            when.astimezone(timezone.utc).isoformat(),
        )
        self.assertEqual(rows[1]["estimated_send_at"], midnight.isoformat())

    def test_paused_has_no_send_time(self):
        when = datetime(2026, 8, 15, 10, 0, tzinfo=TOKYO)
        items = [
            {
                "queue_id": 1,
                "status": "queued",
                "country": "usa",
                "queued_at": "2026-08-15T09:00:00+09:00",
            }
        ]
        rows = estimate_queue_send_times(
            items,
            sent_today=0,
            daily_limit=20,
            drip_paused=True,
            now=when,
        )
        self.assertIsNone(rows[0]["estimated_send_at"])
        self.assertEqual(rows[0]["estimated_send_label"], "Paused")


if __name__ == "__main__":
    unittest.main()
