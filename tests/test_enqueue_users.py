import sqlite3
import unittest

import core.db as db


class BlockedEmailTests(unittest.TestCase):
    def test_consumer_and_unknown_domains_are_allowed(self):
        self.assertTrue(db.can_enqueue_email("user@gmail.com"))
        self.assertTrue(db.can_enqueue_email("user@qq.com"))
        self.assertTrue(db.can_enqueue_email("user@company.com"))
        self.assertTrue(db.can_enqueue_email("user@pm.me"))

    def test_blocked_company_domains(self):
        self.assertTrue(db.is_blocked_email("staff@dev.to"))
        self.assertTrue(db.is_blocked_email("ops@linux.com"))
        self.assertTrue(db.is_blocked_email("a@microsoft.com"))
        self.assertTrue(db.is_blocked_email("a@ca.ibm.com"))
        self.assertFalse(db.is_blocked_email("a@notmicrosoft.com"))
        self.assertFalse(db.is_blocked_email("a@googlemail.com"))


class EnqueueUsersTests(unittest.TestCase):
    def test_enqueue_skips_blocked_company_domains_only(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            now = "2026-08-10T00:00:00+00:00"
            rows = [
                (1, "personal@gmail.com"),
                (2, "shop@company.com"),
                (3, "hire@dev.to"),
                (4, "kernel@linux.com"),
            ]
            for uid, email in rows:
                conn.execute(
                    """
                    INSERT INTO users (id, email, name, link, location, country, created_at, updated_at)
                    VALUES (?, ?, '', '', '', 'us', ?, ?)
                    """,
                    (uid, email, now, now),
                )
            conn.commit()

            counts = db.enqueue_users(conn, [1, 2, 3, 4])

            self.assertEqual(counts["queued"], 2)
            self.assertEqual(counts["skipped_blocked"], 2)
            queue_rows = conn.execute(
                "SELECT user_id FROM queue_items ORDER BY user_id"
            ).fetchall()
            self.assertEqual([row["user_id"] for row in queue_rows], [1, 2])
        finally:
            conn.close()


class RequeueStuckSendingTests(unittest.TestCase):
    def test_interrupted_sending_returns_to_queued(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            now = "2026-08-15T00:00:00+09:00"
            conn.execute(
                """
                INSERT INTO users (id, email, name, link, location, country,
                                   mail_status, created_at, updated_at)
                VALUES (1, 'a@gmail.com', '', '', '', 'usa', 'queued', ?, ?)
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO queue_items
                    (user_id, status, queued_at, sent_at, sender_email, template, subject, error)
                VALUES (1, 'sending', ?, NULL, 'sender@gmail.com', '', '', '')
                """,
                (now,),
            )
            conn.commit()
            recovered = db.requeue_stuck_sending(conn)
            self.assertEqual(recovered, 1)
            row = conn.execute("SELECT status, error FROM queue_items WHERE user_id = 1").fetchone()
            self.assertEqual(row["status"], "queued")
            self.assertIn("interrupted", row["error"])
            mail_status = conn.execute("SELECT mail_status FROM users WHERE id = 1").fetchone()
            self.assertEqual(mail_status["mail_status"], "queued")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
