"""
Unit tests for interface/validate_lda_output.py.

The validator is the only gate between the NLP half and the SUMO half, so the
tests below are mostly adversarial: each one feeds it a specific way the
contract in interface/demand_schema.md can be broken, and asserts it is
REJECTED rather than crashing or silently passing.

Run:
    python -m pytest tests/ -v
    python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "interface"))

from validate_lda_output import validate_proportions, VALID_CATEGORIES  # noqa: E402


def write_json(payload, raw=None):
    """Write a temp JSON file and return its path. `raw` bypasses json.dump."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        if raw is not None:
            f.write(raw)
        else:
            json.dump(payload, f)
    return path


class TempFileTestCase(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    def make(self, payload=None, raw=None):
        path = write_json(payload, raw)
        self._paths.append(path)
        return path


class TestAcceptsValidInput(TempFileTestCase):
    def test_published_proportions_are_accepted(self):
        """The exact distribution behind the reported results must validate."""
        path = self.make({
            "dispatch_proportions": {
                "ambulance": 0.6436,
                "cargo_truck": 0.1679,
                "first_responder": 0.1885,
            }
        })
        self.assertTrue(validate_proportions(path))

    def test_real_project_file_is_accepted(self):
        """Guards against a schema change that would orphan the committed file."""
        real = os.path.join(REPO_ROOT, "sumo_simulation", "demand",
                            "real_demand_proportions.json")
        self.assertTrue(os.path.exists(real), f"missing fixture: {real}")
        self.assertTrue(validate_proportions(real))

    def test_rounding_drift_within_tolerance_is_accepted(self):
        """4-decimal rounding must not trip the sum check."""
        path = self.make({
            "dispatch_proportions": {
                "ambulance": 0.6436, "cargo_truck": 0.1679, "first_responder": 0.1880
            }
        })
        self.assertTrue(validate_proportions(path))


class TestRejectsMalformedInput(TempFileTestCase):
    def test_missing_file(self):
        self.assertFalse(validate_proportions(
            os.path.join(REPO_ROOT, "definitely_not_a_real_file.json")))

    def test_unparseable_json(self):
        self.assertFalse(validate_proportions(self.make(raw="{ not json ,,,")))

    def test_top_level_not_an_object(self):
        self.assertFalse(validate_proportions(self.make(["a", "b"])))

    def test_missing_dispatch_proportions_key(self):
        self.assertFalse(validate_proportions(self.make({"raw_document_counts": {}})))

    def test_dispatch_proportions_is_null(self):
        """Regression: this used to raise AttributeError instead of returning False."""
        self.assertFalse(validate_proportions(self.make({"dispatch_proportions": None})))

    def test_dispatch_proportions_is_a_list(self):
        """Regression: this used to raise AttributeError instead of returning False."""
        self.assertFalse(validate_proportions(
            self.make({"dispatch_proportions": ["ambulance"]})))

    def test_dispatch_proportions_is_empty(self):
        self.assertFalse(validate_proportions(self.make({"dispatch_proportions": {}})))

    def test_unknown_category_is_rejected(self):
        """Placeholder labels from earlier drafts must never be accepted."""
        for bogus in ("medical_help", "medical_aid", "food_shelter", "search_rescue",
                      "water", "food", "shelter", "terrorism_or_other_violence",
                      "road_damage_signal"):
            with self.subTest(category=bogus):
                path = self.make({"dispatch_proportions": {"ambulance": 0.5, bogus: 0.5}})
                self.assertFalse(validate_proportions(path),
                                 f"validator accepted bogus category {bogus!r}")

    def test_proportions_not_summing_to_one(self):
        self.assertFalse(validate_proportions(self.make({
            "dispatch_proportions": {
                "ambulance": 0.5, "cargo_truck": 0.2, "first_responder": 0.1}})))

    def test_negative_proportion_is_rejected(self):
        """
        Regression for a real defect: {1.5, -0.3, -0.2} sums to exactly 1.0 and
        was ACCEPTED by the original validator. A negative share would reach
        generate_demand.py as round(150 * -0.3) = -45, which max(1, ...) turns
        into a single vehicle -- silently distorting the whole fleet.
        """
        self.assertFalse(validate_proportions(self.make({
            "dispatch_proportions": {
                "ambulance": 1.5, "cargo_truck": -0.3, "first_responder": -0.2}})))

    def test_proportion_above_one_is_rejected(self):
        self.assertFalse(validate_proportions(self.make({
            "dispatch_proportions": {
                "ambulance": 2.0, "cargo_truck": -0.5, "first_responder": -0.5}})))

    def test_string_valued_proportions_are_rejected(self):
        """Regression: this used to raise TypeError inside sum()."""
        self.assertFalse(validate_proportions(self.make({
            "dispatch_proportions": {
                "ambulance": "0.6436", "cargo_truck": "0.1679",
                "first_responder": "0.1885"}})))

    def test_boolean_valued_proportions_are_rejected(self):
        """bool is a subclass of int; True must not slip through as 1.0."""
        self.assertFalse(validate_proportions(self.make({
            "dispatch_proportions": {
                "ambulance": True, "cargo_truck": False, "first_responder": False}})))

    def test_partial_category_set_is_rejected(self):
        """
        A single-category file sums to 1.0 and passes every per-key check, but
        would send all 150 vehicles to one category. Reject it by default.
        """
        self.assertFalse(validate_proportions(self.make({
            "dispatch_proportions": {"ambulance": 1.0}})))

    def test_partial_category_set_allowed_when_opted_in(self):
        self.assertTrue(validate_proportions(
            self.make({"dispatch_proportions": {"ambulance": 1.0}}),
            require_all_categories=False))


class TestCategoryContract(unittest.TestCase):
    def test_valid_categories_match_the_sumo_vtypes(self):
        """
        The validator's allow-list must equal the vType ids actually defined in
        vtypes.add.xml -- otherwise it would pass demand the simulation cannot
        dispatch.
        """
        import xml.etree.ElementTree as ET
        vtypes_path = os.path.join(REPO_ROOT, "sumo_simulation", "vehicles",
                                   "vtypes.add.xml")
        declared = {vt.attrib["id"]
                    for vt in ET.parse(vtypes_path).getroot().findall("vType")}
        self.assertEqual(set(VALID_CATEGORIES), declared)


if __name__ == "__main__":
    unittest.main(verbosity=2)
