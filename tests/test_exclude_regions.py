import sqlite3
import tempfile
import unittest
from pathlib import Path

import core.db as db
import core.locations as locations


class ExcludeRegionsFileTests(unittest.TestCase):
    def setUp(self):
        locations._exclude_cache_key = None
        db._purged_exclude_slugs = None

    def test_parses_slugs_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exclude-regions.txt"
            path.write_text("# ignore\n\nIceland\nmalta\n", encoding="utf-8")
            slugs = locations.excluded_country_slugs(path)
            self.assertIn("iceland", slugs)
            self.assertIn("malta", slugs)
            self.assertNotIn("india", slugs)

    def test_named_region_expands_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exclude-regions.txt"
            path.write_text("apac\n", encoding="utf-8")
            slugs = locations.excluded_country_slugs(path)
            self.assertIn("india", slugs)
            self.assertIn("japan", slugs)
            self.assertIn("australia", slugs)
            self.assertNotIn("germany", slugs)

    def test_noloc_and_etc_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exclude-regions.txt"
            path.write_text("noloc\netc\n", encoding="utf-8")
            slugs = locations.excluded_country_slugs(path)
            self.assertNotIn("noloc", slugs)
            self.assertNotIn("etc", slugs)

    def test_ja_alias_is_japan(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exclude-regions.txt"
            path.write_text("ja\n", encoding="utf-8")
            slugs = locations.excluded_country_slugs(path)
            self.assertEqual(slugs, frozenset({"japan"}))

    def test_seed_file_skips_tiny_countries_not_india(self):
        self.assertTrue(locations.is_skipped_country("iceland"))
        self.assertTrue(locations.is_skipped_country("south_korea"))
        self.assertFalse(locations.is_skipped_country("india"))
        self.assertFalse(locations.is_skipped_country("noloc"))
        self.assertFalse(locations.is_skipped_country("usa"))

    def test_add_excluded_country_appends_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exclude-regions.txt"
            path.write_text("malta\n", encoding="utf-8")
            first = locations.add_excluded_country("Iceland", path)
            second = locations.add_excluded_country("iceland", path)
            self.assertEqual(first, "iceland")
            self.assertEqual(second, "iceland")
            self.assertEqual(path.read_text(encoding="utf-8"), "malta\niceland\n")
            self.assertIn("iceland", locations.excluded_country_slugs(path))

    def test_add_excluded_country_rejects_noloc(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exclude-regions.txt"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                locations.add_excluded_country("noloc", path)

    def test_purge_deletes_excluded_users(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        conn.execute(
            """
            INSERT INTO users (email, name, display_name, link, location, country,
                               mail_status, created_at, updated_at)
            VALUES
              ('a@x.com', 'A', 'A', '', '', 'iceland', 'not_sent', 't', 't'),
              ('b@x.com', 'B', 'B', '', '', 'india', 'not_sent', 't', 't')
            """
        )
        conn.commit()
        try:
            deleted = db.delete_users_by_countries(conn, {"iceland"})
            self.assertEqual(deleted, 1)
            left = conn.execute("SELECT country FROM users").fetchall()
            self.assertEqual([r["country"] for r in left], ["india"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
