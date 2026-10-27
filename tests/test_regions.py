import tempfile
import unittest
from pathlib import Path

import mail.regions as regions
from mail.send import (
    create_template,
    delete_template,
    list_templates,
    load_template_pool,
    parse_template_text,
    pick_message,
    region_for_country,
    update_template,
)


class ScheduleRegionTests(unittest.TestCase):
    def test_japan_maps_to_ja(self):
        self.assertEqual(region_for_country("japan"), "ja")
        self.assertEqual(region_for_country("jp"), "ja")
        self.assertEqual(region_for_country("jpn"), "ja")

    def test_existing_windows_unchanged(self):
        self.assertEqual(region_for_country("usa"), "us")
        self.assertEqual(region_for_country("germany"), "eu")
        self.assertEqual(region_for_country("india"), "etc")
        self.assertEqual(region_for_country("serbia"), "etc")


class TemplateCandidateTests(unittest.TestCase):
    def test_germany_prefers_country_then_eu_then_emea(self):
        self.assertEqual(
            regions.template_region_candidates("germany"),
            ["germany", "eu", "emea", "etc"],
        )

    def test_india_uses_apac(self):
        self.assertEqual(
            regions.template_region_candidates("india"),
            ["india", "apac", "etc"],
        )

    def test_catalog_apac_lists_asian_members(self):
        catalog = regions.suggestion_catalog()
        apac = next(item for item in catalog["groups"] if item["slug"] == "apac")
        self.assertIn("india", apac["members"])
        self.assertIn("china", apac["members"])
        self.assertIn("japan", apac["members"])
        self.assertGreaterEqual(apac["member_count"], 20)

    def test_japan_is_country_then_apac(self):
        self.assertEqual(
            regions.template_region_candidates("japan"),
            ["japan", "apac", "etc"],
        )
        self.assertEqual(regions.canonical_template_region("ja"), "japan")
        self.assertEqual(regions.canonical_template_region("jp"), "japan")
        self.assertEqual(regions.canonical_template_region("us"), "usa")

    def test_usa_uses_country_name(self):
        self.assertEqual(
            regions.template_region_candidates("usa"),
            ["usa", "etc"],
        )

    def test_suggestion_catalog_includes_named_regions(self):
        catalog = regions.suggestion_catalog(user_counts={"india": 4})
        slugs = [item["slug"] for item in catalog["groups"]]
        self.assertEqual(slugs, ["eu", "emea", "apac", "latam", "etc"])
        india = next(item for item in catalog["countries"] if item["slug"] == "india")
        self.assertEqual(india["users"], 4)
        self.assertEqual(india["templates"], 0)
        self.assertTrue(any(item["slug"] == "brazil" for item in catalog["countries"]))
        emea = next(item for item in catalog["groups"] if item["slug"] == "emea")
        self.assertEqual(emea["templates"], 0)

    def test_catalog_counts_templates_and_custom_regions(self):
        catalog = regions.suggestion_catalog(
            user_counts={},
            templates=[
                {"region": "india"},
                {"region": "india"},
                {"region": "apac"},
                {"region": "custom_team"},
            ],
        )
        india = next(item for item in catalog["countries"] if item["slug"] == "india")
        self.assertEqual(india["templates"], 2)
        apac = next(item for item in catalog["groups"] if item["slug"] == "apac")
        self.assertEqual(apac["templates"], 1)
        custom_team = next(
            item for item in catalog["countries"] if item["slug"] == "custom_team"
        )
        self.assertEqual(custom_team["templates"], 1)
        self.assertEqual(custom_team["kind"], "country")


