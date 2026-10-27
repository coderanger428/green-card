import json
import sqlite3
import unittest

import core.db as db
from datetime import datetime, timezone

from core.github_enrich import (
    adopted_names,
    build_social_links,
    format_expiration_label,
    github_token_accepted,
    github_token_health,
    parse_github_expiration,
    place_from_text,
    should_adopt_github_name,
    token_expires_soon,
)


class NameAdoptionTests(unittest.TestCase):
    def test_slug_name_takes_github_display_name(self):
        self.assertTrue(
            should_adopt_github_name("serinir", "https://dev.to/serinir", "Merzoug Imad-eddine")
        )
        self.assertEqual(
            adopted_names("serinir", "serinir", "https://dev.to/serinir", "Merzoug Imad-eddine"),
            ("Merzoug Imad-eddine", "Merzoug Imad-eddine"),
        )

    def test_real_devto_name_stays(self):
        self.assertFalse(
            should_adopt_github_name("Ada Lovelace", "https://dev.to/ada", "Octavia")
        )
        self.assertEqual(
            adopted_names("Ada Lovelace", "Ada Lovelace", "https://dev.to/ada", "Octavia"),
            ("Ada Lovelace", "Ada Lovelace"),
        )

    def test_edited_greeting_is_kept(self):
        self.assertEqual(
            adopted_names("serinir", "Hi Imad", "https://dev.to/serinir", "Merzoug Imad-eddine"),
            ("Merzoug Imad-eddine", "Hi Imad"),
        )

    def test_blank_github_name_is_ignored(self):
        self.assertEqual(
            adopted_names("serinir", "serinir", "https://dev.to/serinir", "  "),
            ("serinir", "serinir"),
        )


class SocialLinkTests(unittest.TestCase):
    def test_x_link_and_dedup(self):
        links = build_social_links(
            {"twitter_username": "ada"},
            [
                {"provider": "twitter", "url": "https://twitter.com/ada"},
                {"provider": "linkedin", "url": "https://linkedin.com/in/ada"},
                {"provider": "generic", "url": "https://github.com/ada"},
                {"provider": "generic", "url": "https://discord.gg/abc"},
                {"provider": "generic", "url": "https://t.me/ada"},
                {"provider": "generic", "url": "https://stackoverflow.com/users/1/ada"},
                {"provider": "generic", "url": "https://pt.stackoverflow.com/users/2/ada"},
                {"provider": "generic", "url": "https://bsky.app/profile/ada"},
                {"provider": "generic", "url": "https://dev.to/ada"},
            ],
        )
        self.assertEqual(
            links,
            [
                {"provider": "x", "url": "https://x.com/ada", "status": "not_sent"},
                {"provider": "linkedin", "url": "https://linkedin.com/in/ada", "status": "not_sent"},
                {"provider": "discord", "url": "https://discord.gg/abc", "status": "not_sent"},
                {"provider": "telegram", "url": "https://t.me/ada", "status": "not_sent"},
                {"provider": "stackoverflow", "url": "https://stackoverflow.com/users/1/ada", "status": "not_sent"},
                {"provider": "stackoverflow", "url": "https://pt.stackoverflow.com/users/2/ada", "status": "not_sent"},
                {"provider": "bluesky", "url": "https://bsky.app/profile/ada", "status": "not_sent"},
            ],
        )


