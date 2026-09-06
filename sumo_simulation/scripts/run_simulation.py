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
import traci


def load_damage_schedule(damage_file_path):
    """Load the JSON schedule of earthquake road damage events."""
    with open(damage_file_path, 'r') as f:
        data = json.load(f)
    return data.get('blockage_events', [])


def run_simulation(net_file, vtypes_file, routes_file, damage_file, output_tripinfo,
                   enable_rerouting=True, use_gui=False, step_length=1.0, max_steps=5400, seed='42'):
    """
    Main TraCI simulation execution loop.
    """
    damage_events = load_damage_schedule(damage_file)

    # Select SUMO binary
    sumo_binary_name = 'sumo-gui.exe' if use_gui else 'sumo.exe'
    sumo_binary = os.path.join(os.environ['SUMO_HOME'], 'bin', sumo_binary_name)

    # Build command line
    # For dynamic fleet management, we only pass background routes to SUMO, 
    # and let TraCI inject the relief vehicles.
    sumo_route_files = routes_file.split(',')[1] if ',' in routes_file else routes_file
    
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
    # Parse dispatch routes manually to control fleet spawning
    relief_routes_file = [p for p in routes_file.split(',') if 'relief' in p][0]
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
                if sim_time >= req['depart']:
                    if active_dispatch_counts.get(req['type'], 0) < MAX_FLEET.get(req['type'], 100):
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
            if enable_rerouting and active_blocked_edges:
                active_vehicle_ids = traci.vehicle.getIDList()

                for veh_id in active_vehicle_ids:
                    try:
                        vtype = traci.vehicle.getTypeID(veh_id)
                        if vtype not in ['ambulance', 'first_responder', 'cargo_truck']:
                            continue
                        
                        current_route = traci.vehicle.getRoute(veh_id)
                        route_index = traci.vehicle.getRouteIndex(veh_id)
                        upcoming_edges = current_route[route_index:]

                        if any(edge in active_blocked_edges for edge in upcoming_edges):
                            try:
                                traci.vehicle.rerouteTraveltime(veh_id, currentTravelTimes=True)
                                
                                # Check if the newly computed route STILL contains a blocked edge
                                new_route = traci.vehicle.getRoute(veh_id)
                                new_upcoming = new_route[traci.vehicle.getRouteIndex(veh_id):]
                                
                                if any(edge in active_blocked_edges for edge in new_upcoming):
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

            # Print periodic heartbeat every 900 seconds
            if step % int(900 / step_length) == 0:
                running = traci.vehicle.getIDCount()
                print(f"[Heartbeat t={sim_time:.0f}s] Active relief vehicles: {sum(active_dispatch_counts.values())} | Queued: {len(dispatch_queue)} | Undeliverable: {undeliverable_count}", flush=True)

    finally:
        traci.close()
        print(f"\n=======================================================")
        print(f" Simulation Finished at t={sim_time:.1f}s")
        print(f" Total Reroute Interventions: {total_reroute_events}")
        print(f" Unique Vehicles Rerouted:    {len(vehicles_rerouted_set)}")
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
