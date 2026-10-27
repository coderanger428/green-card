import unittest

from core.github_enrich import place_from_text
from core.locations import UnknownLocation, format_place, place_decision, suggest_places


class FormatPlaceTests(unittest.TestCase):
    def test_country_only_uses_a_short_code(self):
        self.assertEqual(format_place("Brasil", "brazil"), "BRA")
        self.assertEqual(format_place("Germany", "germany"), "DEU")
        self.assertEqual(format_place("United Kingdom", "uk"), "UK")
        self.assertEqual(format_place("USA", "usa"), "US")
        self.assertEqual(format_place("United Arab Emirates", "uae"), "UAE")
        self.assertEqual(format_place("Czech Republic", "czech_republic"), "CZE")
        self.assertEqual(format_place("South Korea", "south_korea"), "KOR")

    def test_city_and_country(self):
        self.assertEqual(format_place("Berlin", "germany"), "Berlin, DEU")
        self.assertEqual(format_place("Berlin, Germany", "germany"), "Berlin, DEU")
        self.assertEqual(format_place("London, UK", "uk"), "London, UK")
        self.assertEqual(format_place("São Paulo, SP, Brasil", "brazil"), "São Paulo, BRA")
        self.assertEqual(format_place("Toronto, ON, Canada", "canada"), "Toronto, CAN")

    def test_us_state_code(self):
        self.assertEqual(format_place("California", "usa"), "CA")
        self.assertEqual(format_place("Seattle", "usa"), "Seattle, WA")
        self.assertEqual(format_place("Seattle, WA", "usa"), "Seattle, WA")
        self.assertEqual(format_place("Austin, Texas, United States", "usa"), "Austin, TX")
        self.assertEqual(format_place("San Francisco, CA, USA", "usa"), "San Francisco, CA")
        self.assertEqual(format_place("Charlotte NC", "usa"), "Charlotte, NC")
        self.assertEqual(format_place("NYC", "usa"), "New York, NY")
        self.assertEqual(format_place("San Francisco Bay Area", "usa"), "San Francisco, CA")
        self.assertEqual(format_place("Portland, ME", "usa"), "Portland, ME")
        self.assertEqual(format_place("Washington, DC", "usa"), "Washington, DC")

    def test_blank_and_noloc_stay_empty(self):
        self.assertEqual(format_place("", "germany"), "")
        self.assertEqual(format_place("Berlin", "noloc"), "")
        self.assertEqual(format_place("Berlin", ""), "")

    def test_github_place_stores_the_formatted_text(self):
        placed = place_from_text("Berlin, Germany")
        self.assertEqual(placed.location, "Berlin, DEU")
        self.assertEqual(placed.country, "germany")
        city_only = place_from_text("Seattle")
        self.assertEqual(city_only.location, "Seattle, WA")
        self.assertEqual(city_only.country, "usa")


class PlaceDecisionTests(unittest.TestCase):
    def test_blank_clears_and_unknown_is_rejected(self):
        self.assertEqual(
            place_decision("  "),
            {"location": "", "country": "noloc", "action": "save"},
        )
        with self.assertRaises(UnknownLocation):
            place_decision("not a real place xyzzy")

    def test_country_codes_and_excluded_country(self):
        self.assertEqual(
            place_decision("United States"),
            {"location": "US", "country": "usa", "action": "save"},
        )
        self.assertEqual(
            place_decision("United Kingdom"),
            {"location": "UK", "country": "uk", "action": "save"},
        )
        self.assertEqual(
            place_decision("United Arab Emirates"),
            {"location": "UAE", "country": "uae", "action": "save"},
        )
        excluded = place_decision("Seoul, South Korea")
        self.assertEqual(excluded["location"], "Seoul, KOR")
        self.assertEqual(excluded["country"], "south_korea")
        self.assertEqual(excluded["action"], "delete")

    def test_marked_location_suppresses(self):
        decision = place_decision(
            "Berlin, Germany",
            suppressed_locations={"Berlin, DEU"},
        )
        self.assertEqual(decision["action"], "suppress")
        self.assertEqual(decision["location"], "Berlin, DEU")
        self.assertEqual(decision["country"], "germany")


class SuggestPlacesTests(unittest.TestCase):
    def test_compound_names_and_cities(self):
        self.assertEqual(suggest_places("u"), [])
        united = [item["location"] for item in suggest_places("united")]
        self.assertIn("US", united)
        self.assertIn("UK", united)
        self.assertIn("UAE", united)
        self.assertEqual(suggest_places("united arab")[0]["location"], "UAE")
        self.assertEqual(suggest_places("seattle")[0]["location"], "Seattle, WA")
        self.assertEqual(suggest_places("london")[0]["location"], "London, UK")

    def test_typed_text_normalizes_and_stored_places_match(self):
        typed = suggest_places("Berlin, Germany")
        self.assertEqual(typed[0]["location"], "Berlin, DEU")
        self.assertEqual(typed[0]["action"], "save")
        stored = [
            item["location"]
            for item in suggest_places(
                "ber",
                stored=[{"location": "Berlin, DEU", "country": "germany"}],
            )
        ]
        self.assertIn("Berlin, DEU", stored)
        self.assertEqual(suggest_places("berlin", stored=[{"location": "Berlin, DEU", "country": "germany"}])[0]["location"], "Berlin, DEU")

    def test_excluded_and_suppressed_marks(self):
        excluded = suggest_places("south korea")[0]
        self.assertEqual(excluded["location"], "KOR")
        self.assertEqual(excluded["action"], "delete")
        suppressed = suggest_places(
            "berlin",
            suppressed_locations={"Berlin, DEU"},
            stored=[{"location": "Berlin, DEU", "country": "germany"}],
        )[0]
        self.assertEqual(suppressed["action"], "suppress")


if __name__ == "__main__":
    unittest.main()
