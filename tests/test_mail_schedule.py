import unittest
from datetime import datetime, timedelta, timezone

import mail.schedule as ms


TOKYO = timezone(timedelta(hours=9))


class PacedIntervalTests(unittest.TestCase):
    def test_spreads_cap_across_remaining_day(self):
        # 48 left, 24h → 30 min each
        self.assertEqual(ms.paced_interval_sec(48, 24 * 3600, min_sec=30), 1800.0)

    def test_speeds_up_when_day_is_almost_over(self):
        # 60 left, 1h → 60s (below a 30s*60 floor would miss midnight)
        self.assertEqual(ms.paced_interval_sec(60, 3600, min_sec=30), 60.0)

    def test_floor_when_there_is_room(self):
        # 2 left, 24h → floor 30s would be tiny; use 12h
        self.assertEqual(ms.paced_interval_sec(2, 24 * 3600, min_sec=30), 12 * 3600)

    def test_zero_cap_waits_until_midnight(self):
        self.assertEqual(ms.paced_interval_sec(0, 3600, min_sec=30), 3600.0)

    def test_delay_never_exceeds_remaining_day(self):
        delay = ms.paced_delay_sec(1, 90, min_sec=30, jitter=False)
        self.assertLessEqual(delay, 90.0)
        self.assertGreaterEqual(delay, 1.0)


class RemainingDayTests(unittest.TestCase):
    def test_counts_down_to_tokyo_midnight(self):
        when = datetime(2026, 8, 15, 18, 0, tzinfo=TOKYO)
        self.assertEqual(ms.remaining_tokyo_day_sec(when), 6 * 3600)


if __name__ == "__main__":
    unittest.main()
