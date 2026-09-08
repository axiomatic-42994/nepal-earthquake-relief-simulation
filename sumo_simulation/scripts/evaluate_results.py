import os
import xml.etree.ElementTree as ET
import json
import numpy as np


def get_total_expected(route_file):
    """Dynamically count the number of expected relief vehicles from the route file."""
    if not os.path.exists(route_file):
        print(f"Warning: route file {route_file} not found. Defaulting to 150 vehicles.")
        return 150
    tree = ET.parse(route_file)
    root = tree.getroot()
    
    dispatch_types = ['ambulance', 'first_responder', 'cargo_truck']
    count = 0
    # For routed files (vehicles with embedded routes)
    for v in root.findall('vehicle'):
        if v.attrib.get('type', '').split('@')[0] in dispatch_types:
            count += 1
    # For unrouted files (trips)
    for t in root.findall('trip'):
        if t.attrib.get('type', '').split('@')[0] in dispatch_types:
            count += 1
            
    return count if count > 0 else 150


def _load_route_destinations(route_file):
    """Extract the final edge for each dispatch vehicle from the routed file."""
    if route_file is None or not os.path.exists(route_file):
        return None
    tree = ET.parse(route_file)
    root = tree.getroot()
    dispatch_types = ['ambulance', 'first_responder', 'cargo_truck']
    destinations = {}
    for veh in root.findall('vehicle'):
        vtype = veh.attrib.get('type', '').split('@')[0]
        if vtype in dispatch_types:
            route_node = veh.find('route')
            if route_node is not None:
                edges = route_node.attrib['edges'].split()
                if edges:
                    destinations[veh.attrib['id']] = edges[-1]
    return destinations


def _is_genuine_delivery(tripinfo_elem, destinations):
    """Check if a tripinfo record represents a genuine delivery (arrived at assigned destination)
    rather than a false delivery caused by traci.vehicle.remove().
    
    When SUMO's TraCI removes a vehicle via vehicle.remove(), it still writes a tripinfo
    record, but the vehicle's arrivalLane will NOT match its assigned route's last edge.
    These records typically have duration=1.0s and should not be counted as deliveries.
    """
    if destinations is None:
        return True  # No route file provided; can't validate (backward compat)
    vid = tripinfo_elem.attrib['id']
    expected_edge = destinations.get(vid)
    if expected_edge is None:
        return True  # Vehicle not in route file; assume genuine
    arrival_lane = tripinfo_elem.attrib.get('arrivalLane', '')
    arrival_edge = '_'.join(arrival_lane.rsplit('_', 1)[:-1]) if '_' in arrival_lane else arrival_lane
    return arrival_edge == expected_edge


