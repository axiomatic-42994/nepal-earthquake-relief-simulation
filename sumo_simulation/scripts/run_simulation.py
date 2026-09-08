"""
run_simulation.py — TraCI simulation runner for Nepal Earthquake relief simulation.

Executes the Kathmandu relief traffic simulation under two distinct operational modes:
  1. Dynamic Rerouting Mode (active TraCI control loop)
     - Monitors road damage events
     - Blocks damaged edges dynamically at scheduled timestamps
     - Scans en-route relief vehicles whose path crosses blocked edges
     - Triggers dynamic Dijkstra rerouting around blocked corridors
  2. Static Baseline Mode (no rerouting)
     - Road damage occurs at scheduled timestamps
     - Vehicles strictly follow their initial departure route without rerouting

Usage:
    python run_simulation.py --mode dynamic --gui
    python run_simulation.py --mode static
"""

import os
import sys
import json
import argparse
import time

# Ensure SUMO tools are in path
if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))

try:
    import traci
except ImportError:
    raise SystemExit(
        "ERROR: could not import 'traci'.\n"
        "traci ships with SUMO rather than pip. Set the SUMO_HOME environment\n"
        "variable to your SUMO installation directory (the one containing\n"
        "'tools/' and 'bin/') and rerun.\n"
        f"SUMO_HOME is currently {'unset' if 'SUMO_HOME' not in os.environ else os.environ['SUMO_HOME']}."
    )


def resolve_sumo_binary(use_gui):
    """
    Locate the SUMO executable, with an actionable error if SUMO_HOME is unset
    or the binary is missing. Previously this indexed os.environ directly and
    hardcoded a .exe suffix, so a missing SUMO_HOME surfaced as a bare KeyError
    and the script could not run outside Windows.
    """
    sumo_home = os.environ.get('SUMO_HOME')
    if not sumo_home:
        raise SystemExit(
            "ERROR: SUMO_HOME is not set. Point it at your SUMO installation\n"
            "directory (the one containing 'bin/' and 'tools/') and rerun."
        )

    stem = 'sumo-gui' if use_gui else 'sumo'
    suffix = '.exe' if os.name == 'nt' else ''
    binary = os.path.join(sumo_home, 'bin', stem + suffix)

    if not os.path.exists(binary):
        raise SystemExit(
            f"ERROR: SUMO binary not found at {binary}.\n"
            f"Check that SUMO_HOME ({sumo_home}) points at a complete SUMO install."
        )
    return binary


