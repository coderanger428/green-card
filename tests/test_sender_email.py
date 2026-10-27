import sqlite3
import unittest

import core.db as db


class SenderEmailColumnTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA_SQL)
        self.conn.execute("ALTER TABLE users DROP COLUMN sender_email")

    def tearDown(self):
        self.conn.close()

    def _user(self, uid: int, email: str) -> None:
        now = "2026-10-27T00:00:00+09:00"
        self.conn.execute(
            """
            INSERT INTO users (
                id, email, name, link, location, country, mail_status,
                created_at, updated_at
            ) VALUES (?, ?, '', '', '', 'usa', 'sent', ?, ?)
            """,
            (uid, email, now, now),
        )

    def test_migration_copies_sender_from_sent_queue(self):
        self._user(1, "a@gmail.com")
        self._user(2, "b@gmail.com")
        self.conn.execute(
            """
            INSERT INTO queue_items (
                user_id, status, queued_at, sent_at, sender_email
            ) VALUES (1, 'sent', '2026-10-26T00:00:00+09:00',
                      '2026-10-26T01:00:00+09:00', 'old@gmail.com')
            """
        )
        self.conn.execute(
            """
            INSERT INTO queue_items (
                user_id, status, queued_at, sent_at, sender_email
            ) VALUES (2, 'sent', '2026-10-26T00:00:00+09:00',
                      '2026-10-26T01:00:00+09:00', '')
            """
        )
        db.ensure_sender_email_column(self.conn)
        rows = {
            row["id"]: row["sender_email"]
            for row in self.conn.execute("SELECT id, sender_email FROM users")
        }
        self.assertEqual(rows[1], "old@gmail.com")
        self.assertEqual(rows[2], "")

    def test_mark_sent_stores_sender_on_the_user(self):
        now = "2026-10-27T00:00:00+09:00"
        self.conn.execute(
            """
            INSERT INTO users (
                id, email, name, link, location, country, mail_status,
                created_at, updated_at
            ) VALUES (3, 'c@gmail.com', '', '', '', 'usa', 'queued', ?, ?)
            """,
            (now, now),
        )
        db.ensure_sender_email_column(self.conn)
        self.conn.execute(
            """
            INSERT INTO queue_items (user_id, status, queued_at, sender_email)
            VALUES (3, 'sending', ?, 'from@gmail.com')
            """,
            (now,),
        )
        queue_id = self.conn.execute(
            "SELECT id FROM queue_items WHERE user_id = 3"
        ).fetchone()["id"]
        db.mark_queue_sent(self.conn, queue_id, 3, "usa (1).txt", "Hello")
        row = self.conn.execute(
            "SELECT mail_status, sender_email FROM users WHERE id = 3"
        ).fetchone()
        self.assertEqual(row["mail_status"], "sent")
        self.assertEqual(row["sender_email"], "from@gmail.com")


if __name__ == "__main__":
    unittest.main()
