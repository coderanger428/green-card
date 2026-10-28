import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import core.db as db
import scrapers.devto.scrape as main

TOKYO = timezone(timedelta(hours=9))


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_SQL)
    return conn


class ScrapeCapOverrideTests(unittest.TestCase):
    def test_default_cap_ignores_mail_accounts(self):
        conn = _conn()
        try:
            created = datetime.now(TOKYO).isoformat()
            conn.execute(
                """
                INSERT INTO mail_accounts
                    (email, app_password, active, daily_cap, created_at, updated_at)
                VALUES (?, 'pw', 1, 10, ?, ?)
                """,
                ("sender@gmail.com", created, created),
            )
            conn.commit()
            self.assertTrue(db.scrape_cap_enabled(conn))
            self.assertEqual(db.scrape_daily_save_limit(conn), db.DEFAULT_SCRAPE_DAILY_CAP)
        finally:
            conn.close()

    def test_static_cap_and_unlimited(self):
        conn = _conn()
        try:
            db.set_scrape_cap(conn, enabled=True, cap=40)
            conn.commit()
            self.assertEqual(db.get_scrape_daily_cap(conn), 40)
            self.assertEqual(db.scrape_daily_save_limit(conn), 40)
            db.set_scrape_cap(conn, enabled=False, cap=40)
            self.assertIsNone(db.scrape_daily_save_limit(conn))
            self.assertEqual(db.get_scrape_daily_cap(conn), 40)
        finally:
            conn.close()

    def test_startup_copies_a_mail_ratio_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db.init_db(root)
            created = datetime.now(TOKYO).isoformat()
            with db.get_conn(root) as conn:
                db.set_meta(conn, "scrape_cap_static_v1", "")
                db.set_meta(conn, "scrape_daily_cap", "")
                db.set_meta(conn, "scrape_cap_enabled", "")
                conn.execute(
                    """
                    INSERT INTO mail_accounts
                        (email, app_password, active, daily_cap, created_at, updated_at)
                    VALUES (?, 'pw', 1, 10, ?, ?)
                    """,
                    ("sender@gmail.com", created, created),
                )
                expected = db._legacy_mail_ratio_cap(conn)
            db.init_db(root)
            with db.get_conn(root) as conn:
                self.assertEqual(db.get_scrape_daily_cap(conn), expected)
                self.assertTrue(db.scrape_cap_enabled(conn))
                db.set_scrape_cap(conn, enabled=False, cap=8)
            db.init_db(root)
            with db.get_conn(root) as conn:
                self.assertFalse(db.scrape_cap_enabled(conn))
                self.assertEqual(db.get_scrape_daily_cap(conn), 8)
                self.assertIsNone(db.scrape_daily_save_limit(conn))


class ScrapePauseAndHeartbeatTests(unittest.TestCase):
    def test_pause_flag(self):
        conn = _conn()
        try:
            self.assertFalse(db.is_scrape_paused(conn))
            db.set_scrape_paused(conn, True)
            self.assertTrue(db.is_scrape_paused(conn))
            db.set_scrape_paused(conn, False)
            self.assertFalse(db.is_scrape_paused(conn))
        finally:
            conn.close()

    def test_snapshot_stopped_without_heartbeat(self):
        conn = _conn()
        try:
            now = datetime(2026, 8, 23, 14, 0, tzinfo=TOKYO)
            snap = db.scrape_control_snapshot(conn, now=now)
            self.assertEqual(snap["status"], "stopped")
            self.assertFalse(snap["alive"])
            self.assertTrue(snap["cap_enabled"])
            self.assertEqual(snap["daily_cap"], db.DEFAULT_SCRAPE_DAILY_CAP)
        finally:
            conn.close()

    def test_snapshot_running_with_fresh_heartbeat(self):
        conn = _conn()
        try:
            now = datetime(2026, 8, 23, 14, 0, tzinfo=TOKYO)
            db.set_meta(conn, "scrape_heartbeat_at", now.isoformat())
            db.set_meta(conn, "scrape_loop", db.SCRAPE_LOOP_RUNNING)
            snap = db.scrape_control_snapshot(conn, now=now)
            self.assertTrue(snap["alive"])
            self.assertEqual(snap["status"], "running")
        finally:
            conn.close()

    def test_snapshot_paused_when_alive(self):
        conn = _conn()
        try:
            now = datetime(2026, 8, 23, 14, 0, tzinfo=TOKYO)
            db.set_scrape_paused(conn, True)
            db.set_meta(conn, "scrape_heartbeat_at", now.isoformat())
            snap = db.scrape_control_snapshot(conn, now=now)
            self.assertEqual(snap["status"], "paused")
            self.assertTrue(snap["paused"])
        finally:
            conn.close()

    def test_stale_heartbeat_is_stopped(self):
        conn = _conn()
        try:
            now = datetime(2026, 8, 23, 14, 0, tzinfo=TOKYO)
            stale = now - timedelta(seconds=db.SCRAPE_HEARTBEAT_STALE_SEC + 5)
            db.set_meta(conn, "scrape_heartbeat_at", stale.isoformat())
            snap = db.scrape_control_snapshot(conn, now=now)
            self.assertEqual(snap["status"], "stopped")
            self.assertFalse(snap["alive"])
        finally:
            conn.close()

    def test_snapshot_idling_when_at_cap(self):
        conn = _conn()
        try:
            now = datetime(2026, 8, 23, 14, 0, tzinfo=TOKYO)
            db.set_meta(conn, "scrape_heartbeat_at", now.isoformat())
            db.set_scrape_cap(conn, enabled=True, cap=1)
            conn.execute(
                """
                INSERT INTO users (id, email, name, link, location, country,
                                   created_at, updated_at)
                VALUES (1, 'a@example.com', '', '', '', 'usa', ?, ?)
                """,
                (now.isoformat(), now.isoformat()),
            )
            snap = db.scrape_control_snapshot(conn, now=now)
            self.assertEqual(snap["status"], "idling")
            self.assertEqual(snap["saved_today"], 1)
            self.assertEqual(snap["daily_limit"], 1)
            self.assertTrue(snap["cap_enabled"])
        finally:
            conn.close()

    def test_snapshot_keeps_running_when_cap_is_off(self):
        conn = _conn()
        try:
            now = datetime(2026, 8, 23, 14, 0, tzinfo=TOKYO)
            db.set_meta(conn, "scrape_heartbeat_at", now.isoformat())
            db.set_meta(conn, "scrape_loop", db.SCRAPE_LOOP_IDLING)
            db.set_scrape_cap(conn, enabled=False, cap=1)
            conn.execute(
                """
                INSERT INTO users (id, email, name, link, location, country,
                                   created_at, updated_at)
                VALUES (1, 'a@example.com', '', '', '', 'usa', ?, ?)
                """,
                (now.isoformat(), now.isoformat()),
            )
            snap = db.scrape_control_snapshot(conn, now=now)
            self.assertEqual(snap["status"], "running")
            self.assertFalse(snap["cap_enabled"])
            self.assertIsNone(snap["daily_limit"])
            self.assertEqual(snap["daily_cap"], 1)
            self.assertEqual(snap["saved_today"], 1)
        finally:
            conn.close()


