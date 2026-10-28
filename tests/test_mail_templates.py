import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import core.db as db


class MailTemplateStoreTests(unittest.TestCase):
    def test_saved_template_stays_after_another_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db.init_db(root)
            with db.get_conn(root) as conn:
                created = db.create_mail_template(conn, "usa", "Kept in sqlite", "Body")
                self.assertTrue(created["updated_at"])
            db.init_db(root)
            with db.get_conn(root) as conn:
                rows = db.list_mail_templates(conn)
                usa = next(item for item in rows if item["filename"] == created["filename"])
                self.assertEqual(usa["subject"], "Kept in sqlite")
                self.assertEqual(usa["updated_at"], created["updated_at"])

    def test_create_rename_and_delete_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db.init_db(root)
            with db.get_conn(root) as conn:
                created = db.create_mail_template(
                    conn, "india", "Hello [Name]", "Body for India"
                )
                self.assertEqual(created["filename"], "india (1).txt")
                self.assertEqual(created["region"], "india")
                conn.execute(
                    """
                    INSERT INTO users (
                        email, name, link, location, country, mail_template,
                        created_at, updated_at
                    ) VALUES (
                        'ada@example.com', 'Ada', '', 'IN', 'india', ?,
                        '2026-10-28T00:00:00+09:00', '2026-10-28T00:00:00+09:00'
                    )
                    """,
                    (created["filename"],),
                )
                renamed = db.update_mail_template(
                    conn,
                    created["filename"],
                    region="apac",
                    subject="APAC hello",
                    body="Asia-Pacific body",
                )
                self.assertEqual(renamed["filename"], "apac (1).txt")
                stored = conn.execute(
                    "SELECT mail_template FROM users WHERE email = 'ada@example.com'"
                ).fetchone()["mail_template"]
                self.assertEqual(stored, "apac (1).txt")
                names = [item["filename"] for item in db.list_mail_templates(conn)]
                self.assertIn("apac (1).txt", names)
                self.assertNotIn("india (1).txt", names)

                db.create_mail_template(conn, "etc", "Other", "Fallback body")
                db.delete_mail_template(conn, "apac (1).txt")
                names = [item["filename"] for item in db.list_mail_templates(conn)]
                self.assertNotIn("apac (1).txt", names)
                last = names[0]
                for name in names[1:]:
                    db.delete_mail_template(conn, name)
                with self.assertRaises(ValueError):
                    db.delete_mail_template(conn, last)

    def test_blank_updated_at_is_filled_with_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db.init_db(root)
            with db.get_conn(root) as conn:
                created = db.create_mail_template(conn, "usa", "Hello", "Body")
                conn.execute(
                    "UPDATE mail_templates SET updated_at = '' WHERE filename = ?",
                    (created["filename"],),
                )
                rows = db.list_mail_templates(conn)
                usa = next(item for item in rows if item["filename"] == created["filename"])
                self.assertTrue(usa["updated_at"])
                stored = datetime.fromisoformat(usa["updated_at"])
                self.assertEqual(stored.date(), db.current_tokyo_datetime().date())

    def test_blank_subject_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db.init_db(root)
            with db.get_conn(root) as conn:
                with self.assertRaises(ValueError):
                    db.create_mail_template(conn, "usa", "  ", "Body")


if __name__ == "__main__":
    unittest.main()
