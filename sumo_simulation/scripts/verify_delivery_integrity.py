"""
verify_delivery_integrity.py — Delivery-verified evaluation of the relief simulation.

WHY THIS EXISTS
---------------
`evaluate_results.py` treats every <tripinfo> record as a completed delivery.
That assumption does not hold in dynamic mode. When the TraCI controller in
run_simulation.py gives up on a vehicle it calls:

    traci.vehicle.remove(veh_id, traci.constants.REMOVE_PARKING)

SUMO still emits a <tripinfo> record for a vehicle removed this way, with
`arrival` set to the removal time. So an abandoned mission is written out
looking exactly like a fast, successful one — typically `duration="1.00"` with a
routeLength equal to the depot edge alone.

Consequences for the headline metrics, all of them one-sided in favour of
dynamic mode (static mode performs no removals at all):

  * abandoned vehicles are counted as `completed`
  * their ~1s duration clears the 300s threshold, so they count as `fulfilled`
  * their ~1s duration and 0s waiting time pull both means sharply down

THE CHECK
---------
This script ignores the log entirely and asks a structural question of the raw
output: did the vehicle's tripinfo `arrivalLane` sit on the last edge of the
route it was actually given in the routed demand file?

  delivered  <=>  edge_of(tripinfo.arrivalLane) == route.edges[-1]

That is a property of the committed artefacts alone, so it can be re-derived by
anyone without rerunning SUMO. It also self-controls: in static mode every
tripinfo record passes the check, which is what you would expect if the check
itself were sound.

USAGE
-----
    python verify_delivery_integrity.py                  # N=5 seeded replication
    python verify_delivery_integrity.py --seeds 42       # a single seed
    python verify_delivery_integrity.py --single-run     # unseeded tripinfo_{mode}.xml
    python verify_delivery_integrity.py --json out.json  # also write machine-readable output

This script only READS simulation output. It never rewrites the published
results, and it is not a substitute for evaluate_results.py — it is the honesty
check that sits beside it.
"""

import argparse
import json
import os
import xml.etree.ElementTree as ET

import numpy as np

DISPATCH_TYPES = ("ambulance", "first_responder", "cargo_truck")
DEFAULT_SEEDS = (42, 101, 202, 303, 404)
FULFILMENT_THRESHOLD_S = 300.0

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def base_vtype(raw):
    """
    Strip SUMO's singular-vType suffix.

    SUMO renames a vehicle's type to 'origType@vehID' when that vehicle acquires
    per-vehicle parameters, so 'cargo_truck@cargo_truck_114' is still a cargo truck.
    """
    return raw.split("@")[0]


def edge_of(lane_id):
    """'123456#0_1' -> '123456#0'. SUMO lane ids are '<edge>_<index>'."""
    return lane_id.rsplit("_", 1)[0] if lane_id else ""


def load_intended_destinations(routed_route_file):
    """Map vehicle id -> final edge of the route it was dispatched with."""
    if not os.path.exists(routed_route_file):
        raise FileNotFoundError(
            f"Routed demand file not found: {routed_route_file}\n"
            "It is produced by duarouter; see sumo_simulation/README.md step 2."
        )

    destinations = {}
    for veh in ET.parse(routed_route_file).getroot().findall("vehicle"):
        route = veh.find("route")
        if route is None:
            continue
        edges = route.attrib.get("edges", "").split()
        if edges:
            destinations[veh.attrib["id"]] = edges[-1]

    if not destinations:
        raise ValueError(
            f"No <vehicle> elements with an embedded <route> found in "
            f"{routed_route_file}. Was duarouter run on the raw trips file?"
        )
    return destinations


def analyse_run(tripinfo_file, destinations, threshold=FULFILMENT_THRESHOLD_S):
    """
    Compare the naive (tripinfo-record) view against the delivery-verified view
    for one simulation output file.
    """
    if not os.path.exists(tripinfo_file):
        raise FileNotFoundError(f"Tripinfo file not found: {tripinfo_file}")

    dispatched = len(destinations)
    trips = [t for t in ET.parse(tripinfo_file).getroot().findall("tripinfo")
             if base_vtype(t.attrib.get("vType", "")) in DISPATCH_TYPES]

    delivered, phantom = [], []
    for t in trips:
        intended = destinations.get(t.attrib["id"])
        if intended is not None and edge_of(t.attrib.get("arrivalLane", "")) == intended:
            delivered.append(t)
        else:
            phantom.append(t)

    def summarise(records):
        if not records:
            return {"count": 0, "fulfilled": 0, "fulfilment_pct": 0.0,
                    "avg_duration_s": 0.0, "avg_waiting_s": 0.0}
        durations = [float(r.attrib["duration"]) for r in records]
        waits = [float(r.attrib["waitingTime"]) for r in records]
        fulfilled = sum(1 for d in durations if d <= threshold)
        return {
            "count": len(records),
            "fulfilled": fulfilled,
            "fulfilment_pct": fulfilled / dispatched * 100.0,
            "avg_duration_s": float(np.mean(durations)),
            "avg_waiting_s": float(np.mean(waits)),
        }

    return {
        "tripinfo_file": os.path.basename(tripinfo_file),
        "dispatched": dispatched,
        "as_reported": summarise(trips),
        "delivery_verified": summarise(delivered),
        "phantom_arrivals": len(phantom),
        "phantom_ids": sorted(t.attrib["id"] for t in phantom),
        "stranded_as_reported": dispatched - len(trips),
        "stranded_verified": dispatched - len(delivered),
    }