def load_damage_schedule(damage_file_path):
    """Load the JSON schedule of earthquake road damage events."""
    with open(damage_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('blockage_events', [])


# --------------------------------------------------------------------------
# Pure decision predicates.
#
# These carry the control-loop's decision logic with no TraCI calls in them, so
# they can be unit-tested without a running SUMO (see tests/test_rerouting_logic.py).
# They are extracted verbatim from the inline expressions they replace; the
# behaviour of the loop is unchanged.
# --------------------------------------------------------------------------

def route_is_blocked(route, route_index, blocked_edges):
    """
    True if any edge the vehicle has yet to traverse is fully blocked.

    `route_index` is the vehicle's position along `route`, so the slice starts at
    the edge it is currently on. That edge is deliberately included: a vehicle
    already sitting on rubble still counts as blocked.

    Only FULLY blocked edges belong in `blocked_edges`. Partially blocked edges
    are merely slowed (2.5 m/s) and must stay routable, so the caller never adds
    them to the set.
    """
    return any(edge in blocked_edges for edge in route[route_index:])


def is_due(request, sim_time):
    """True if a queued dispatch request has reached its departure time."""
    return sim_time >= request['depart']


def has_fleet_capacity(vtype, active_counts, max_fleet, default_cap=100):
    """
    True if another vehicle of `vtype` may be released from the dispatch queue.

    Capacity is per vehicle type, not global: saturating the ambulance fleet must
    not stop a cargo truck from being dispatched.
    """
    return active_counts.get(vtype, 0) < max_fleet.get(vtype, default_cap)


def run_simulation(net_file, vtypes_file, routes_file, damage_file, output_tripinfo,
                   enable_rerouting=True, use_gui=False, step_length=1.0, max_steps=5400, seed='42'):
    """
    Main TraCI simulation execution loop.
    """
    damage_events = load_damage_schedule(damage_file)

    # Select SUMO binary
    sumo_binary = resolve_sumo_binary(use_gui)

    # Build command line.
    # For dynamic fleet management, SUMO is only handed the BACKGROUND routes;
    # relief vehicles are injected by TraCI from `dispatch_queue` below so the
    # fleet cap can be enforced. `routes_file` is the comma-joined pair
    # "<relief routed file>,<background file>" assembled in __main__.
    route_parts = [p for p in routes_file.split(',') if p]
    background_parts = [p for p in route_parts if 'relief' not in os.path.basename(p)]
    if not background_parts:
        raise SystemExit(
            f"ERROR: no background route file found in --route-files '{routes_file}'.\n"
            "Expected '<relief_*_routed.rou.xml>,<background.rou.xml>'."
        )
    sumo_route_files = ','.join(background_parts)

    cmd = [
        sumo_binary,
        '--net-file', net_file,
        '--additional-files', vtypes_file,
        '--route-files', sumo_route_files,
        '--tripinfo-output', output_tripinfo,
        '--step-length', str(step_length),
        '--begin', '0',
        '--end', str(max_steps),
        '--seed', str(seed),
        '--ignore-route-errors', 'true',
        '--time-to-teleport', '300',
        '--collision.action', 'teleport',
        '--no-warnings', 'true',
        '--no-step-log', 'true',
        '--duration-log.statistics', 'true'
    ]

    # If sublane lateral resolution is desired
    cmd.extend(['--lateral-resolution', '0.8'])

    print(f"\n=======================================================")
    print(f" Starting SUMO Simulation via TraCI")
    print(f" Mode:             {'DYNAMIC REROUTING' if enable_rerouting else 'STATIC BASELINE'}")
    print(f" GUI:              {'Enabled' if use_gui else 'Disabled (Headless)'}")
    print(f" Tripinfo Output:  {output_tripinfo}")
    print(f"=======================================================\n")

    traci.start(cmd)

    active_blocked_edges = set()
    events_triggered = set()
    total_reroute_events = 0
    vehicles_rerouted_set = set()

    step = 0
    sim_time = 0.0

    import xml.etree.ElementTree as ET
    # Parse dispatch routes manually to control fleet spawning.
    # Match on the basename: the repository directory is itself called
    # "nepal-earthquake-relief-simulation", so matching 'relief' against the full
    # path matches every entry and silently relies on ordering.
    relief_candidates = [p for p in route_parts if 'relief' in os.path.basename(p)]
    if not relief_candidates:
        raise SystemExit(
            f"ERROR: no relief route file found in --route-files '{routes_file}'.\n"
            "Expected a filename containing 'relief', e.g. 'relief_vehicles_routed.rou.xml'."
        )
    relief_routes_file = relief_candidates[0]
    tree = ET.parse(relief_routes_file)
    dispatch_queue = []
    for veh in tree.getroot().findall('vehicle'):
        route_node = veh.find('route')
        if route_node is not None:
            dispatch_queue.append({
                'id': veh.attrib['id'],
                'type': veh.attrib['type'],
                'depart': float(veh.attrib['depart']),
                'edges': route_node.attrib['edges'].split()
            })
    
    # Sort queue by depart time
    dispatch_queue.sort(key=lambda x: x['depart'])
    
    MAX_FLEET = {
        'ambulance': 8,
        'first_responder': 8,
        'cargo_truck': 8
    }
    
    active_dispatch_counts = { 'ambulance': 0, 'first_responder': 0, 'cargo_truck': 0 }
    undeliverable_count = 0
    
    try:
        while traci.simulation.getMinExpectedNumber() > 0 and sim_time < max_steps:
            traci.simulationStep()
            sim_time = traci.simulation.getTime()
            step += 1

            # 0. Fleet Management & Queuing
            # Update active counts
            active_ids = traci.vehicle.getIDList()
            for vtype in active_dispatch_counts.keys():
                active_dispatch_counts[vtype] = sum(1 for v in active_ids if traci.vehicle.getTypeID(v) == vtype)
                
            # Try to spawn pending requests if fleet has capacity
            # Create a list to track which vehicles to remove from queue
            spawned = []
            for req in dispatch_queue:
                if is_due(req, sim_time):
                    if has_fleet_capacity(req['type'], active_dispatch_counts, MAX_FLEET):
                        # Spawn vehicle
                        route_id = f"route_{req['id']}"
                        try:
                            traci.route.add(route_id, req['edges'])
                            traci.vehicle.add(req['id'], route_id, typeID=req['type'])
                            active_dispatch_counts[req['type']] += 1
                            spawned.append(req)
                        except traci.TraCIException as e:
                            # E.g. route is disconnected right at spawn
                            print(f"[t={sim_time:.1f}s] UNDELIVERABLE: Request {req['id']} cannot be dispatched. {e}", flush=True)
                            undeliverable_count += 1
                            spawned.append(req)
                else:
                    break # queue is sorted by depart
                    
            for req in spawned:
                dispatch_queue.remove(req)

            # 1. Check for scheduled earthquake damage events
            for event in damage_events:
                event_id = event['event_id']
                event_time = event['timestamp_seconds']

                if event_id not in events_triggered and sim_time >= event_time:
                    events_triggered.add(event_id)
                    print(f"\n[t={sim_time:.1f}s] EARTHQUAKE DAMAGE EVENT: '{event_id}'", flush=True)
                    print(f" Description: {event['description']}", flush=True)

                    for edge_id in event.get('fully_blocked_edges', []):
                        # Choke max speed to 0.1 m/s (~0.36 km/h) to simulate heavy rubble blockage
                        traci.edge.setMaxSpeed(edge_id, 0.1)
                        # Set massive travel time penalty for routing engine
                        traci.edge.adaptTraveltime(edge_id, 100000.0)
                        active_blocked_edges.add(edge_id)
                        print(f"   --> Edge FULLY BLOCKED / RUBBLE RESTRICTION: {edge_id}")

                    for edge_id in event.get('partially_blocked_edges', []):
                        # Passable but degraded: reduce max speed to 2.5 m/s (9 km/h)
                        traci.edge.setMaxSpeed(edge_id, 2.5)
                        try:
                            length = traci.lane.getLength(f"{edge_id}_0")
                            traci.edge.adaptTraveltime(edge_id, length / 2.5)
                        except traci.TraCIException:
                            pass
                        print(f"   --> Edge PARTIALLY BLOCKED / DEGRADED SPEED: {edge_id}")

            # 2. If Dynamic Rerouting is enabled, inspect active vehicles and reroute if needed
            #
            # !! KNOWN MEASUREMENT DEFECT — READ BEFORE QUOTING ANY DYNAMIC-MODE METRIC !!
            # The two `traci.vehicle.remove(...)` calls below abandon a mission, but SUMO
            # still writes a <tripinfo> record for a TraCI-removed vehicle, with `arrival`
            # set to the removal time. evaluate_results.py counts any tripinfo record as a
            # completed trip, so each abandoned vehicle is scored as a SUCCESSFUL delivery
            # — and, because it is removed within ~1s of spawning, as one that beat the
            # 300s fulfilment threshold and drags the mean duration down.
            #
            # Measured on the committed N=5 outputs: 10 vehicles per dynamic run are
            # removed here. Edge '1194719931' is their DESTINATION, not just a via-edge,
            # so no reroute could ever avoid it — abandonment is structurally guaranteed
            # for them. Static mode performs no removals at all, so the bias is one-sided.
            #
            # Static mode is not a clean control for these 10 either: --time-to-teleport
            # 300 is set, and 9 of the 10 arrive with vaporized="teleport" after stalling
            # 301-1448s. Only cargo_truck_102 drives the last stretch at 0.1 m/s. Do not
            # read "static delivered them" as "patience beats rerouting".
            #
            # Delivery-verified figures (arrival edge == intended destination edge) are
            # produced by scripts/verify_delivery_integrity.py. This logic is left AS IS
            # so the published runs stay reproducible; do not "fix" it silently — doing so
            # changes every reported dynamic-mode number.
            if enable_rerouting and active_blocked_edges:
                active_vehicle_ids = traci.vehicle.getIDList()

                for veh_id in active_vehicle_ids:
                    try:
                        vtype = traci.vehicle.getTypeID(veh_id)
                        if vtype not in ['ambulance', 'first_responder', 'cargo_truck']:
                            continue
                        
                        current_route = traci.vehicle.getRoute(veh_id)
                        route_index = traci.vehicle.getRouteIndex(veh_id)

                        if route_is_blocked(current_route, route_index, active_blocked_edges):
                            try:
                                traci.vehicle.rerouteTraveltime(veh_id, currentTravelTimes=True)

                                # Check if the newly computed route STILL contains a blocked edge
                                new_route = traci.vehicle.getRoute(veh_id)
                                new_index = traci.vehicle.getRouteIndex(veh_id)

                                if route_is_blocked(new_route, new_index, active_blocked_edges):
                                    # The vehicle could not find a path that avoids the fully blocked edge.
                                    # This means the destination is completely cut off by damage.
                                    print(f"[t={sim_time:.1f}s] UNDELIVERABLE: Vehicle '{veh_id}' destination cut off! Removing from network.", flush=True)
                                    traci.vehicle.remove(veh_id, traci.constants.REMOVE_PARKING)
                                    undeliverable_count += 1
                                else:
                                    total_reroute_events += 1
                                    vehicles_rerouted_set.add(veh_id)
                                    print(f"[t={sim_time:.1f}s] Dynamic Reroute: Vehicle '{veh_id}' ({vtype}) rerouted around debris.", flush=True)
                            except traci.TraCIException as e:
                                # Vehicle destination is fully cut off by damage (disconnected graph)
                                print(f"[t={sim_time:.1f}s] UNDELIVERABLE: Vehicle '{veh_id}' destination cut off! Removing from network.", flush=True)
                                traci.vehicle.remove(veh_id, traci.constants.REMOVE_PARKING)
                                undeliverable_count += 1
                    except traci.TraCIException:
                        pass

            # Print periodic heartbeat every 900 seconds.
            # max(1, ...) guards a step_length > 900, which would otherwise make
            # the modulus divide by zero.
            if step % max(1, int(900 / step_length)) == 0:
                print(f"[Heartbeat t={sim_time:.0f}s] Active relief vehicles: {sum(active_dispatch_counts.values())} | Queued: {len(dispatch_queue)} | Undeliverable: {undeliverable_count}", flush=True)

    finally:
        traci.close()
        print(f"\n=======================================================")
        print(f" Simulation Finished at t={sim_time:.1f}s")
        print(f" Total Reroute Interventions: {total_reroute_events}")
        print(f" Unique Vehicles Rerouted:    {len(vehicles_rerouted_set)}")
        print(f" Missions Abandoned (UNDELIVERABLE): {undeliverable_count}")
        if undeliverable_count:
            print(f" NOTE: abandoned missions still appear in {os.path.basename(output_tripinfo)}")
            print(f"       as completed trips. Use scripts/verify_delivery_integrity.py")
            print(f"       for delivery-verified metrics.")
        if dispatch_queue:
            print(f" WARNING: {len(dispatch_queue)} dispatch requests never left the queue")
            print(f"          (fleet saturated, or the loop ended before their depart time).")
        print(f" Trip statistics saved to:    {output_tripinfo}")
        print(f"=======================================================\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Nepal Earthquake SUMO-TraCI Simulation Runner')
    parser.add_argument('--mode', choices=['dynamic', 'static'], default='dynamic',
                        help="Simulation mode: 'dynamic' (TraCI rerouting) or 'static' (baseline)")
    parser.add_argument('--gui', action='store_true', help='Launch sumo-gui instead of headless sumo')
    parser.add_argument('--damage-file', default=None, help='Path to road damage JSON')
    parser.add_argument('--output', default=None, help='Path to output tripinfo XML')
    parser.add_argument('--seed', default='42', help='Random seed for SUMO')
    parser.add_argument('--background', default=None, help='Path to background traffic rou.xml')
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    net_path = os.path.join(base_dir, 'network', 'kathmandu.net.xml')
    vtypes_path = os.path.join(base_dir, 'vehicles', 'vtypes.add.xml')
    
    bg_path = args.background if args.background else os.path.join(base_dir, 'demand', 'background_routes.rou.xml')
    routes_path = os.path.join(base_dir, 'demand', 'relief_vehicles_routed.rou.xml') + ',' + bg_path

    if args.damage_file is None:
        args.damage_file = os.path.join(base_dir, 'damage', 'road_damage_events.json')

    if args.output is None:
        args.output = os.path.join(base_dir, 'output', f'tripinfo_{args.mode}.xml')

    is_dynamic = (args.mode == 'dynamic')
    run_simulation(
        net_file=net_path,
        vtypes_file=vtypes_path,
        routes_file=routes_path,
        damage_file=args.damage_file,
        output_tripinfo=args.output,
        enable_rerouting=is_dynamic,
        use_gui=args.gui,
        seed=args.seed
    )
