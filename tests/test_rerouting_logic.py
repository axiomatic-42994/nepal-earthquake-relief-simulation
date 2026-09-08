"""
Unit tests for the TraCI control-loop decision logic in run_simulation.py.

run_simulation.py imports `traci`, which ships with SUMO rather than pip, so a
minimal stub is installed in sys.modules before the import. Only module-level
import needs to succeed — every test here exercises the pure predicates
(`route_is_blocked`, `is_due`, `has_fleet_capacity`), which make no TraCI calls.

Also covered:
  * `resolve_sumo_binary` error handling when SUMO_HOME is unset or wrong
  * the damage schedule's own invariants (blocked-edge sets, event ordering)
  * the phantom-arrival defect, asserted directly against the committed output
"""

import json
import os
import sys
import types
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMO_DIR = os.path.join(REPO_ROOT, "sumo_simulation")
sys.path.insert(0, os.path.join(SUMO_DIR, "scripts"))

# --- install a stub `traci` so run_simulation can be imported without SUMO ----
if "traci" not in sys.modules:
    stub = types.ModuleType("traci")

    class _TraCIException(Exception):
        pass

    stub.TraCIException = _TraCIException
    stub.constants = types.SimpleNamespace(REMOVE_PARKING=1)
    sys.modules["traci"] = stub

from run_simulation import (  # noqa: E402
    has_fleet_capacity,
    is_due,
    load_damage_schedule,
    resolve_sumo_binary,
    route_is_blocked,
)

DAMAGE_FILE = os.path.join(SUMO_DIR, "damage", "road_damage_events.json")
MAX_FLEET = {"ambulance": 8, "first_responder": 8, "cargo_truck": 8}


class TestRouteIsBlocked(unittest.TestCase):
    ROUTE = ["e0", "e1", "e2", "e3", "e4"]

    def test_no_blockage_anywhere(self):
        self.assertFalse(route_is_blocked(self.ROUTE, 0, set()))

    def test_blockage_ahead_is_detected(self):
        self.assertTrue(route_is_blocked(self.ROUTE, 1, {"e3"}))

    def test_blockage_already_passed_is_ignored(self):
        """A vehicle past the rubble must not be rerouted for it."""
        self.assertFalse(route_is_blocked(self.ROUTE, 3, {"e0", "e1"}))

    def test_blockage_on_the_current_edge_counts_as_blocked(self):
        """
        The slice starts AT route_index, so the vehicle's current edge is
        included. This is the behaviour that makes an already-stuck vehicle
        reroute-eligible — and, when no detour exists, get abandoned.
        """
        self.assertTrue(route_is_blocked(self.ROUTE, 2, {"e2"}))

    def test_blockage_on_the_final_edge_is_detected(self):
        self.assertTrue(route_is_blocked(self.ROUTE, 0, {"e4"}))

    def test_index_at_end_of_route(self):
        self.assertFalse(route_is_blocked(self.ROUTE, len(self.ROUTE), {"e4"}))

    def test_empty_route(self):
        self.assertFalse(route_is_blocked([], 0, {"e0"}))

    def test_partially_blocked_edges_are_not_in_the_blocked_set(self):
        """
        Partially blocked edges stay passable at 2.5 m/s and must never trigger
        a reroute. The contract is that the caller only ever puts fully blocked
        edges into the set; assert the two sets are disjoint in the real
        schedule so that contract cannot silently rot.
        """
        events = load_damage_schedule(DAMAGE_FILE)
        full = {e for ev in events for e in ev.get("fully_blocked_edges", [])}
        partial = {e for ev in events for e in ev.get("partially_blocked_edges", [])}
        self.assertTrue(full.isdisjoint(partial),
                        f"edge listed as both fully and partially blocked: "
                        f"{full & partial}")
        for edge in partial:
            self.assertFalse(route_is_blocked(["a", edge, "b"], 0, full))