class GitHubUsernameNormalizationTests(unittest.TestCase):
    def test_strips_full_github_url(self):
        self.assertEqual(main.normalize_github_username("github.com/alice"), "alice")
        self.assertEqual(main.normalize_github_username("https://github.com/alice"), "alice")
        self.assertEqual(main.normalize_github_username("https://github.com/alice/"), "alice")

    def test_rejects_invalid_handles(self):
        self.assertEqual(main.normalize_github_username("https://example.com/foo"), "")
        self.assertEqual(main.normalize_github_username("alice/evil"), "alice")
        self.assertEqual(main.normalize_github_username(""), "")


class ScraperDashboardRoutesTests(unittest.TestCase):
    def test_scraper_routes_are_registered(self):
        from server.dashboard import app

        paths = {getattr(route, "path", "") for route in app.routes}
        self.assertIn("/api/scraper", paths)
        self.assertIn("/api/scraper/pause", paths)
        self.assertIn("/api/scraper/cap", paths)
        self.assertIn("/api/templates", paths)
        self.assertIn("/api/template-regions", paths)
        self.assertIn("/api/countries/{country}/exclude", paths)


class ScraperParameterTests(unittest.TestCase):
    def test_existing_last_id_is_copied_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = db.db_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path)
            conn.executescript(db.SCHEMA_SQL)
            conn.execute(
                """
                CREATE TABLE scrape_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_id INTEGER NOT NULL DEFAULT 0,
                    total_saved INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO scrape_state (id, last_id, total_saved, updated_at) "
                "VALUES (1, 836290, 10, '2026-01-01T00:00:00+09:00')"
            )
            conn.commit()
            conn.close()

            db.init_db(root)

            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            raw = conn.execute(
                "SELECT parameter FROM scraper_parameter WHERE platform_id = 'devto'"
            ).fetchone()["parameter"]
            gone = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'scrape_state'"
            ).fetchone()
            conn.execute(
                "UPDATE scraper_parameter SET parameter = ? WHERE platform_id = 'devto'",
                ('{"cursor":"keep","last_id":1}',),
            )
            conn.commit()
            conn.close()

            self.assertEqual(json.loads(raw)["last_id"], 836290)
            self.assertIsNone(gone)

            db.init_db(root)

            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            kept = conn.execute(
                "SELECT parameter FROM scraper_parameter WHERE platform_id = 'devto'"
            ).fetchone()["parameter"]
            conn.close()
            self.assertEqual(json.loads(kept), {"cursor": "keep", "last_id": 1})

    def test_last_id_update_keeps_other_keys_and_other_platforms(self):
        conn = _conn()
        try:
            db.set_scraper_parameter(conn, "other", {"token": "abc"})
            db.set_scraper_parameter(conn, "devto", {"cursor": "keep", "last_id": 4})
            state = db.set_scrape_state(conn, last_id=9)
            self.assertEqual(state["last_id"], 9)
            self.assertEqual(state["total_saved"], 0)
            self.assertEqual(
                db.get_scraper_parameter(conn, "devto"),
                {"cursor": "keep", "last_id": 9},
            )
            self.assertEqual(db.get_scraper_parameter(conn, "other"), {"token": "abc"})
            self.assertEqual(db.advance_last_id(conn, 8), 9)
            self.assertEqual(db.advance_last_id(conn, 12), 12)
            self.assertEqual(db.get_scraper_parameter(conn, "devto")["last_id"], 12)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
