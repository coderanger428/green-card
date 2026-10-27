import sqlite3
import unittest

import core.db as db


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_SQL)
    return conn


class UpdateOutcomeTests(unittest.TestCase):
    def test_update_keeps_allowed_values(self):
        conn = _conn()
        try:
            _, user_id = db.insert_user(
                conn,
                email="a@gmail.com",
                name="ada",
                link="",
                location="",
                country="usa",
            )
            row = conn.execute(
                "SELECT outcome FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            self.assertEqual(row["outcome"], "Waiting")

            updated = db.update_user_outcome(conn, user_id, "Replied")
            self.assertEqual(updated["outcome"], "Replied")
            updated = db.update_user_outcome(conn, user_id, "Rejected")
            self.assertEqual(updated["outcome"], "Rejected")

            self.assertIsNone(db.update_user_outcome(conn, 999, "Waiting"))
            with self.assertRaises(ValueError):
                db.update_user_outcome(conn, user_id, "Interested")
        finally:
            conn.close()


class GreetingNameTests(unittest.TestCase):
    def test_prefers_display_name(self):
        self.assertEqual(db.greeting_name("Alex", "coolcoder99"), "Alex")

    def test_falls_back_to_original(self):
        self.assertEqual(db.greeting_name("  ", "coolcoder99"), "coolcoder99")
        self.assertEqual(db.greeting_name(None, "Jane"), "Jane")


class InsertDisplayNameTests(unittest.TestCase):
    def test_insert_copies_scraped_name(self):
        conn = _conn()
        try:
            inserted, user_id = db.insert_user(
                conn,
                email="a@gmail.com",
                name="coolcoder99",
                link="https://dev.to/coolcoder99",
                location="Tokyo",
                country="japan",
                platform_user_id=12,
            )
            self.assertTrue(inserted)
            row = conn.execute(
                "SELECT name, display_name FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            self.assertEqual(row["name"], "coolcoder99")
            self.assertEqual(row["display_name"], "coolcoder99")
        finally:
            conn.close()


class UpdateDisplayNameTests(unittest.TestCase):
    def test_update_and_empty_resets_to_original(self):
        conn = _conn()
        try:
            _, user_id = db.insert_user(
                conn,
                email="a@gmail.com",
                name="xXkiller99",
                link="",
                location="",
                country="usa",
            )
            updated = db.update_user_display_name(conn, user_id, "  Alex  ")
            self.assertEqual(updated["display_name"], "Alex")
            self.assertEqual(updated["name"], "xXkiller99")

            reset = db.update_user_display_name(conn, user_id, "   ")
            self.assertEqual(reset["display_name"], "xXkiller99")

            missing = db.update_user_display_name(conn, 999, "Alex")
            self.assertIsNone(missing)

            conn.execute(
                "UPDATE users SET mail_status = 'sent' WHERE id = ?",
                (user_id,),
            )
            with self.assertRaises(ValueError):
                db.update_user_display_name(conn, user_id, "Changed")
        finally:
            conn.close()

    def test_upsert_does_not_overwrite_edited_display_name(self):
        conn = _conn()
        try:
            _, user_id = db.insert_user(
                conn,
                email="a@gmail.com",
                name="nick123",
                link="",
                location="NY",
                country="usa",
            )
            db.update_user_display_name(conn, user_id, "Nick")
            db.upsert_user_last_wins(
                conn,
                email="a@gmail.com",
                name="nick123",
                link="https://dev.to/nick123",
                location="NY",
                country="usa",
            )
            row = conn.execute(
                "SELECT name, display_name, link FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            self.assertEqual(row["display_name"], "Nick")
            self.assertEqual(row["link"], "https://dev.to/nick123")
        finally:
            conn.close()


class InitDbBackfillTests(unittest.TestCase):
    def test_legacy_users_table_backfills_display_name(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL COLLATE NOCASE,
                    name TEXT NOT NULL DEFAULT '',
                    link TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    country TEXT NOT NULL,
                    mail_status TEXT NOT NULL DEFAULT 'not_sent',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(email)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO users (email, name, link, location, country, created_at, updated_at)
                VALUES ('a@gmail.com', 'dev_ninja', '', '', 'usa',
                        '2026-01-01T00:00:00+09:00', '2026-01-01T00:00:00+09:00')
                """
            )
            user_columns = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
            self.assertNotIn("display_name", user_columns)
            db.ensure_display_name_column(conn)
            row = conn.execute(
                "SELECT name, display_name FROM users WHERE email = ?",
                ("a@gmail.com",),
            ).fetchone()
            self.assertEqual(row["name"], "dev_ninja")
            self.assertEqual(row["display_name"], "dev_ninja")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
