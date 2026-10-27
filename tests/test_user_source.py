import sqlite3
import tempfile
import unittest
from pathlib import Path

import core.db as db


class PlatformUserIdTests(unittest.TestCase):
    def test_blank_platform_id_is_stored_as_null(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            inserted, user_id = db.insert_user(
                conn,
                email="a@gmail.com",
                name="ada",
                link="",
                location="",
                country="usa",
                platform_user_id="  ",
            )
            self.assertTrue(inserted)
            row = conn.execute(
                "SELECT source, platform_user_id FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            self.assertEqual(row["source"], "devto")
            self.assertIsNone(row["platform_user_id"])
        finally:
            conn.close()

    def test_platform_id_keeps_non_numeric_values(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            _, user_id = db.insert_user(
                conn,
                email="b@gmail.com",
                name="bea",
                link="",
                location="",
                country="usa",
                source="abc",
                platform_user_id="user-99",
            )
            row = conn.execute(
                "SELECT source, platform_user_id FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            self.assertEqual(row["source"], "abc")
            self.assertEqual(row["platform_user_id"], "user-99")
        finally:
            conn.close()

    def test_insert_stores_github_account(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            inserted, user_id = db.insert_user(
                conn,
                email="c@gmail.com",
                name="cy",
                link="https://dev.to/cy",
                location="",
                country="usa",
                github="  cy-dev  ",
            )
            self.assertTrue(inserted)
            row = conn.execute(
                "SELECT github, source FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            self.assertEqual(row["github"], "cy-dev")
            self.assertEqual(row["source"], "devto,github")
        finally:
            conn.close()

    def test_existing_github_account_is_recorded_as_a_source_once(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            conn.execute(
                """
                INSERT INTO users (
                    email, name, link, github, location, country, source,
                    mail_status, created_at, updated_at
                ) VALUES (
                    'd@gmail.com', 'dee', 'https://dev.to/dee', 'dee', '', 'usa',
                    'devto', 'not_sent', '2026-10-27T00:00:00+09:00', '2026-10-27T00:00:00+09:00'
                )
                """
            )
            db.ensure_github_as_source(conn)
            db.ensure_github_as_source(conn)
            source = conn.execute(
                "SELECT source FROM users WHERE email = 'd@gmail.com'"
            ).fetchone()["source"]
            self.assertEqual(source, "devto,github")
        finally:
            conn.close()


class LegacyDevtoColumnTests(unittest.TestCase):
    def test_init_db_renames_id_resets_mail_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp)
            legacy_path = db.db_path(result_dir)
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy = sqlite3.connect(legacy_path)
            legacy.row_factory = sqlite3.Row
            legacy.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL COLLATE NOCASE,
                    name TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    link TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    country TEXT NOT NULL,
                    devto_user_id INTEGER,
                    mail_status TEXT NOT NULL DEFAULT 'not_sent',
                    opened INTEGER,
                    replied INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(email)
                );
                CREATE TABLE queue_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    status TEXT NOT NULL DEFAULT 'queued',
                    queued_at TEXT NOT NULL,
                    sent_at TEXT,
                    sender_email TEXT NOT NULL DEFAULT '',
                    template TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    UNIQUE(user_id)
                );
                """
            )
            legacy.execute(
                """
                INSERT INTO users (
                    email, name, display_name, link, location, country,
                    devto_user_id, mail_status, created_at, updated_at
                ) VALUES (
                    'a@gmail.com', 'ada', 'ada', '', '', 'usa',
                    42, 'sent', '2026-01-01T00:00:00+09:00', '2026-01-01T00:00:00+09:00'
                )
                """
            )
            user_id = legacy.execute(
                "SELECT id FROM users WHERE email = 'a@gmail.com'"
            ).fetchone()["id"]
            legacy.execute(
                """
                INSERT INTO queue_items (user_id, status, queued_at, sent_at, template, subject)
                VALUES (?, 'sent', '2026-01-01T00:00:00+09:00', '2026-01-02T00:00:00+09:00', 'usa (1).txt', 'Hi')
                """,
                (user_id,),
            )
            legacy.commit()
            legacy.close()

            db.init_db(result_dir)

            conn = sqlite3.connect(db.db_path(result_dir))
            conn.row_factory = sqlite3.Row
            try:
                columns = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
                self.assertNotIn("devto_user_id", columns)
                self.assertNotIn("opened", columns)
                self.assertNotIn("replied", columns)
                self.assertIn("platform_user_id", columns)
                self.assertIn("github", columns)
                row = conn.execute(
                    "SELECT source, platform_user_id, github, mail_status FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                self.assertEqual(row["source"], "devto")
                self.assertEqual(row["platform_user_id"], "42")
                self.assertEqual(row["github"], "")
                self.assertEqual(row["mail_status"], "not_sent")
                self.assertIn("outcome", columns)
                outcome = conn.execute(
                    "SELECT outcome FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                self.assertEqual(outcome["outcome"], "Waiting")
                queued = conn.execute("SELECT COUNT(*) AS n FROM queue_items").fetchone()
                self.assertEqual(queued["n"], 0)

                conn.execute(
                    """
                    INSERT INTO queue_items (user_id, status, queued_at)
                    VALUES (?, 'queued', '2026-02-01T00:00:00+09:00')
                    """,
                    (user_id,),
                )
                conn.execute(
                    "UPDATE users SET mail_status = 'queued' WHERE id = ?",
                    (user_id,),
                )
                conn.commit()
            finally:
                conn.close()

            db.init_db(result_dir)

            conn = sqlite3.connect(db.db_path(result_dir))
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT mail_status FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                queued = conn.execute("SELECT COUNT(*) AS n FROM queue_items").fetchone()
                self.assertEqual(row["mail_status"], "not_sent")
                self.assertEqual(queued["n"], 1)
            finally:
                conn.close()


class LegacyDbPathTests(unittest.TestCase):
    def test_platform_nested_db_moves_up_to_the_shared_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp)
            nested = result_dir / "devto" / "devto.db"
            nested.parent.mkdir()
            legacy = sqlite3.connect(nested)
            legacy.execute("CREATE TABLE marker (id INTEGER)")
            legacy.commit()
            legacy.close()

            opened = db.connect(result_dir)
            try:
                row = opened.execute(
                    "SELECT name FROM sqlite_master WHERE name = 'marker'"
                ).fetchone()
                self.assertIsNotNone(row)
            finally:
                opened.close()

            self.assertTrue(db.db_path(result_dir).is_file())
            self.assertFalse(nested.exists())


if __name__ == "__main__":
    unittest.main()