class TestDispatchQueueAdmission(unittest.TestCase):
    def test_request_not_yet_due(self):
        self.assertFalse(is_due({"depart": 100.0}, 99.0))

    def test_request_due_exactly_now(self):
        self.assertTrue(is_due({"depart": 100.0}, 100.0))

    def test_request_overdue(self):
        self.assertTrue(is_due({"depart": 100.0}, 250.0))

    def test_capacity_available(self):
        self.assertTrue(has_fleet_capacity("ambulance", {"ambulance": 7}, MAX_FLEET))

    def test_capacity_exhausted(self):
        self.assertFalse(has_fleet_capacity("ambulance", {"ambulance": 8}, MAX_FLEET))

    def test_capacity_over_subscribed(self):
        """Defensive: a count above the cap must still read as 'no capacity'."""
        self.assertFalse(has_fleet_capacity("ambulance", {"ambulance": 12}, MAX_FLEET))

    def test_capacity_is_per_type_not_global(self):
        """
        Edge case from the improvement mandate: every ambulance busy must not
        block a cargo truck.
        """
        counts = {"ambulance": 8, "first_responder": 8, "cargo_truck": 0}
        self.assertFalse(has_fleet_capacity("ambulance", counts, MAX_FLEET))
        self.assertFalse(has_fleet_capacity("first_responder", counts, MAX_FLEET))
        self.assertTrue(has_fleet_capacity("cargo_truck", counts, MAX_FLEET))

    def test_all_types_saturated_blocks_everything(self):
        counts = dict.fromkeys(MAX_FLEET, 8)
        for vtype in MAX_FLEET:
            self.assertFalse(has_fleet_capacity(vtype, counts, MAX_FLEET))

    def test_unseen_type_uses_the_default_cap(self):
        self.assertTrue(has_fleet_capacity("helicopter", {}, MAX_FLEET))
        self.assertFalse(
            has_fleet_capacity("helicopter", {"helicopter": 100}, MAX_FLEET))

    def test_type_missing_from_counts_is_treated_as_idle(self):
        self.assertTrue(has_fleet_capacity("cargo_truck", {}, MAX_FLEET))


