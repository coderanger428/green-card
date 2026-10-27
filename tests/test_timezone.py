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

    def test_count_sent_today_uses_tokyo_day_for_old_utc_timestamps(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            conn.execute(
                """
                INSERT INTO users (id, email, name, link, location, country, created_at, updated_at)
                VALUES (?, ?, '', '', '', 'us', ?, ?)
                """,
                (1, "user@example.com", "2026-08-10T00:00:00+00:00", "2026-08-10T00:00:00+00:00"),
            )
            conn.execute(
                """
                INSERT INTO queue_items (user_id, status, queued_at, sent_at, sender_email)
                VALUES (?, 'sent', ?, ?, ?)
                """,
                (1, "2026-08-10T18:01:43.404593+00:00", "2026-08-10T18:01:43.404593+00:00", "sender@example.com"),
            )
            conn.commit()

            self.assertEqual(db.count_sent_today(conn, "2026-08-11"), 1)
            self.assertEqual(
                db.count_sent_by_sender_today(conn, "2026-08-11").get("sender@example.com", 0),
                1,
            )
        finally:
            conn.close()

    def test_next_active_account_respects_tokyo_day_cap(self):
        """UTC sent_at on previous calendar day still counts toward Tokyo daily cap."""
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
            # Cap is 10 for age < 1 day. Insert 10 Tokyo-day sends via UTC timestamps
            # that do NOT start with 2026-08-11 (would fool a LIKE prefix check).
            for i in range(10):
                uid = i + 1
                conn.execute(
                    """
                    INSERT INTO users (id, email, name, link, location, country, created_at, updated_at)
                    VALUES (?, ?, '', '', '', 'us', ?, ?)
                    """,
                    (uid, f"user{i}@example.com", created, created),
                )
                # 2026-08-10 15:00 UTC == 2026-08-11 00:00 JST
                sent_at = f"2026-08-10T15:{i:02d}:00+00:00"
                conn.execute(
                    """
                    INSERT INTO queue_items (user_id, status, queued_at, sent_at, sender_email)
                    VALUES (?, 'sent', ?, ?, ?)
                    """,
                    (uid, sent_at, sent_at, "sender@example.com"),
                )
            conn.commit()

            self.assertEqual(
                db.count_sent_by_sender_today(conn, "2026-08-11").get("sender@example.com", 0),
                10,
            )
            self.assertIsNone(db.get_next_active_mail_account(conn, "2026-08-11"))
        finally:
            conn.close()

    def test_next_active_account_prefers_least_filled(self):
        """Do not let an older account with headroom starve a less-filled one."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            older = "2026-08-09T00:00:00+09:00"  # calendar age >= 2 on Aug 11 → cap 20
            newer = "2026-08-11T12:00:00+09:00"  # calendar age 0 → cap 10
            conn.execute(
                """
                INSERT INTO mail_accounts (email, app_password, active, daily_cap, created_at, updated_at)
                VALUES ('old@example.com', 'pw', 1, 20, ?, ?),
                       ('new@example.com', 'pw', 1, 10, ?, ?)
                """,
                (older, older, newer, newer),
            )
            # old: 13/20 filled; new: 7/10 filled → prefer new (lower ratio)
            for i, (email, n) in enumerate(
                [("old@example.com", 13), ("new@example.com", 7)], start=1
            ):
                for j in range(n):
                    uid = i * 100 + j
                    conn.execute(
                        """
                        INSERT INTO users (id, email, name, link, location, country, created_at, updated_at)
                        VALUES (?, ?, '', '', '', 'usa', ?, ?)
                        """,
                        (uid, f"u{uid}@example.com", newer, newer),
                    )
                    conn.execute(
                        """
                        INSERT INTO queue_items (user_id, status, queued_at, sent_at, sender_email)
                        VALUES (?, 'sent', ?, ?, ?)
                        """,
                        (uid, newer, newer, email),
                    )
            conn.commit()

            self.assertEqual(db.computed_mail_cap(older), 20)
            self.assertEqual(db.computed_mail_cap(newer), 10)
            nxt = db.get_next_active_mail_account(conn, "2026-08-11")
            self.assertIsNotNone(nxt)
            self.assertEqual(nxt["email"], "new@example.com")
        finally:
            conn.close()


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

    def test_scrape_daily_save_limit_uses_mail_cap_ratio(self):
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
            # Age < 1 day → cap 10; 1.5× → 15
            self.assertEqual(db.computed_mail_cap(created, now=now), 10)
            self.assertEqual(db.scrape_daily_save_limit(conn, ratio=1.5, now=now), 15)
            self.assertEqual(
                db.scrape_daily_save_limit(
                    conn, ratio=1.5, fallback_mail_cap=20, now=now
                ),
                15,
            )
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