class PickMessageRegionTests(unittest.TestCase):
    def test_country_template_beats_group(self):
        pool = [
            {"filename": "eu (1).txt", "region": "eu", "subject": "EU", "body": "eu"},
            {
                "filename": "germany (1).txt",
                "region": "germany",
                "subject": "DE",
                "body": "de",
            },
            {"filename": "etc (1).txt", "region": "etc", "subject": "ETC", "body": "etc"},
        ]
        filename, subject, body = pick_message(pool, "germany", "Ada", "Me", "")
        self.assertEqual(filename, "germany (1).txt")
        self.assertEqual(subject, "DE")
        self.assertEqual(body, "de")

    def test_apac_used_when_no_country_file(self):
        pool = [
            {"filename": "apac (1).txt", "region": "apac", "subject": "APAC", "body": "a"},
            {"filename": "etc (1).txt", "region": "etc", "subject": "ETC", "body": "e"},
        ]
        filename, _, _ = pick_message(pool, "india", "Ravi", "Me", "")
        self.assertEqual(filename, "apac (1).txt")

    def test_adding_apac_covers_asian_countries(self):
        available = {"us", "eu", "etc", "apac"}
        asian = sorted(regions.APAC_COUNTRIES)
        self.assertTrue(asian)
        pool = [
            {"filename": "us (1).txt", "region": "us", "subject": "US", "body": "u"},
            {"filename": "eu (1).txt", "region": "eu", "subject": "EU", "body": "e"},
            {"filename": "etc (1).txt", "region": "etc", "subject": "ETC", "body": "x"},
            {"filename": "apac (1).txt", "region": "apac", "subject": "APAC", "body": "a"},
        ]
        for country in asian:
            with self.subTest(country=country):
                self.assertEqual(
                    regions.select_template_region(country, available),
                    "apac",
                )
                filename, _, _ = pick_message(pool, country, "Ada", "Me", "")
                self.assertEqual(filename, "apac (1).txt")

    def test_japan_country_file_beats_apac(self):
        self.assertEqual(
            regions.select_template_region("japan", {"japan", "apac", "etc"}),
            "japan",
        )
        self.assertEqual(
            regions.select_template_region("japan", {"ja", "apac", "etc"}),
            "japan",
        )
        self.assertEqual(
            regions.select_template_region("japan", {"us", "eu", "etc", "apac"}),
            "apac",
        )

    def test_falls_back_to_etc_without_apac(self):
        pool = [
            {"filename": "eu (1).txt", "region": "eu", "subject": "EU", "body": "eu"},
            {"filename": "etc (1).txt", "region": "etc", "subject": "ETC", "body": "etc"},
        ]
        filename, _, _ = pick_message(pool, "india", "Ravi", "Me", "")
        self.assertEqual(filename, "etc (1).txt")


class TemplateFileTests(unittest.TestCase):
    def test_create_update_delete_custom_country(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            created = create_template(
                "india",
                "Hello [Name]",
                "Body for India",
                templates_dir=folder,
            )
            self.assertEqual(created["filename"], "india (1).txt")
            self.assertEqual(created["region"], "india")
            self.assertEqual(created["subject"], "Hello [Name]")

            pool = load_template_pool(folder)
            self.assertEqual(len(pool), 1)
            self.assertEqual(pool[0]["region"], "india")

            updated = update_template(
                created["filename"],
                region="apac",
                subject="APAC hello",
                body="Asia-Pacific body",
                templates_dir=folder,
            )
            self.assertEqual(updated["filename"], "apac (1).txt")
            self.assertFalse((folder / "india (1).txt").exists())
            self.assertTrue((folder / "apac (1).txt").exists())

            second = create_template("etc", "Other", "Fallback body", templates_dir=folder)
            self.assertEqual(len(list_templates(folder)), 2)
            delete_template(updated["filename"], templates_dir=folder)
            remaining = list_templates(folder)
            self.assertEqual([item["filename"] for item in remaining], [second["filename"]])

            with self.assertRaises(ValueError):
                delete_template(second["filename"], templates_dir=folder)

    def test_ja_alias_writes_japan_country_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "ja (1).txt").write_text(
                "Subject: Legacy JP\nHello\n", encoding="utf-8"
            )
            parsed = parse_template_text(
                "ja (1).txt", (folder / "ja (1).txt").read_text(encoding="utf-8")
            )
            self.assertEqual(parsed["region"], "japan")
            self.assertEqual(parsed["filename"], "ja (1).txt")

            created = create_template("ja", "Hello Japan", "Body", templates_dir=folder)
            self.assertEqual(created["filename"], "japan (1).txt")
            self.assertEqual(created["region"], "japan")

            renamed = update_template(
                "ja (1).txt",
                region="japan",
                subject="Legacy JP",
                body="Hello",
                templates_dir=folder,
            )
            self.assertEqual(renamed["filename"], "japan (2).txt")
            self.assertFalse((folder / "ja (1).txt").exists())

    def test_us_alias_writes_usa_country_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            created = create_template("us", "Hello US", "Body", templates_dir=folder)
            self.assertEqual(created["filename"], "usa (1).txt")
            self.assertEqual(created["region"], "usa")


if __name__ == "__main__":
    unittest.main()
