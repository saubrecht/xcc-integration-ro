"""Polling selection regressions, runnable without Home Assistant or pytest."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "_page_selection_helpers",
    Path(__file__).resolve().parents[1] / "custom_components/xcc/entity_helpers.py",
)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


class TestPageSelection(unittest.TestCase):
    ip = "192.0.2.1"
    pages = ["NAST1.XML", "NAST2.XML", "NAST3.XML"]

    def setUp(self):
        raw = [
            {"state": "10", "attributes": {"field_name": prop, "page": page}}
            for page, prop in [
                ("NAST1.XML", "SHARED"),
                ("NAST2.XML", "SHARED"),
                ("NAST2.XML", "SECOND"),
            ]
        ]
        self.data, self.entities = helpers.process_entities(raw, {}, "czech")

    def select(self, disabled=(), loaded=None):
        return helpers.select_data_pages(
            self.pages, set(self.pages if loaded is None else loaded),
            self.entities, set(disabled), self.ip,
        )

    def test_startup_fetches_every_page_before_registry_exists(self):
        self.assertEqual(self.select(loaded=[]), self.pages)

    def test_successful_empty_page_is_skipped(self):
        self.assertEqual(self.select(), self.pages[:2])

    def test_page_with_only_duplicate_values_is_skipped(self):
        raw = [
            {"state": "10", "attributes": {"field_name": "SHARED", "page": page}}
            for page in self.pages[:2]
        ]
        _, self.entities = helpers.process_entities(raw, {}, "czech")
        self.assertEqual(self.select(), ["NAST1.XML"])

    def test_failed_or_unparseable_page_keeps_retrying(self):
        self.assertEqual(self.select(loaded=self.pages[:2]), self.pages)

    def test_page_with_only_disabled_entities_is_skipped(self):
        disabled = [("sensor", f"{self.ip}_xcc_second")]
        self.assertEqual(self.select(disabled), ["NAST1.XML"])

    def test_reenabled_entity_restores_its_page(self):
        disabled = [("sensor", f"{self.ip}_xcc_second")]
        self.assertEqual(self.select(disabled), ["NAST1.XML"])
        self.assertEqual(self.select(), self.pages[:2])

    def test_all_disabled_requires_no_data_pages(self):
        disabled = [("sensor", f"{self.ip}_{key}") for key in self.entities]
        self.assertEqual(self.select(disabled), [])

    def test_identity_uses_domain_and_controller_ip(self):
        self.assertEqual(self.select([("binary_sensor", f"{self.ip}_xcc_second")]), self.pages[:2])
        self.assertEqual(self.select([("sensor", "192.0.2.2_xcc_second")]), self.pages[:2])

    def test_one_enabled_entity_keeps_page(self):
        # SHARED remains owned by NAST1 even when NAST2 also contains it.
        self.assertEqual(self.entities["xcc_shared"]["page"], "NAST1.XML")
        disabled = [("sensor", f"{self.ip}_xcc_shared")]
        self.assertEqual(self.select(disabled), ["NAST2.XML"])
        self.assertEqual(self.entities["xcc_shared"]["page"], "NAST1.XML")

    def test_renamed_entity_is_matched_by_unique_id(self):
        # No display name or entity_id from the HA registry enters selection.
        disabled = [("sensor", f"{self.ip}_xcc_second")]
        self.assertEqual(self.select(disabled), ["NAST1.XML"])


if __name__ == "__main__":
    unittest.main()