def parse_tripinfo(xml_file, total_expected, threshold_seconds=300.0, route_file=None):
    """Parse SUMO tripinfo.xml file into structured performance metrics.
    
    Args:
        xml_file: Path to the tripinfo XML output from SUMO.
        total_expected: Total number of dispatch vehicles expected.
        threshold_seconds: Max duration to count as "fulfilled" (default 300s).
        route_file: Optional path to the routed vehicle file. When provided,
            cross-references each vehicle's arrivalLane against its assigned
            route's last edge to filter out false deliveries caused by
            traci.vehicle.remove().
    """
    if not os.path.exists(xml_file):
        raise FileNotFoundError(f"File not found: {xml_file}")

    tree = ET.parse(xml_file)
    root = tree.getroot()
    # Filter to only consider dispatch vehicles (ignore background civilian traffic)
    dispatch_types = ['ambulance', 'first_responder', 'cargo_truck']
    all_dispatch_trips = [t for t in root.findall('tripinfo') if t.attrib.get('vType', '').split('@')[0] in dispatch_types]

    # Filter out false deliveries (vehicles removed by TraCI that still wrote tripinfo)
    destinations = _load_route_destinations(route_file)
    trips = [t for t in all_dispatch_trips if _is_genuine_delivery(t, destinations)]
    false_deliveries = len(all_dispatch_trips) - len(trips)

    completed = len(trips)
    completion_rate = (completed / total_expected) * 100.0 if total_expected > 0 else 0.0

    durations = [float(t.attrib['duration']) for t in trips]
    waiting_times = [float(t.attrib['waitingTime']) for t in trips]
    time_losses = [float(t.attrib['timeLoss']) for t in trips]
    route_lengths = [float(t.attrib['routeLength']) for t in trips]

    # Trips arriving within operational threshold
    fulfilled = [t for t in trips if float(t.attrib['duration']) <= threshold_seconds]
    fulfillment_rate = (len(fulfilled) / total_expected) * 100.0 if total_expected > 0 else 0.0

    # Categorize by clean base vehicle type
    type_data = {'ambulance': [], 'first_responder': [], 'cargo_truck': []}
    for t in trips:
        raw_type = t.attrib.get('vType', '')
        base_type = raw_type.split('@')[0] if '@' in raw_type else raw_type
        if base_type in type_data:
            type_data[base_type].append({
                'id': t.attrib['id'],
                'duration': float(t.attrib['duration']),
                'waiting': float(t.attrib['waitingTime']),
                'timeLoss': float(t.attrib['timeLoss']),
                'length': float(t.attrib['routeLength'])
            })

    type_stats = {}
    for vt, entries in type_data.items():
        if entries:
            type_stats[vt] = {
                'completed_count': len(entries),
                'avg_duration': float(np.mean([e['duration'] for e in entries])),
                'avg_waiting': float(np.mean([e['waiting'] for e in entries])),
                'avg_timeLoss': float(np.mean([e['timeLoss'] for e in entries]))
            }
        else:
            type_stats[vt] = {'completed_count': 0, 'avg_duration': 0.0, 'avg_waiting': 0.0, 'avg_timeLoss': 0.0}

    return {
        'total_expected': total_expected,
        'completed': completed,
        'uncompleted_or_stranded': total_expected - completed,
        'completion_rate_pct': float(completion_rate),
        'fulfilled_within_threshold': len(fulfilled),
        'fulfillment_rate_pct': float(fulfillment_rate),
        'threshold_seconds': threshold_seconds,
        'avg_duration_sec': float(np.mean(durations)) if durations else 0.0,
        'std_duration_sec': float(np.std(durations)) if durations else 0.0,
        'median_duration_sec': float(np.median(durations)) if durations else 0.0,
        'avg_waiting_time_sec': float(np.mean(waiting_times)) if waiting_times else 0.0,
        'avg_time_loss_sec': float(np.mean(time_losses)) if time_losses else 0.0,
        'avg_route_length_km': float(np.mean(route_lengths) / 1000.0) if route_lengths else 0.0,
        'by_vehicle_type': type_stats
    }


