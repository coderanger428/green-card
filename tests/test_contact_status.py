import json
import sqlite3
import unittest

import core.db as db


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_SQL)
    return conn


def _user(conn, email, mail_status="not_sent"):
    now = "2026-10-27T00:00:00+09:00"
    conn.execute(
        """
        INSERT INTO users (
            email, name, link, location, country, mail_status, created_at, updated_at
        ) VALUES (?, 'Ada', 'https://dev.to/ada', 'US', 'usa', ?, ?, ?)
        """,
        (email, mail_status, now, now),
    )
    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    ).fetchone()["id"]


class ManualContactTests(unittest.TestCase):
    def test_queued_mail_returns_to_untouched_and_passwords_clear_once(self):
        conn = _conn()
        try:
            conn.execute("ALTER TABLE users DROP COLUMN social_status")
            user_id = _user(conn, "queued@gmail.com", "sending")
            now = "2026-10-27T00:00:00+09:00"
            conn.execute(
                """
                INSERT INTO mail_accounts (
                    email, app_password, active, daily_cap, created_at, updated_at
                ) VALUES ('from@gmail.com', 'secret-app-password', 1, 20, ?, ?)
                """,
                (now, now),
            )
            db.ensure_manual_contact(conn)
            row = conn.execute(
                "SELECT mail_status, social_status FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            self.assertEqual(row["mail_status"], "not_sent")
            self.assertEqual(row["social_status"], "not_sent")
            password = conn.execute(
                "SELECT app_password FROM mail_accounts"
            ).fetchone()["app_password"]
            self.assertEqual(password, "")

            conn.execute(
                "UPDATE mail_accounts SET app_password = 'typed-later'"
            )
            db.ensure_manual_contact(conn)
            password = conn.execute(
                "SELECT app_password FROM mail_accounts"
            ).fetchone()["app_password"]
            self.assertEqual(password, "typed-later")
        finally:
            conn.close()

    def test_sent_mail_stores_sender_and_failed_keeps_it(self):
        conn = _conn()
        try:
            user_id = _user(conn, "ada@gmail.com")
            with self.assertRaises(ValueError):
                db.set_user_contact(
                    conn, user_id, channel="email", status="sent", sender_email="  "
                )
            saved = db.set_user_contact(
                conn,
                user_id,
                channel="email",
                status="sent",
                sender_email="from@gmail.com",
            )
            self.assertEqual(saved["mail_status"], "sent")
            self.assertEqual(saved["sender_email"], "from@gmail.com")

            failed = db.set_user_contact(
                conn, user_id, channel="email", status="failed"
            )
            self.assertEqual(failed["mail_status"], "failed")
            self.assertEqual(failed["sender_email"], "from@gmail.com")
        finally:
            conn.close()

    def test_each_social_link_keeps_its_own_status(self):
        conn = _conn()
        try:
            user_id = _user(conn, "social@gmail.com", "sent")
            conn.execute(
                "UPDATE users SET socials = ? WHERE id = ?",
                (
                    '[{"provider":"linkedin","url":"https://linkedin.com/in/ada"},'
                    '{"provider":"telegram","url":"https://t.me/ada"}]',
                    user_id,
                ),
            )
            saved = db.set_user_contact(
                conn,
                user_id,
                channel="social",
                status="sent",
                social_url="https://linkedin.com/in/ada/",
            )
            links = json.loads(saved["socials"])
            self.assertEqual(links[0]["status"], "sent")
            self.assertEqual(links[1]["status"], "not_sent")
            self.assertEqual(saved["mail_status"], "sent")

            cleared = db.set_user_contact(
                conn,
                user_id,
                channel="social",
                status="not_sent",
                social_url="https://linkedin.com/in/ada",
            )
            self.assertEqual(json.loads(cleared["socials"])[0]["status"], "not_sent")
            with self.assertRaises(ValueError):
                db.set_user_contact(conn, user_id, channel="social", status="failed")
            self.assertIsNone(
                db.set_user_contact(
                    conn,
                    999,
                    channel="social",
                    status="failed",
                    social_url="https://linkedin.com/in/ada",
                )
            )
        finally:
            conn.close()

    def test_profile_refresh_keeps_a_link_status(self):
        conn = _conn()
        try:
            user_id = _user(conn, "refresh@gmail.com")
            conn.execute(
                "UPDATE users SET socials = ? WHERE id = ?",
                (
                    '[{"provider":"linkedin","url":"https://linkedin.com/in/ada","status":"failed"}]',
                    user_id,
                ),
            )
            db.update_github_profile(
                conn,
                user_id,
                bio="",
                github_name="",
                socials=[
                    {"provider": "linkedin", "url": "https://linkedin.com/in/ada", "status": "not_sent"},
                    {"provider": "x", "url": "https://x.com/ada", "status": "not_sent"},
                ],
            )
            links = json.loads(
                conn.execute("SELECT socials FROM users WHERE id = ?", (user_id,)).fetchone()["socials"]
            )
            self.assertEqual(links[0]["status"], "failed")
            self.assertEqual(links[1], {"provider": "x", "url": "https://x.com/ada", "status": "not_sent"})
        finally:
            conn.close()

    def test_old_user_status_is_copied_onto_each_link_once(self):
        conn = _conn()
        try:
            user_id = _user(conn, "old@gmail.com")
            conn.execute(
                "UPDATE users SET social_status = 'sent', socials = ? WHERE id = ?",
                ('[{"provider":"discord","url":"https://discord.gg/ada"}]', user_id),
            )
            db.ensure_social_link_status(conn)
            db.ensure_social_link_status(conn)
            links = json.loads(
                conn.execute("SELECT socials FROM users WHERE id = ?", (user_id,)).fetchone()["socials"]
            )
            self.assertEqual(links, [{"provider": "discord", "url": "https://discord.gg/ada", "status": "sent"}])
        finally:
            conn.close()

    def test_known_site_is_named_and_keeps_its_status(self):
        conn = _conn()
        try:
            user_id = _user(conn, "sites@gmail.com")
            conn.execute(
                "UPDATE users SET socials = ? WHERE id = ?",
                (
                    '['
                    '{"provider":"generic","url":"https://stackoverflow.com/users/1/ada","status":"failed"},'
                    '{"provider":"generic","url":"https://github.com/ada","status":"sent"}'
                    ']',
                    user_id,
                ),
            )
            db.ensure_social_provider_names(conn)
            db.ensure_social_provider_names(conn)
            links = json.loads(
                conn.execute("SELECT socials FROM users WHERE id = ?", (user_id,)).fetchone()["socials"]
            )
            self.assertEqual(
                links,
                [{"provider": "stackoverflow", "url": "https://stackoverflow.com/users/1/ada", "status": "failed"}],
            )
        finally:
            conn.close()

    def test_source_profile_is_removed_from_socials(self):
        conn = _conn()
        try:
            user_id = _user(conn, "source-link@gmail.com")
            conn.execute(
                "UPDATE users SET link = ?, github = ?, socials = ? WHERE id = ?",
                (
                    "https://dev.to/ada",
                    "ada",
                    '['
                    '{"provider":"devto","url":"https://dev.to/ada","status":"sent"},'
                    '{"provider":"x","url":"https://x.com/ada","status":"failed"}'
                    ']',
                    user_id,
                ),
            )
            db.ensure_drop_source_socials(conn)
            db.ensure_drop_source_socials(conn)
            links = json.loads(
                conn.execute("SELECT socials FROM users WHERE id = ?", (user_id,)).fetchone()["socials"]
            )
            self.assertEqual(
                links,
                [{"provider": "x", "url": "https://x.com/ada", "status": "failed"}],
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