def aggregate(runs, key_path):
    vals = [run[key_path[0]][key_path[1]] if len(key_path) == 2 else run[key_path[0]]
            for run in runs]
    return float(np.mean(vals)), float(np.std(vals))


def fmt(mean, std):
    return f"{mean:8.2f} (+/- {std:5.2f})"


def report(results_by_mode):
    print("=" * 78)
    print(" DELIVERY-VERIFIED EVALUATION")
    print(" delivered := tripinfo arrivalLane sits on the route's final edge")
    print("=" * 78)

    for mode, runs in results_by_mode.items():
        n = len(runs)
        print(f"\n--- {mode.upper()} MODE (N={n}) ---")
        print(f"  {'metric':<28}{'as reported':>22}{'delivery-verified':>24}")
        rows = [
            ("delivered vehicles", ("as_reported", "count"), ("delivery_verified", "count")),
            ("stranded vehicles", ("stranded_as_reported",), ("stranded_verified",)),
            ("fulfilment %", ("as_reported", "fulfilment_pct"), ("delivery_verified", "fulfilment_pct")),
            ("avg duration (s)", ("as_reported", "avg_duration_s"), ("delivery_verified", "avg_duration_s")),
            ("avg waiting (s)", ("as_reported", "avg_waiting_s"), ("delivery_verified", "avg_waiting_s")),
        ]
        for label, rep_key, ver_key in rows:
            print(f"  {label:<28}{fmt(*aggregate(runs, rep_key)):>22}"
                  f"{fmt(*aggregate(runs, ver_key)):>24}")

        phantom_mean, phantom_std = aggregate(runs, ("phantom_arrivals",))
        print(f"  {'phantom arrivals':<28}{fmt(phantom_mean, phantom_std):>22}"
              f"{'(abandoned, scored as OK)':>24}")

    if len(results_by_mode) == 2 and "static" in results_by_mode and "dynamic" in results_by_mode:
        print("\n" + "-" * 78)
        print(" DYNAMIC vs STATIC - headline deltas")
        print("-" * 78)
        print(f"  {'delta':<28}{'as reported':>22}{'delivery-verified':>24}")
        for label, key in [("fulfilment gain (pp)", "fulfilment_pct"),
                           ("duration saved (s)", "avg_duration_s"),
                           ("waiting saved (s)", "avg_waiting_s")]:
            out = []
            for view in ("as_reported", "delivery_verified"):
                s = aggregate(results_by_mode["static"], (view, key))[0]
                d = aggregate(results_by_mode["dynamic"], (view, key))[0]
                out.append(d - s if key == "fulfilment_pct" else s - d)
            print(f"  {label:<28}{out[0]:>+22.2f}{out[1]:>+24.2f}")

        for label, key in [("delivered vehicles", "count")]:
            out = []
            for view in ("as_reported", "delivery_verified"):
                s = aggregate(results_by_mode["static"], (view, key))[0]
                d = aggregate(results_by_mode["dynamic"], (view, key))[0]
                out.append(d - s)
            print(f"  {label:<28}{out[0]:>+22.2f}{out[1]:>+24.2f}")


def main():
    parser = argparse.ArgumentParser(
        description="Delivery-verified evaluation of relief simulation output")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS),
                        help="Replication seeds to evaluate (default: 42 101 202 303 404)")
    parser.add_argument("--single-run", action="store_true",
                        help="Evaluate the unseeded tripinfo_{mode}.xml pair instead")
    parser.add_argument("--routed-demand",
                        default=os.path.join(BASE_DIR, "demand", "relief_vehicles_routed.rou.xml"),
                        help="Routed relief demand file defining each vehicle's destination")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="Also write the full per-run results to this JSON path")
    args = parser.parse_args()

    destinations = load_intended_destinations(args.routed_demand)
    print(f"Intended destinations loaded for {len(destinations)} dispatched vehicles "
          f"from {os.path.basename(args.routed_demand)}\n")

    results = {"static": [], "dynamic": []}
    for mode in ("static", "dynamic"):
        if args.single_run:
            files = [os.path.join(BASE_DIR, "output", f"tripinfo_{mode}.xml")]
        else:
            files = [os.path.join(BASE_DIR, "output", f"tripinfo_{mode}_{s}.xml")
                     for s in args.seeds]
        for f in files:
            results[mode].append(analyse_run(f, destinations))

    report(results)

    phantoms = sorted({vid for run in results["dynamic"] for vid in run["phantom_ids"]})
    if phantoms:
        print(f"\nVehicles recorded as arriving without reaching their destination "
              f"(dynamic, union over runs, n={len(phantoms)}):")
        for vid in phantoms:
            print(f"  {vid}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nFull per-run results written to {args.json_out}")


if __name__ == "__main__":
    main()
