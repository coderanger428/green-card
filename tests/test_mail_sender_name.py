import os
import sqlite3
import unittest

import core.db as db


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_SQL)
    return conn


class MailSenderNameTests(unittest.TestCase):
    def test_upsert_keeps_a_name_per_address(self):
        conn = _conn()
        try:
            first = db.upsert_mail_account(
                conn,
                email="From@gmail.com",
                app_password="",
                sender_name="James Mellyk",
            )
            self.assertEqual(first["email"], "from@gmail.com")
            self.assertEqual(first["sender_name"], "James Mellyk")
            updated = db.upsert_mail_account(
                conn,
                email="from@gmail.com",
                app_password="",
                sender_name="Ada Lovelace",
            )
            self.assertEqual(updated["sender_name"], "Ada Lovelace")
            self.assertEqual(db.mail_sender_name(conn, "from@gmail.com"), "Ada Lovelace")
            listed = db.get_mail_accounts(conn)
            self.assertEqual(listed[0]["sender_name"], "Ada Lovelace")
        finally:
            conn.close()

    def test_blank_name_is_rejected(self):
        conn = _conn()
        try:
            with self.assertRaises(ValueError):
                db.upsert_mail_account(
                    conn,
                    email="from@gmail.com",
                    app_password="",
                    sender_name="  ",
                )
        finally:
            conn.close()

    def test_legacy_env_name_fills_blank_rows_once(self):
        conn = _conn()
        previous = os.environ.get("SENDER_NAME")
        os.environ["SENDER_NAME"] = "James Mellyk"
        try:
            conn.execute(
                """
                CREATE TABLE mail_accounts_old AS SELECT id, email, app_password, active,
                    daily_cap, created_at, updated_at FROM mail_accounts
                """
            )
            now = "2026-10-27T00:00:00+09:00"
            conn.execute("DROP TABLE mail_accounts")
            conn.execute(
                """
                CREATE TABLE mail_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    app_password TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    daily_cap INTEGER NOT NULL DEFAULT 20,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO mail_accounts (
                    email, app_password, active, daily_cap, created_at, updated_at
                ) VALUES ('from@gmail.com', '', 1, 20, ?, ?)
                """,
                (now, now),
            )
            db.ensure_mail_sender_name(conn)
            name = conn.execute(
                "SELECT sender_name FROM mail_accounts WHERE email = 'from@gmail.com'"
            ).fetchone()["sender_name"]
            self.assertEqual(name, "James Mellyk")
            conn.execute(
                "UPDATE mail_accounts SET sender_name = 'Kept' WHERE email = 'from@gmail.com'"
            )
            os.environ["SENDER_NAME"] = "Someone Else"
            db.ensure_mail_sender_name(conn)
            name = conn.execute(
                "SELECT sender_name FROM mail_accounts WHERE email = 'from@gmail.com'"
            ).fetchone()["sender_name"]
            self.assertEqual(name, "Kept")
        finally:
            if previous is None:
                os.environ.pop("SENDER_NAME", None)
            else:
                os.environ["SENDER_NAME"] = previous
            conn.close()