class TestSumoBinaryResolution(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("SUMO_HOME")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("SUMO_HOME", None)
        else:
            os.environ["SUMO_HOME"] = self._saved

    def test_unset_sumo_home_raises_actionable_error(self):
        os.environ.pop("SUMO_HOME", None)
        with self.assertRaises(SystemExit) as ctx:
            resolve_sumo_binary(use_gui=False)
        self.assertIn("SUMO_HOME", str(ctx.exception))

    def test_wrong_sumo_home_names_the_missing_binary(self):
        os.environ["SUMO_HOME"] = os.path.join(REPO_ROOT, "not_a_sumo_install")
        with self.assertRaises(SystemExit) as ctx:
            resolve_sumo_binary(use_gui=False)
        self.assertIn("not_a_sumo_install", str(ctx.exception))


class TestDamageSchedule(unittest.TestCase):
    def setUp(self):
        self.events = load_damage_schedule(DAMAGE_FILE)
        net = os.path.join(SUMO_DIR, "network", "kathmandu.net.xml")
        self.net_edges = {
            e.attrib["id"]
            for e in ET.parse(net).getroot().findall("edge")
            if e.attrib.get("function") is None
        }

    def test_schedule_is_non_empty(self):
        self.assertEqual(len(self.events), 3)

    def test_event_ids_are_unique(self):
        ids = [e["event_id"] for e in self.events]
        self.assertEqual(len(ids), len(set(ids)))

    def test_events_are_in_chronological_order(self):
        """The control loop assumes nothing here, but a report that quotes
        'damage at t=300/1800/3600' does."""
        times = [e["timestamp_seconds"] for e in self.events]
        self.assertEqual(times, sorted(times))
        self.assertEqual(times, [300, 1800, 3600])

    def test_all_events_fire_within_the_simulation_horizon(self):
        for e in self.events:
            self.assertLess(e["timestamp_seconds"], 5400,
                            f"{e['event_id']} fires after the run ends")

    def test_every_damaged_edge_exists_in_the_network(self):
        """
        A typo here would be silently swallowed: setMaxSpeed on an unknown edge
        raises TraCIException, which the loop catches and discards, so the
        blockage would simply never happen.
        """
        for e in self.events:
            for edge in e.get("fully_blocked_edges", []) + e.get("partially_blocked_edges", []):
                with self.subTest(edge=edge):
                    self.assertIn(edge, self.net_edges)

    def test_no_edge_is_damaged_twice(self):
        seen = []
        for e in self.events:
            seen += e.get("fully_blocked_edges", []) + e.get("partially_blocked_edges", [])
        self.assertEqual(len(seen), len(set(seen)))

    def test_damage_counts_match_the_documented_schedule(self):
        full = sum(len(e.get("fully_blocked_edges", [])) for e in self.events)
        partial = sum(len(e.get("partially_blocked_edges", [])) for e in self.events)
        self.assertEqual(full, 7)
        self.assertEqual(partial, 6)
        with open(DAMAGE_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["seed"], 2015)


class TestPhantomArrivalDefect(unittest.TestCase):
    """
    Locks in the measured defect described in run_simulation.py, so that if the
    UNDELIVERABLE-removal accounting is ever changed these tests fail loudly and
    every reported dynamic-mode number gets re-derived rather than silently drift.
    """

    DISPATCH_TYPES = ("ambulance", "first_responder", "cargo_truck")

    @staticmethod
    def _destinations():
        path = os.path.join(SUMO_DIR, "demand", "relief_vehicles_routed.rou.xml")
        out = {}
        for v in ET.parse(path).getroot().findall("vehicle"):
            r = v.find("route")
            if r is not None:
                out[v.attrib["id"]] = r.attrib["edges"].split()[-1]
        return out

    def _split(self, tripinfo_path):
        dest = self._destinations()
        trips = [t for t in ET.parse(tripinfo_path).getroot().findall("tripinfo")
                 if t.attrib.get("vType", "").split("@")[0] in self.DISPATCH_TYPES]
        delivered = [t for t in trips
                     if t.attrib.get("arrivalLane", "").rsplit("_", 1)[0] == dest.get(t.attrib["id"])]
        phantom = [t for t in trips if t not in delivered]
        return trips, delivered, phantom

    def test_static_runs_contain_no_phantom_arrivals(self):
        """The control: static mode performs no removals, so every record is real."""
        for seed in (42, 101, 202, 303, 404):
            with self.subTest(seed=seed):
                _, _, phantom = self._split(
                    os.path.join(SUMO_DIR, "output", f"tripinfo_static_{seed}.xml"))
                self.assertEqual(phantom, [])

    def test_dynamic_runs_contain_exactly_ten_phantom_arrivals(self):
        for seed in (42, 101, 202, 303, 404):
            with self.subTest(seed=seed):
                trips, delivered, phantom = self._split(
                    os.path.join(SUMO_DIR, "output", f"tripinfo_dynamic_{seed}.xml"))
                self.assertEqual(len(trips), 145)
                self.assertEqual(len(delivered), 135)
                self.assertEqual(len(phantom), 10)

    def test_phantom_arrivals_clear_the_fulfilment_threshold(self):
        """This is why they inflate the metric: they all look 'on time'."""
        _, _, phantom = self._split(
            os.path.join(SUMO_DIR, "output", "tripinfo_dynamic_42.xml"))
        for t in phantom:
            with self.subTest(vehicle=t.attrib["id"]):
                self.assertLessEqual(float(t.attrib["duration"]), 300.0)

    def test_both_modes_deliver_the_same_number_of_vehicles(self):
        """
        The headline '+10 vehicles delivered' claim does not survive the
        delivery check: seed 42 delivers 135 either way.
        """
        _, static_delivered, _ = self._split(
            os.path.join(SUMO_DIR, "output", "tripinfo_static_42.xml"))
        _, dynamic_delivered, _ = self._split(
            os.path.join(SUMO_DIR, "output", "tripinfo_dynamic_42.xml"))
        self.assertEqual(len(static_delivered), len(dynamic_delivered))


if __name__ == "__main__":
    unittest.main(verbosity=2)