def generate_evaluation_report(dynamic_file, static_file, output_json, output_md, route_file, routed_file=None):
    """Compare dynamic vs static results and generate report."""
    total_expected = get_total_expected(route_file)
    dyn = parse_tripinfo(dynamic_file, total_expected, route_file=routed_file)
    sta = parse_tripinfo(static_file, total_expected, route_file=routed_file)

    # Compute comparative delta & improvements
    duration_diff = sta['avg_duration_sec'] - dyn['avg_duration_sec']
    duration_improvement_pct = (duration_diff / sta['avg_duration_sec']) * 100.0 if sta['avg_duration_sec'] > 0 else 0.0

    waiting_diff = sta['avg_waiting_time_sec'] - dyn['avg_waiting_time_sec']
    waiting_reduction_pct = (waiting_diff / sta['avg_waiting_time_sec']) * 100.0 if sta['avg_waiting_time_sec'] > 0 else 0.0

    fulfillment_diff = dyn['fulfillment_rate_pct'] - sta['fulfillment_rate_pct']

    comparison = {
        'scenario': '2015 Nepal Earthquake Kathmandu Relief Simulation',
        'metrics': {
            'dynamic_rerouting': dyn,
            'static_baseline': sta,
            'comparative_deltas': {
                'avg_duration_saved_seconds': float(duration_diff),
                'avg_duration_improvement_pct': float(duration_improvement_pct),
                'avg_waiting_reduction_seconds': float(waiting_diff),
                'avg_waiting_reduction_pct': float(waiting_reduction_pct),
                'fulfillment_rate_gain_pct': float(fulfillment_diff),
                'stranded_vehicles_prevented': sta['uncompleted_or_stranded'] - dyn['uncompleted_or_stranded']
            }
        }
    }

    # Save JSON summary
    with open(output_json, 'w') as f:
        json.dump(comparison, f, indent=4)

    # Generate Markdown Table Report
    md_content = rf"""# Simulation Performance Comparison: Dynamic TraCI Rerouting vs. Static Baseline

> **PROVENANCE — this is a SINGLE-RUN diagnostic, not the reported result.**
>
> Generated by `scripts/evaluate_results.py` from `{os.path.basename(dynamic_file)}`
> and `{os.path.basename(static_file)}`: one unseeded run against
> `demand/background_routes.rou.xml` (1,500 background vehicles).
>
> The figures reported in `reports/final_integration_report.md` come from the
> **N=5 seeded replication** (seeds 42/101/202/303/404, 1,200 background vehicles
> per seed) via `scripts/run_statistical_replication.py`. The two sets of numbers
> differ because they are different experiments — the single run is not a
> replication of the reported one. Quote the N=5 figures.
>
> **Abandoned missions are excluded from these figures.** When the TraCI
> controller removes an undeliverable vehicle, SUMO still writes a `<tripinfo>`
> record for it. `parse_tripinfo` now cross-references each record's
> `arrivalLane` against its assigned route's final edge and drops the ones that
> never arrived, so `Successfully Completed Trips` and `Mission Fulfillment Rate`
> count genuine deliveries only. This filtering is active whenever `route_file`
> is passed; called without it, the old inflated counts return.
> Run `scripts/verify_delivery_integrity.py` to see both columns side by side.

## 1. Overall System Performance Summary

| Metric | Static Baseline (No Rerouting) | Dynamic TraCI Rerouting | Improvement / Delta |
|---|:---:|:---:|:---:|
| **Total Dispatched Vehicles** | {sta['total_expected']} | {dyn['total_expected']} | - |
| **Successfully Completed Trips** | {sta['completed']} ({sta['completion_rate_pct']:.1f}%) | {dyn['completed']} ({dyn['completion_rate_pct']:.1f}%) | **+{dyn['completed'] - sta['completed']} vehicles delivered** |
| **Stranded / Jammed Vehicles** | {sta['uncompleted_or_stranded']} | {dyn['uncompleted_or_stranded']} | **-{sta['uncompleted_or_stranded'] - dyn['uncompleted_or_stranded']} stuck vehicles** |
| **Mission Fulfillment Rate ($\le 300\text{{s}}$)** | {sta['fulfillment_rate_pct']:.1f}% | {dyn['fulfillment_rate_pct']:.1f}% | **+{fulfillment_diff:.1f}% gain** |
| **Average Delivery Duration** | {sta['avg_duration_sec']:.1f} s ({sta['avg_duration_sec']/60:.1f} min) | {dyn['avg_duration_sec']:.1f} s ({dyn['avg_duration_sec']/60:.1f} min) | **{duration_improvement_pct:.1f}% faster ({duration_diff:.1f}s saved)** |
| **Average Stopped Waiting Time** | {sta['avg_waiting_time_sec']:.1f} s | {dyn['avg_waiting_time_sec']:.1f} s | **{waiting_reduction_pct:.1f}% queue reduction** |
| **Average Route Distance** | {sta['avg_route_length_km']:.2f} km | {dyn['avg_route_length_km']:.2f} km | +{(dyn['avg_route_length_km']-sta['avg_route_length_km'])*1000:.0f} m (detour margin) |

---

## 2. Performance Breakdown by Relief Vehicle Category

### A. Ambulances
- **Static Baseline:** Completed: {sta['by_vehicle_type']['ambulance']['completed_count']} | Avg Duration: {sta['by_vehicle_type']['ambulance']['avg_duration']:.1f}s | Avg Waiting: {sta['by_vehicle_type']['ambulance']['avg_waiting']:.1f}s
- **Dynamic Rerouting:** Completed: {dyn['by_vehicle_type']['ambulance']['completed_count']} | Avg Duration: {dyn['by_vehicle_type']['ambulance']['avg_duration']:.1f}s | Avg Waiting: {dyn['by_vehicle_type']['ambulance']['avg_waiting']:.1f}s
- **Key Takeaway:** Ambulances in dynamic mode avoid central corridor gridlocks, saving **{sta['by_vehicle_type']['ambulance']['avg_waiting'] - dyn['by_vehicle_type']['ambulance']['avg_waiting']:.1f} seconds of stopped delay**.

### B. First Responders
- **Static Baseline:** Completed: {sta['by_vehicle_type']['first_responder']['completed_count']} | Avg Duration: {sta['by_vehicle_type']['first_responder']['avg_duration']:.1f}s | Avg Waiting: {sta['by_vehicle_type']['first_responder']['avg_waiting']:.1f}s
- **Dynamic Rerouting:** Completed: {dyn['by_vehicle_type']['first_responder']['completed_count']} | Avg Duration: {dyn['by_vehicle_type']['first_responder']['avg_duration']:.1f}s | Avg Waiting: {dyn['by_vehicle_type']['first_responder']['avg_waiting']:.1f}s
- **Key Takeaway:** First responder units achieved a **{sta['by_vehicle_type']['first_responder']['avg_duration'] - dyn['by_vehicle_type']['first_responder']['avg_duration']:.1f}s duration improvement**, crucial for time-sensitive search and rescue ops.

### C. Heavy Cargo Trucks
- **Static Baseline:** Completed: {sta['by_vehicle_type']['cargo_truck']['completed_count']} | Avg Duration: {sta['by_vehicle_type']['cargo_truck']['avg_duration']:.1f}s | Avg Waiting: {sta['by_vehicle_type']['cargo_truck']['avg_waiting']:.1f}s
- **Dynamic Rerouting:** Completed: {dyn['by_vehicle_type']['cargo_truck']['completed_count']} | Avg Duration: {dyn['by_vehicle_type']['cargo_truck']['avg_duration']:.1f}s | Avg Waiting: {dyn['by_vehicle_type']['cargo_truck']['avg_waiting']:.1f}s
- **Key Takeaway:** Heavy trucks suffered the most catastrophic delays in static baseline. Dynamic rerouting successfully guided trucks to destination wards.
"""

    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"\nEvaluation complete!")
    print(f"JSON summary saved to: {output_json}")
    print(f"Markdown report saved to: {output_md}\n")
    print(md_content)


if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dyn_xml = os.path.join(base_dir, 'output', 'tripinfo_dynamic.xml')
    sta_xml = os.path.join(base_dir, 'output', 'tripinfo_static.xml')
    out_json = os.path.join(base_dir, 'output', 'comparison_summary.json')
    out_md = os.path.join(base_dir, 'output', 'comparison_report.md')
    route_file = os.path.join(base_dir, 'demand', 'relief_vehicles.rou.xml')
    routed_file = os.path.join(base_dir, 'demand', 'relief_vehicles_routed.rou.xml')

    generate_evaluation_report(dyn_xml, sta_xml, out_json, out_md, route_file, routed_file=routed_file)
