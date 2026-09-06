"""
generate_demand.py — Converts NMF-derived demand proportions into SUMO route files.

Takes the real demand proportions JSON (computed from topic_schema.json via
compute_demand_proportions.py) and produces a .rou.xml file with vehicles
dispatched from relief depots to affected areas, distributed by the
renormalized dispatch_category shares.

For the final integrated pipeline, this consumes real_demand_proportions.json
(Part D, Path 3 approximation). The old mock_lda_input.json interface is no
longer used for reported results.

Usage:
    python generate_demand.py --demand-input demand/real_demand_proportions.json \\
                              --net network/kathmandu.net.xml \\
                              --output demand/relief_vehicles.rou.xml \\
                              --total-vehicles 150 \\
                              --seed 42
"""

import json
import math
import random
import argparse
import os
import sys

# Add SUMO tools to path
if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
import sumolib


def find_depot_edges(net, n=3):
    """
    Find depot/origin edges near the center of the network.
    In our Kathmandu scenario, the center is roughly Tundikhel / Bir Hospital
    area — the main relief staging point.
    """
    boundary = net.getBoundary()
    cx = (boundary[0] + boundary[2]) / 2
    cy = (boundary[1] + boundary[3]) / 2

    candidates = net.getNeighboringEdges(cx, cy, r=800)
    candidates = [(e, d) for e, d in candidates
                  if ':' not in e.getID()
                  and e.allows('passenger')
                  and e.getLength() > 50]  # skip very short stubs
    candidates.sort(key=lambda x: x[1])

    depots = [e.getID() for e, d in candidates[:n]]
    if not depots:
        raise RuntimeError("No suitable depot edges found near network center")
    return depots


def find_destination_edges(net, n=30, seed=42):
    """
    Find destination edges spread across the network representing
    affected areas/wards. Selects edges distributed across the network
    that are reachable (have at least some connectivity).
    """
    rng = random.Random(seed)
    all_edges = [e for e in net.getEdges()
                 if ':' not in e.getID()
                 and e.allows('passenger')
                 and e.getLength() > 30]

    # Spread destinations across the network by sampling from
    # different spatial zones
    boundary = net.getBoundary()
    mid_x = (boundary[0] + boundary[2]) / 2
    mid_y = (boundary[1] + boundary[3]) / 2

    zones = {'NE': [], 'NW': [], 'SE': [], 'SW': []}
    for e in all_edges:
        shape = e.getShape()
        ex = sum(p[0] for p in shape) / len(shape)
        ey = sum(p[1] for p in shape) / len(shape)
        key = ('N' if ey > mid_y else 'S') + ('E' if ex > mid_x else 'W')
        zones[key].append(e.getID())

    destinations = []
    per_zone = max(1, n // 4)
    for zone_name, zone_edges in zones.items():
        if zone_edges:
            sample_n = min(per_zone, len(zone_edges))
            destinations.extend(rng.sample(zone_edges, sample_n))

    return destinations


def generate_routes(demand_input_path, net_path, output_path, total_vehicles=150,
                    time_start=0, time_end=5400, seed=42):
    """Main route generation logic using real demand proportions."""
    rng = random.Random(seed)

    # Load demand proportions
    with open(demand_input_path) as f:
        demand_data = json.load(f)

    proportions = demand_data['dispatch_proportions']
    meta = demand_data.get('_meta', {})

    print(f"Source: {meta.get('source', 'unknown')}")
    print(f"Method: {meta.get('method', 'unknown')}")
    if meta.get('warning'):
        print(f"WARNING: {meta['warning']}")
    print()

    # Load network
    net = sumolib.net.readNet(net_path)

    # Find depots and destinations
    depots = find_depot_edges(net, n=3)
    destinations = find_destination_edges(net, n=30, seed=seed)

    print(f"Depots ({len(depots)}): {depots}")
    print(f"Destinations ({len(destinations)}): {destinations[:5]}... (showing first 5)")
    print()

    # Distribute vehicles by proportion
    vehicles = []
    vehicle_id = 0
    time_span = time_end - time_start

    print(f"Total vehicles to dispatch: {total_vehicles}")
    print(f"Time window: {time_start}s to {time_end}s ({time_span}s span)")
    print()

    actual_total = 0
    for vtype, proportion in proportions.items():
        n_vehicles = max(1, round(total_vehicles * proportion))
        actual_total += n_vehicles
        print(f"  {vtype:<20}: proportion={proportion:.4f} -> {n_vehicles} vehicles")

        for i in range(n_vehicles):
            # Departure time: evenly spread within the time window with jitter
            base_time = time_start + (time_span * i / max(1, n_vehicles))
            depart = base_time + rng.uniform(0, time_span / max(1, n_vehicles))
            depart = round(depart, 1)

            origin = rng.choice(depots)
            dest = rng.choice(destinations)

            # Make sure origin != destination
            attempts = 0
            while dest == origin and attempts < 10:
                dest = rng.choice(destinations)
                attempts += 1

            vehicles.append({
                'id': f'{vtype}_{vehicle_id}',
                'type': vtype,
                'depart': depart,
                'from': origin,
                'to': dest,
            })
            vehicle_id += 1

    # Sort by departure time
    vehicles.sort(key=lambda v: v['depart'])

    # Write the route XML
    with open(output_path, 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xsi:noNamespaceSchemaLocation='
                '"http://sumo.dlr.de/xsd/routes_file.xsd">\n\n')

        for v in vehicles:
            f.write(f'    <trip id="{v["id"]}" '
                    f'type="{v["type"]}" '
                    f'depart="{v["depart"]}" '
                    f'from="{v["from"]}" '
                    f'to="{v["to"]}"/>\n')

        f.write('\n</routes>\n')

    print(f"\nGenerated {len(vehicles)} vehicle trips -> {output_path}")
    print(f"Time range: {vehicles[0]['depart']}s to {vehicles[-1]['depart']}s")

    # Summary by type
    from collections import Counter
    type_counts = Counter(v['type'] for v in vehicles)
    print(f"By type: {dict(type_counts)}")

    return vehicles


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate SUMO routes from NMF demand proportions')
    parser.add_argument('--demand-input', required=True, help='Path to real_demand_proportions.json')
    parser.add_argument('--net', required=True, help='Path to SUMO .net.xml')
    parser.add_argument('--output', required=True, help='Output .rou.xml path')
    parser.add_argument('--total-vehicles', type=int, default=150, help='Total vehicles to dispatch')
    parser.add_argument('--time-start', type=float, default=0, help='Dispatch window start (seconds)')
    parser.add_argument('--time-end', type=float, default=5400, help='Dispatch window end (seconds)')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    args = parser.parse_args()

    generate_routes(
        args.demand_input, args.net, args.output,
        total_vehicles=args.total_vehicles,
        time_start=args.time_start, time_end=args.time_end,
        seed=args.seed
    )
