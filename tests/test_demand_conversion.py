"""
Unit tests for the demand-conversion logic.

Two layers are covered:

1. compute_demand_proportions.compute_document_proportions — the confusion
   matrix -> dispatch-category aggregation. The key test reconstructs a
   confusion matrix consistent with the published corpus (10,910 documents,
   4,478 actionable) and asserts the function reproduces the committed
   real_demand_proportions.json byte-for-byte in its numeric content.

2. The proportion -> vehicle-count apportionment used by generate_demand.py.
   generate_demand.py cannot be imported here because it imports sumolib at
   module scope (sumolib ships with SUMO, not pip), so the arithmetic is
   restated and pinned against the committed route file instead.
"""

import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMO_DIR = os.path.join(REPO_ROOT, "sumo_simulation")
sys.path.insert(0, os.path.join(SUMO_DIR, "scripts"))

from compute_demand_proportions import (  # noqa: E402
    CLASS_TO_DISPATCH,
    DISPATCHABLE_CATEGORIES,
    compute_document_proportions,
)

# Published, independently verified document counts (see reports/).
PUBLISHED = {
    "total_documents": 10910,
    "actionable_documents": 4478,
    "non_actionable_documents": 6432,
    "counts": {"ambulance": 2882, "cargo_truck": 752, "first_responder": 844},
    "proportions": {"ambulance": 0.6436, "cargo_truck": 0.1679, "first_responder": 0.1885},
}


def write_alignment(tmp_path, predicted_totals):
    """
    Build a minimal alignment_results.json whose confusion matrix sums to the
    given per-predicted-class totals. Ground-truth rows are irrelevant to the
    aggregation (it sums down columns), so a single row is enough.
    """
    payload = {"confusion_matrix": {"some_ground_truth_class": dict(predicted_totals)}}
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return tmp_path


