import os
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("STABLE_TOKYO_NOW", "2026-08-11T12:00:00+09:00")

import core.db as db


class TimezoneTests(unittest.TestCase):
    def test_tokyo_now_uses_asia_tokyo_timezone(self):
        value = db.tokyo_now()
        parsed = datetime.fromisoformat(value)

        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset(), timedelta(hours=9))

    def test_local_day_prefix_uses_tokyo_date(self):
        now = datetime(2026, 8, 10, 23, 30, tzinfo=timezone(timedelta(hours=9)))

        self.assertEqual(db.local_day_prefix(now), "2026-08-10")

    def test_mail_cap_uses_tokyo_calendar_days_not_rolling_24h(self):
        created = "2026-08-10T20:00:00+09:00"  # evening of Aug 10 Tokyo
        # Create day → cap 10
        same_day_late = datetime(2026, 8, 10, 23, 59, tzinfo=timezone(timedelta(hours=9)))
        self.assertEqual(db.computed_mail_cap(created, now=same_day_late), 10)
        # Entire next Tokyo day still cap 10 (until midnight Aug 11→12)
        next_day_evening = datetime(2026, 8, 11, 21, 0, tzinfo=timezone(timedelta(hours=9)))
        self.assertEqual(db.computed_mail_cap(created, now=next_day_evening), 10)
        # Midnight into the day after → cap 20
        day_after = datetime(2026, 8, 12, 0, 1, tzinfo=timezone(timedelta(hours=9)))
        self.assertEqual(db.computed_mail_cap(created, now=day_after), 20)

    def test_scrape_daily_save_limit_is_a_static_number(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            created = "2026-08-11T00:00:00+09:00"
            conn.execute(
                """
                INSERT INTO mail_accounts (email, app_password, active, daily_cap, created_at, updated_at)
                VALUES (?, 'pw', 1, 10, ?, ?)
                """,
                ("sender@example.com", created, created),
            )
            conn.commit()
            now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone(timedelta(hours=9)))
            self.assertEqual(db.computed_mail_cap(created, now=now), 10)
            self.assertEqual(db.scrape_daily_save_limit(conn), db.DEFAULT_SCRAPE_DAILY_CAP)
            db.set_scrape_cap(conn, enabled=False, cap=12)
            self.assertIsNone(db.scrape_daily_save_limit(conn))
        finally:
            conn.close()

    def test_count_users_saved_today_uses_tokyo_day(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            # UTC evening 8/10 == Tokyo morning 8/11
            conn.execute(
                """
                INSERT INTO users (id, email, name, link, location, country, created_at, updated_at)
                VALUES (1, 'a@example.com', '', '', '', 'usa', ?, ?)
                """,
                ("2026-08-10T18:00:00+00:00", "2026-08-10T18:00:00+00:00"),
            )
            conn.execute(
                """
                INSERT INTO users (id, email, name, link, location, country, created_at, updated_at)
                VALUES (2, 'b@example.com', '', '', '', 'noloc', ?, ?)
                """,
                ("2026-08-10T18:05:00+00:00", "2026-08-10T18:05:00+00:00"),
            )
            conn.commit()
            # noloc excluded from daily located-save budget
            self.assertEqual(db.count_users_saved_today(conn, "2026-08-11"), 1)
            self.assertEqual(db.count_users_saved_today(conn, "2026-08-10"), 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
