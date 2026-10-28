import unittest

from mail.send import normalize_display_name, pick_message, region_for_country, render_template_text


POOL = [
    {"filename": "us (1).txt", "region": "us", "subject": "US [Name]", "body": "us"},
    {"filename": "eu (1).txt", "region": "eu", "subject": "EU [Name]", "body": "eu"},
    {"filename": "ja (1).txt", "region": "ja", "subject": "JA [Name]", "body": "ja"},
    {"filename": "etc (1).txt", "region": "etc", "subject": "ETC [Name]", "body": "etc"},
]


class NormalizeDisplayNameTests(unittest.TestCase):
    def test_strips_parenthetical_pronouns(self):
        self.assertEqual(normalize_display_name("Jason Watt (He/Him)"), "Jason Watt")

    def test_strips_brackets_and_fullwidth_parens(self):
        self.assertEqual(normalize_display_name("Alex [they/them]"), "Alex")
        self.assertEqual(normalize_display_name("山田太郎（たなか）"), "山田太郎")

    def test_plain_name_unchanged_aside_from_caps(self):
        self.assertEqual(normalize_display_name("jane doe"), "Jane Doe")

    def test_mail_placeholder_uses_stripped_name(self):
        rendered = render_template_text("Hi [Name],", "Jason Watt (He/Him)", "Me", "")
        self.assertEqual(rendered, "Hi Jason Watt,")


class RegionForCountryTests(unittest.TestCase):
    def test_japan_maps_to_ja(self):
        self.assertEqual(region_for_country("japan"), "ja")
        self.assertEqual(region_for_country("jp"), "ja")
        self.assertEqual(region_for_country("jpn"), "ja")

    def test_existing_regions_unchanged(self):
        self.assertEqual(region_for_country("usa"), "us")
        self.assertEqual(region_for_country("germany"), "eu")
        self.assertEqual(region_for_country("india"), "etc")


class PickMessageTests(unittest.TestCase):
    def test_usa_uses_legacy_us_filename(self):
        filename, subject, body = pick_message(POOL, "usa", "Jane", "Me", "")
        self.assertEqual(filename, "us (1).txt")
        self.assertIn("Jane", subject)
        self.assertEqual(body, "us")

    def test_japan_uses_legacy_ja_filename(self):
        filename, subject, body = pick_message(POOL, "japan", "Taro", "Me", "")
        self.assertEqual(filename, "ja (1).txt")
        self.assertIn("Taro", subject)
        self.assertEqual(body, "ja")

    def test_ja_falls_back_to_etc_when_missing(self):
        pool = [t for t in POOL if t["region"] != "ja"]
        filename, _, _ = pick_message(pool, "japan", "Taro", "Me", "")
        self.assertEqual(filename, "etc (1).txt")

    def test_first_filename_wins_when_several_match(self):
        pool = [
            {"filename": "usa (2).txt", "region": "usa", "subject": "Second", "body": "b"},
            {"filename": "usa (1).txt", "region": "usa", "subject": "First [Name]", "body": "a"},
        ]
        filename, subject, body = pick_message(pool, "usa", "Jane", "Me", "")
        self.assertEqual(filename, "usa (1).txt")
        self.assertEqual(subject, "First Jane")
        self.assertEqual(body, "a")

    def test_named_template_overrides_the_location_match(self):
        filename, subject, body = pick_message(
            POOL, "usa", "Jane", "Me", "", filename="ja (1).txt"
        )
        self.assertEqual(filename, "ja (1).txt")
        self.assertIn("Jane", subject)
        self.assertEqual(body, "ja")


if __name__ == "__main__":
    unittest.main()