class ProfileStoreTests(unittest.TestCase):
    def test_update_keeps_updated_at_and_marks_empty_socials(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            _, user_id = db.insert_user(
                conn,
                email="ada@gmail.com",
                name="serinir",
                link="https://dev.to/serinir",
                github="serinir",
                location="",
                country="usa",
            )
            before = conn.execute(
                "SELECT updated_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()["updated_at"]
            db.update_github_profile(
                conn,
                user_id,
                bio="builder",
                github_name="Merzoug Imad-eddine",
                socials=[],
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            self.assertEqual(row["name"], "Merzoug Imad-eddine")
            self.assertEqual(row["display_name"], "Merzoug Imad-eddine")
            self.assertEqual(row["github_bio"], "builder")
            self.assertEqual(json.loads(row["socials"]), [])
            self.assertEqual(row["updated_at"], before)
            self.assertEqual(row["link"], "https://dev.to/serinir")
            self.assertEqual(row["location"], "")
            self.assertEqual(row["country"], "usa")
        finally:
            conn.close()

    def test_noloc_takes_github_location(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA_SQL)
        try:
            _, user_id = db.insert_user(
                conn,
                email="no@gmail.com",
                name="noplace",
                link="https://dev.to/noplace",
                github="noplace",
                location="",
                country="noloc",
            )
            before = conn.execute(
                "SELECT updated_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()["updated_at"]
            db.update_github_profile(
                conn,
                user_id,
                bio="",
                github_name="",
                socials=[],
                github_location="Berlin, Germany",
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            self.assertEqual(row["location"], "Berlin, DEU")
            self.assertEqual(row["country"], "germany")
            self.assertEqual(row["updated_at"], before)

            db.update_github_profile(
                conn,
                user_id,
                bio="later",
                github_name="",
                socials=[],
                github_location="Paris, France",
            )
            row = conn.execute("SELECT location, country FROM users WHERE id = ?", (user_id,)).fetchone()
            self.assertEqual(row["location"], "Berlin, DEU")
            self.assertEqual(row["country"], "germany")
        finally:
            conn.close()


class PlaceTests(unittest.TestCase):
    def test_vague_and_blocked_locations_are_not_stored(self):
        blank = place_from_text("  Earth ")
        self.assertEqual((blank.location, blank.country, blank.skipped), ("", "noloc", False))
        blocked = place_from_text("Reykjavik, Iceland")
        self.assertTrue(blocked.skipped)
        self.assertEqual(blocked.country, "iceland")


class GithubTokenExpirationTests(unittest.TestCase):
    def test_parses_github_header_and_blank_means_unknown(self):
        self.assertEqual(
            parse_github_expiration("2027-04-01 00:00:00 UTC"),
            "2027-04-01T00:00:00+00:00",
        )
        self.assertEqual(parse_github_expiration(""), "")
        self.assertEqual(parse_github_expiration("not a date"), "")
        self.assertEqual(
            format_expiration_label("2027-04-01T00:00:00+00:00"),
            "2027-04-01 09:00 JST",
        )

    def test_soon_is_under_seven_days_and_still_in_the_future(self):
        now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        self.assertTrue(token_expires_soon("2026-11-02T00:00:00+00:00", now=now))
        self.assertFalse(token_expires_soon("2026-11-04T00:00:00+00:00", now=now))
        self.assertFalse(token_expires_soon("2026-10-01T00:00:00+00:00", now=now))
        self.assertTrue(github_token_accepted("ok"))
        self.assertTrue(github_token_accepted("no_expiration"))
        self.assertFalse(github_token_accepted("expired"))
        self.assertFalse(github_token_accepted("invalid"))
        self.assertFalse(github_token_accepted("unreachable"))

    def test_status_from_http_and_expiry(self):
        now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        future = "2027-04-01T00:00:00+00:00"
        past = "2026-01-01T00:00:00+00:00"
        self.assertEqual(
            github_token_health(http_status=200, expires_at=future, now=now),
            "ok",
        )
        self.assertEqual(
            github_token_health(http_status=200, expires_at=past, now=now),
            "expired",
        )
        self.assertEqual(
            github_token_health(http_status=200, expires_at="", now=now),
            "no_expiration",
        )
        self.assertEqual(
            github_token_health(http_status=401, expires_at=past, now=now),
            "expired",
        )
        self.assertEqual(
            github_token_health(http_status=401, expires_at="", now=now),
            "invalid",
        )
        self.assertEqual(
            github_token_health(http_status=503, expires_at="", now=now),
            "unreachable",
        )