class TestDocumentAggregation(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.join(REPO_ROOT, "tests", "_tmp_alignment.json")

    def tearDown(self):
        if os.path.exists(self.tmp):
            os.unlink(self.tmp)

    def test_reproduces_published_proportions(self):
        """
        A confusion matrix carrying the published class counts must yield the
        published proportions. This pins the conversion arithmetic to the
        numbers the paper reports.
        """
        write_alignment(self.tmp, {
            "injured_or_dead_people": 2882,        # -> ambulance
            "missing_and_found_people": 844,       # -> first_responder
            "displaced_and_evacuations": 752,      # -> cargo_truck
            "requests_or_needs": 0,                # -> cargo_truck (0 topics)
            "sympathy_and_support": 6432,          # -> no_dispatch
        })
        props, counts, no_dispatch, total, _, descoped = compute_document_proportions(
            self.tmp, CLASS_TO_DISPATCH)

        self.assertEqual(counts, PUBLISHED["counts"])
        self.assertEqual(props, PUBLISHED["proportions"])
        self.assertEqual(total, PUBLISHED["total_documents"])
        self.assertEqual(no_dispatch, PUBLISHED["non_actionable_documents"])
        self.assertEqual(sum(counts.values()), PUBLISHED["actionable_documents"])
        self.assertEqual(descoped, {})

    def test_matches_committed_output_file(self):
        """The recomputed values must equal what is committed on disk."""
        write_alignment(self.tmp, {
            "injured_or_dead_people": 2882,
            "missing_and_found_people": 844,
            "displaced_and_evacuations": 752,
            "sympathy_and_support": 6432,
        })
        props, counts, no_dispatch, total, _, _ = compute_document_proportions(
            self.tmp, CLASS_TO_DISPATCH)

        committed_path = os.path.join(SUMO_DIR, "demand", "real_demand_proportions.json")
        with open(committed_path, encoding="utf-8") as f:
            committed = json.load(f)

        self.assertEqual(props, committed["dispatch_proportions"])
        self.assertEqual(counts, committed["raw_document_counts"])
        self.assertEqual(total, committed["_meta"]["total_documents"])
        self.assertEqual(no_dispatch, committed["_meta"]["non_actionable_documents"])
        self.assertEqual(sum(counts.values()),
                         committed["_meta"]["actionable_documents"])

    def test_proportions_sum_to_one(self):
        write_alignment(self.tmp, {
            "injured_or_dead_people": 2882,
            "missing_and_found_people": 844,
            "displaced_and_evacuations": 752,
        })
        props, *_ = compute_document_proportions(self.tmp, CLASS_TO_DISPATCH)
        self.assertAlmostEqual(sum(props.values()), 1.0, places=3)

    def test_both_classes_fold_into_cargo_truck(self):
        """displaced_and_evacuations and requests_or_needs share one vehicle type."""
        write_alignment(self.tmp, {
            "displaced_and_evacuations": 300,
            "requests_or_needs": 200,
            "injured_or_dead_people": 500,
        })
        _, counts, *_ = compute_document_proportions(self.tmp, CLASS_TO_DISPATCH)
        self.assertEqual(counts["cargo_truck"], 500)

    def test_descoped_class_never_enters_dispatch_proportions(self):
        """
        Regression for a latent defect: infrastructure_and_utilities_damage maps
        to 'road_damage_signal', which the original code treated as actionable.
        Any non-zero count there would have emitted a category no SUMO vType
        implements, producing a file that fails schema validation.
        """
        write_alignment(self.tmp, {
            "injured_or_dead_people": 900,
            "infrastructure_and_utilities_damage": 100,
        })
        props, counts, no_dispatch, total, _, descoped = compute_document_proportions(
            self.tmp, CLASS_TO_DISPATCH)

        self.assertNotIn("road_damage_signal", props)
        self.assertNotIn("road_damage_signal", counts)
        self.assertEqual(descoped, {"road_damage_signal": 100})
        # The descoped documents are still counted in the corpus total, so the
        # denominator stays honest.
        self.assertEqual(total, 1000)
        self.assertEqual(sum(counts.values()), 900)

    def test_emitted_categories_are_all_dispatchable(self):
        write_alignment(self.tmp, {
            "injured_or_dead_people": 10,
            "missing_and_found_people": 10,
            "displaced_and_evacuations": 10,
            "infrastructure_and_utilities_damage": 10,
            "not_humanitarian": 10,
        })
        props, *_ = compute_document_proportions(self.tmp, CLASS_TO_DISPATCH)
        for category in props:
            self.assertIn(category, DISPATCHABLE_CATEGORIES)

    def test_unmapped_class_raises_rather_than_silently_dropping(self):
        """
        The original code used mapping.get(cls, 'no_dispatch'), so a class the
        NMF pipeline renamed would have been silently discarded, shrinking the
        actionable pool with no warning.
        """
        write_alignment(self.tmp, {"a_brand_new_class": 500,
                                   "injured_or_dead_people": 500})
        with self.assertRaises(KeyError):
            compute_document_proportions(self.tmp, CLASS_TO_DISPATCH)

    def test_missing_alignment_file_raises_actionable_error(self):
        missing = os.path.join(REPO_ROOT, "tests", "_does_not_exist.json")
        with self.assertRaises(FileNotFoundError) as ctx:
            compute_document_proportions(missing, CLASS_TO_DISPATCH)
        self.assertIn("lda_pipeline", str(ctx.exception))

    def test_missing_confusion_matrix_key_raises(self):
        with open(self.tmp, "w", encoding="utf-8") as f:
            json.dump({"something_else": {}}, f)
        with self.assertRaises(KeyError):
            compute_document_proportions(self.tmp, CLASS_TO_DISPATCH)

    def test_all_zero_counts_yield_empty_proportions_not_zero_division(self):
        write_alignment(self.tmp, {"sympathy_and_support": 100})
        props, counts, no_dispatch, total, *_ = compute_document_proportions(
            self.tmp, CLASS_TO_DISPATCH)
        self.assertEqual(props, {})
        self.assertEqual(counts, {})
        self.assertEqual(no_dispatch, 100)
        self.assertEqual(total, 100)


class TestMappingConsistency(unittest.TestCase):
    def test_matches_interface_mapping_file(self):
        """
        compute_demand_proportions.CLASS_TO_DISPATCH and
        interface/dispatch_category_mapping.json must not drift apart.
        """
        path = os.path.join(REPO_ROOT, "interface", "dispatch_category_mapping.json")
        with open(path, encoding="utf-8") as f:
            interface_map = json.load(f)["mapping"]
        self.assertEqual(CLASS_TO_DISPATCH, interface_map)

    def test_covers_all_twelve_canonical_classes(self):
        self.assertEqual(len(CLASS_TO_DISPATCH), 12)

    def test_topic_vehicle_map_agrees_on_dispatchable_classes(self):
        """
        vehicles/topic_vehicle_map.json is the SUMO-side view of the same
        mapping; its dispatchable entries must agree with the interface mapping.
        """
        path = os.path.join(SUMO_DIR, "vehicles", "topic_vehicle_map.json")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)

        for entry in doc["mappings"]:
            cls = entry["mapped_ground_truth_class"]
            with self.subTest(cls=cls):
                self.assertEqual(CLASS_TO_DISPATCH[cls], entry["dispatch_category"])
                self.assertEqual(entry["dispatch_category"], entry["sumo_vtype"])

        for entry in doc["no_dispatch_classes"]:
            cls = entry["mapped_ground_truth_class"]
            with self.subTest(cls=cls):
                self.assertNotIn(CLASS_TO_DISPATCH[cls], DISPATCHABLE_CATEGORIES)

    def test_topic_id_assignments_match_the_verified_breakdown(self):
        """
        Pins the topic->class counts that the demand model rests on. 30 NMF
        topics; only the four dispatchable classes carry topic ids here.
        """
        path = os.path.join(SUMO_DIR, "vehicles", "topic_vehicle_map.json")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        by_class = {e["mapped_ground_truth_class"]: e["topic_ids"]
                    for e in doc["mappings"]}

        self.assertEqual(sorted(by_class["injured_or_dead_people"]), [7, 21])
        self.assertEqual(sorted(by_class["missing_and_found_people"]), [20, 27])
        self.assertEqual(sorted(by_class["displaced_and_evacuations"]), [8, 11])
        self.assertEqual(by_class["requests_or_needs"], [])

        all_ids = [i for ids in by_class.values() for i in ids]
        self.assertEqual(len(all_ids), len(set(all_ids)), "topic id assigned twice")
        for i in all_ids:
            self.assertTrue(0 <= i < 30, f"topic id {i} outside the k=30 model")


