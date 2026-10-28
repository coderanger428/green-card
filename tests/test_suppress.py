import sqlite3
import unittest

import core.db as db


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_SQL)
    return conn


class SuppressUserTests(unittest.TestCase):
    def test_suppress_keeps_row_and_drops_pool_counts(self):
        conn = _conn()
        try:
            _, pending_id = db.insert_user(
                conn,
                email="pending@gmail.com",
                name="Pending",
                link="",
                location="",
                country="japan",
            )
            _, sent_id = db.insert_user(
                conn,
                email="sent@gmail.com",
                name="Sent",
                link="",
                location="",
                country="japan",
            )
            conn.execute(
                "UPDATE users SET mail_status = 'sent' WHERE id = ?",
                (sent_id,),
            )
            hidden = db.suppress_user(conn, pending_id)
            self.assertEqual(hidden["suppressed"], 1)
            self.assertIsNone(db.suppress_user(conn, 999))

            inserted, same_id = db.insert_user(
                conn,
                email="pending@gmail.com",
                name="Pending Again",
                link="",
                location="",
                country="japan",
            )
            self.assertFalse(inserted)
            self.assertEqual(same_id, pending_id)
            still = conn.execute(
                "SELECT suppressed FROM users WHERE id = ?",
                (pending_id,),
            ).fetchone()
            self.assertEqual(still["suppressed"], 1)

            stats = {row["country"]: row for row in db.country_stats(conn)}
            self.assertEqual(stats["japan"]["count"], 1)
            self.assertEqual(stats["japan"]["sent"], 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
