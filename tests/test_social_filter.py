import json
import sqlite3
import unittest

import core.db as db
from server.dashboard import social_account_clauses


class SocialAccountClauseTests(unittest.TestCase):
    def test_unchecked_sends_no_sql(self):
        where, params = social_account_clauses([])
        self.assertEqual(where, [])
        self.assertEqual(params, [])

    def test_unknown_values_are_ignored(self):
        where, params = social_account_clauses(["github", "LINKEDIN", "linkedin"])
        self.assertEqual(params, ["linkedin"])
        self.assertEqual(len(where), 1)

    def test_whatsapp_is_accepted(self):
        where, params = social_account_clauses(["WhatsApp", "whatsapp"])
        self.assertEqual(params, ["whatsapp"])
        self.assertEqual(len(where), 1)

    def test_checked_platforms_are_anded(self):
        where, params = social_account_clauses(
            ["linkedin", "telegram", "discord"]
        )
        self.assertEqual(params, ["linkedin", "telegram", "discord"])
        self.assertEqual(len(where), 3)


class SocialAccountQueryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA_SQL)
        now = "2026-10-24T00:00:00+09:00"
        rows = [
            (1, "li@gmail.com", [{"provider": "linkedin", "url": "https://linkedin.com/in/a"}]),
            (2, "tg@gmail.com", [{"provider": "telegram", "url": "https://t.me/a"}]),
            (
                3,
                "all@gmail.com",
                [
                    {"provider": "linkedin", "url": "https://linkedin.com/in/b"},
                    {"provider": "telegram", "url": "https://t.me/b"},
                    {"provider": "discord", "url": "https://discord.gg/b"},
                ],
            ),
            (4, "none@gmail.com", []),
            (5, "broken@gmail.com", None),
            (6, "wa@gmail.com", [{"provider": "whatsapp", "url": "https://wa.me/15551212"}]),
        ]
        for uid, email, socials in rows:
            self.conn.execute(
                """
                INSERT INTO users (
                    id, email, name, link, location, country, socials,
                    created_at, updated_at
                )
                VALUES (?, ?, '', '', '', 'usa', ?, ?, ?)
                """,
                (
                    uid,
                    email,
                    None if socials is None else json.dumps(socials),
                    now,
                    now,
                ),
            )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _ids(self, has_social):
        where, params = social_account_clauses(has_social)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self.conn.execute(
            f"SELECT id FROM users{clause} ORDER BY id", params
        ).fetchall()
        return [row["id"] for row in rows]

    def test_linkedin_only(self):
        self.assertEqual(self._ids(["linkedin"]), [1, 3])

    def test_all_three_requires_every_account(self):
        self.assertEqual(self._ids(["linkedin", "telegram", "discord"]), [3])

    def test_whatsapp_only(self):
        self.assertEqual(self._ids(["whatsapp"]), [6])

    def test_none_checked_returns_everyone(self):
        self.assertEqual(self._ids([]), [1, 2, 3, 4, 5, 6])


if __name__ == "__main__":
    unittest.main()