class TestVehicleApportionment(unittest.TestCase):
    """
    generate_demand.py sizes each category as max(1, round(total * proportion)),
    independently per category. That is what produced the committed fleet, so it
    is pinned here rather than replaced.
    """

    @staticmethod
    def apportion(proportions, total_vehicles):
        return {k: max(1, round(total_vehicles * v)) for k, v in proportions.items()}

    def test_published_split_is_97_25_28(self):
        counts = self.apportion(PUBLISHED["proportions"], 150)
        self.assertEqual(counts, {"ambulance": 97, "cargo_truck": 25,
                                  "first_responder": 28})
        self.assertEqual(sum(counts.values()), 150)

    def test_matches_committed_route_file(self):
        """The arithmetic must agree with the route file the simulation consumed."""
        route_file = os.path.join(SUMO_DIR, "demand", "relief_vehicles.rou.xml")
        actual = Counter(t.attrib["type"]
                         for t in ET.parse(route_file).getroot().findall("trip"))
        self.assertEqual(dict(actual), self.apportion(PUBLISHED["proportions"], 150))

    def test_routed_file_preserves_the_same_fleet(self):
        """duarouter must not have dropped any vehicle."""
        raw = Counter(t.attrib["type"] for t in ET.parse(
            os.path.join(SUMO_DIR, "demand", "relief_vehicles.rou.xml")
        ).getroot().findall("trip"))
        routed = Counter(v.attrib["type"] for v in ET.parse(
            os.path.join(SUMO_DIR, "demand", "relief_vehicles_routed.rou.xml")
        ).getroot().findall("vehicle"))
        self.assertEqual(raw, routed)

    def test_independent_rounding_can_miss_the_requested_total(self):
        """
        Documents the known limitation the new warning in generate_demand.py
        reports: per-category rounding does not have to sum to --total-vehicles.
        """
        counts = self.apportion(
            {"ambulance": 0.3333, "cargo_truck": 0.3333, "first_responder": 0.3334}, 100)
        self.assertNotEqual(sum(counts.values()), 100)
        self.assertEqual(sum(counts.values()), 99)

    def test_tiny_share_still_dispatches_one_vehicle(self):
        counts = self.apportion(
            {"ambulance": 0.999, "cargo_truck": 0.0005, "first_responder": 0.0005}, 150)
        self.assertEqual(counts["cargo_truck"], 1)
        self.assertEqual(counts["first_responder"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
